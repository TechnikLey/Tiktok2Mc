#!/usr/bin/env python3
# ==================================================
# main.py - TikTok Live to Minecraft bridge
# ==================================================
# Connects to a TikTok livestream, listens for gifts,
# follows, and likes, then translates those events
# into Minecraft commands via RCON or datapacks.
# Also runs a webhook server for the MinecraftServerAPI
# plugin and forwards overlay updates.
# ==================================================

import sys
import yaml
import asyncio
import aiohttp
import re
import shutil
import subprocess
import shlex
import threading
import logging
import traceback
import time
import datetime
import json
from pathlib import Path
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, ConnectEvent, LikeEvent, CommentEvent, JoinEvent, ShareEvent, LiveEndEvent
from mcrcon import MCRcon
from flask import Flask, request
from core.validator import validate_file, print_diagnostics
from core.paths import get_base_dir
from core.hook_api import HookAPI, HOOK_ACTIONS
from core.hook_loader import load_event_hooks
from core.overlay_utils import send_overlay_text

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)

# ==========================================
# CONFIGURATION & PATHS
# ==========================================

BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR.parent / "config" / "config.yaml").resolve()
ACTIONS_FILE = (BASE_DIR.parent / "data" / "actions.mca").resolve()
SHELL_ACTIONS_FILE = (BASE_DIR.parent / "data" / "shell_actions.txt").resolve()
FOLLOWED_USERS_FILE = (BASE_DIR.parent / "data" / "followed_users.txt").resolve()

class BotContext:
    """Central state container for the TikTok-to-Minecraft bridge."""
    def __init__(self):
        # RCON
        self.mc_host = "localhost"
        self.mc_port = 25575
        self.mc_pass = ""

        # Config values (set by load_config)
        self.datapack_root = Path("")
        self.tiktok_user = ""
        self.reconnect_delay = 30
        self.server_host = "127.0.0.1"
        self.like_goal_port = 29193
        self.mcserver_api_port = 29188
        self.overlaytxt_port = 29186
        self.like_triggers = []
        self.autosave_interval_seconds = 60

        # Follow tracking
        self.follow_tracking_mode = "all_time"
        self.follow_tracking_file = FOLLOWED_USERS_FILE
        self._followed_cache = set()

        # Comment commands
        self.comment_cmd_enable = False
        self.comment_cmd_groups = []
        self.comment_cmd_all_prefixes = set()
        self.comment_cmd_global_cooldown = 0
        self.comment_cmd_global_last = 0.0
        self.comment_cmd_global_user_cooldown = 0
        self.comment_cmd_global_user_last = {}
        self.comment_cmd_last_global = {}
        self.comment_cmd_last_user = {}

        # Queues
        self.trigger_queue = asyncio.Queue(maxsize=10_000)
        self.rcon_queue = asyncio.Queue(maxsize=10_000)
        self.likegoal_queue = asyncio.Queue()

        # Throttling
        self.throttle_time = 0.5

        # Datapack
        self.datapack_name = "StreamingTool"
        self.namespace = "streamingtool"
        self.start_likes = None
        self.valid_functions = set()
        self.vanilla_functions = set()
        self.shell_actions_cache = {}
        self.script_actions = {}
        self.overlay_actions = {}
        self.rcon_only_actions = {}

        # Threading
        self.like_lock = threading.Lock()
        self.tiktok_lock = threading.Lock()
        self.gift_lock = threading.Lock()
        self.rcon_pool_lock = asyncio.Lock()

        # RCON state
        self.rcon_connection = None
        self.last_rcon_attempt = 0

        # Like goal state
        self.last_likegoal_sent = 0
        self.last_likegoal_time = 0
        self.likegoal_interval = 3

        # TikTok state
        self.disable_tiktok_connect = False

        # Gift tracking
        self.gift_value_usd = 0
        self.gift_day_start_value = 0
        self.gift_current_log_date = None

        # Runtime
        self.main_loop = None
        self.hook_api = None
        self.queue_active = True
        self.config = {}
        self.runtime_path_shutdown = (BASE_DIR / "runtime" / "shutdown").resolve()

        # RCON retry tracking (keyed by repr(commands) to limit re-queue loops)
        self.max_rcon_retries = 3
        self.rcon_queue_retries: dict[str, int] = {}


ctx = BotContext()

app = Flask(__name__)

werkzeug_log = logging.getLogger('werkzeug')
werkzeug_log.setLevel(logging.WARNING)

# ==========================================
# SETUP & HELPER FUNCTIONS
# ==========================================

def _check_dup_cmd_config():
    """Check raw YAML for duplicate keys in commands_config sections."""
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except Exception:
        return
    lines = text.split("\n")
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("commands_config:"):
            continue
        base_indent = len(line) - len(line.lstrip())
        seen = {}
        j = i + 1
        while j < len(lines):
            cline = lines[j]
            if not cline.strip() or cline.strip().startswith("#"):
                j += 1
                continue
            indent = len(cline) - len(cline.lstrip())
            if indent <= base_indent:
                break
            if ":" in cline and indent == base_indent + 2:
                key = cline.strip().split(":")[0].strip().lower()
                if key in seen:
                    log.error(f"command_config: Command '{key}' configured multiple times! (line {j+1}, first at line {seen[key]})")
                    found = True
                else:
                    seen[key] = j + 1
            j += 1
    if found:
        input("Press Enter to exit...")
        sys.exit(1)


def load_config():
    """Loads configuration values from the YAML config file."""
    if not CONFIG_FILE.exists():
        log.error(f"Config not found: {CONFIG_FILE}")
        return False

    _check_dup_cmd_config()

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        ctx.config = config

        ctx.mc_host = config.get("server_host", "127.0.0.1")
        ctx.mc_pass = config.get("rcon", {}).get("password", "")
        ctx.mc_port = config.get("rcon", {}).get("port", 25575)
        ctx.server_host = config.get("server_host", "127.0.0.1")
        ctx.tiktok_user = config.get("tiktok", {}).get("user", "")
        ctx.reconnect_delay = config.get("tiktok", {}).get("reconnect_delay_seconds", 10)
        ctx.mcserver_api_port = config.get("minecraft_server_api", {}).get("web_server_port", 29188)
        ctx.overlaytxt_port = config.get("overlay_text", {}).get("port", 29186)
        ctx.like_goal_port = config.get("like_goal", {}).get("port", 29193)
        ctx.autosave_interval_seconds = config.get("tiktok", {}).get("autosave_interval_seconds", 60)

        ft_cfg = config.get("tiktok", {}).get("follow_tracking", {})
        ctx.follow_tracking_mode = str(ft_cfg.get("mode", "all_time")).lower()
        raw_path = str(ft_cfg.get("file", "data/followed_users.txt"))
        ctx.follow_tracking_file = (BASE_DIR.parent / raw_path).resolve()
        ctx._followed_cache = set()
        if ctx.follow_tracking_file.exists():
            with open(ctx.follow_tracking_file, "r") as f:
                ctx._followed_cache = set(line.strip().lower() for line in f if line.strip())
            log.info(f"[CONFIG] Follow tracking ({ctx.follow_tracking_mode}): {len(ctx._followed_cache)} known followers loaded")
        if ctx.follow_tracking_mode == "per_stream":
            ctx.follow_tracking_file.write_text("")
            ctx._followed_cache.clear()
            log.info("[CONFIG] Follow tracking mode 'per_stream' — follower list reset")

        ctx.like_triggers = validate_like_triggers(config.get("like_goal", {}).get("triggers", []))

        comment_cmd_cfg = config.get("comment_commands", {})
        ctx.comment_cmd_enable = bool(comment_cmd_cfg.get("enabled", False))
        ctx.comment_cmd_global_cooldown = max(0, int(comment_cmd_cfg.get("cooldown", 0)))
        ctx.comment_cmd_global_user_cooldown = max(0, int(comment_cmd_cfg.get("user_cooldown", 0)))
        raw_groups = comment_cmd_cfg.get("groups", None)
        if raw_groups is None:
            raw_groups = [{
                "enabled": True,
                "prefix": comment_cmd_cfg.get("prefix", "#"),
                "allowed_roles": comment_cmd_cfg.get("allowed_roles", ["moderator"]),
                "mode": comment_cmd_cfg.get("mode", "deny-all"),
                "commands": comment_cmd_cfg.get("commands", []),
                "handler": "rcon",
                "url": "",
            }]
            log.info("[CONFIG] comment_commands: using legacy single-group format")
        ctx.comment_cmd_groups = []
        ctx.comment_cmd_all_prefixes = set()
        seen_prefixes = set()
        for g in raw_groups:
            prefix = str(g.get("prefix", "#"))
            ctx.comment_cmd_all_prefixes.add(prefix)
            enabled = bool(g.get("enabled", True))
            if not enabled:
                log.info(f"[CONFIG] comment_commands group '{prefix}': disabled by config")
                continue
            if prefix in seen_prefixes:
                log.warning(f"comment_commands: duplicate prefix '{prefix}' — keeping only first definition, skipping duplicate")
                continue
            seen_prefixes.add(prefix)
            raw_roles = g.get("allowed_roles", ["moderator"])
            roles = [str(r).strip().lower() for r in raw_roles if str(r).strip()] if isinstance(raw_roles, list) else ["moderator"]
            mode = str(g.get("mode", "deny-all")).lower()
            raw_commands = g.get("commands", [])
            commands = []
            seen_cmd = set()
            dup_warn_count = 0
            dup_warn_max = 5
            if isinstance(raw_commands, list):
                for item in raw_commands:
                    if isinstance(item, str):
                        cname = item.strip().lower()
                        if cname:
                            if cname in seen_cmd:
                                dup_warn_count += 1
                                if dup_warn_count <= dup_warn_max:
                                    log.warning(f"comment_commands group '{prefix}': '{cname}' listed multiple times in commands")
                            seen_cmd.add(cname)
                            commands.append(cname)
            if dup_warn_count > dup_warn_max:
                remaining = dup_warn_count - dup_warn_max
                log.warning(f"comment_commands group '{prefix}': {remaining} further duplicate command warnings suppressed")
            commands_config = {}
            raw_config = g.get("commands_config", {})
            if isinstance(raw_config, dict):
                for cname, ccfg in raw_config.items():
                    cname = cname.strip().lower()
                    if cname and isinstance(ccfg, dict):
                        # Resolve port vars in per-command url
                        if "url" in ccfg:
                            url_tpl = str(ccfg["url"])
                            spotify_port = config.get("spotify", {}).get("port", 29194)
                            url_tpl = url_tpl.replace("{spotify_port}", str(spotify_port))
                            cp_port = config.get("channel_points", {}).get("port", 29195)
                            url_tpl = url_tpl.replace("{channel_points_port}", str(cp_port))
                            ccfg = {**ccfg, "url": url_tpl}
                        commands_config[cname] = ccfg
            handler = str(g.get("handler", "rcon")).lower()
            url = str(g.get("url", ""))
            spotify_port = config.get("spotify", {}).get("port", 29194)
            url = url.replace("{spotify_port}", str(spotify_port))
            cp_port = config.get("channel_points", {}).get("port", 29195)
            url = url.replace("{channel_points_port}", str(cp_port))
            cooldown = max(0, int(g.get("cooldown", 0)))
            user_cooldown = max(0, int(g.get("user_cooldown", 0)))
            if mode == "allow-all" and not commands and handler == "rcon":
                log.warning(f"comment_commands group '{prefix}': allow-all + empty list — ALL commands allowed!")
            trigger_comment = g.get("trigger_comment_event", True)

            # Warn about commands_config entries that can never be used
            cmd_warn_count = 0
            cmd_warn_max = 5
            for cname in commands_config:
                if mode == "deny-all" and cname not in commands:
                    cmd_warn_count += 1
                    if cmd_warn_count <= cmd_warn_max:
                        log.warning(f"comment_commands group '{prefix}': '{cname}' in commands_config but NOT in commands list (deny-all) — will never match")
                elif mode == "allow-all" and cname in commands:
                    cmd_warn_count += 1
                    if cmd_warn_count <= cmd_warn_max:
                        log.warning(f"comment_commands group '{prefix}': '{cname}' in commands_config AND in commands list (allow-all) — blocked by mode")
            if cmd_warn_count > cmd_warn_max:
                remaining = cmd_warn_count - cmd_warn_max
                log.warning(f"comment_commands group '{prefix}': {remaining} further command config warnings suppressed")

            ctx.comment_cmd_groups.append({
                "prefix": prefix,
                "roles": roles,
                "mode": mode,
                "commands": commands,
                "commands_config": commands_config,
                "handler": handler,
                "url": url,
                "cooldown": cooldown,
                "user_cooldown": user_cooldown,
                "trigger_comment_event": trigger_comment,
            })

        ctx.datapack_root = (BASE_DIR / ".." / "server" / "mc" / "world" / "datapacks").resolve()
        return ctx.datapack_root.exists() and ctx.datapack_root.is_dir()
    except Exception as e:
        log.error(f"Config error: {e}")
        return False

def sanitize_filename(name):
    """Returns a Minecraft-safe name (only a-z, 0-9, _, -)."""
    name = str(name).lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_-]", "", name)

def generate_datapack():
    """Generates datapack files for vanilla commands and stores
    plugin/script commands separately.
    Supported command prefixes: '!' (RCON), '$' (script), '/' (vanilla).
    Multiplier ' xN' applies to all types.
    """
    log.info(f"\n[BUILD] Generating datapack in: {ctx.datapack_root}")

    full_dp_path = ctx.datapack_root / ctx.datapack_name
    functions_path = full_dp_path / "data" / ctx.namespace / "function"

    # Reset state
    ctx.rcon_only_actions = {}
    ctx.valid_functions = set()
    collected_vanilla = {}
    ctx.vanilla_functions = set()
    ctx.script_actions = {}
    ctx.overlay_actions = {}

    # Prepare filesystem
    try:
        if full_dp_path.exists():
            shutil.rmtree(full_dp_path)
        functions_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.error(f"Failed to create datapack directory: {e}")
        return

    try:
        # === Parse actions.mca ===
        if ACTIONS_FILE.exists():
            with ACTIONS_FILE.open("r", encoding="utf-8") as f:
                for line_num, original_line in enumerate(f, 1):
                    # Strip comments
                    line = original_line.split("#", 1)[0].strip()
                    if not line or ":" not in line:
                        continue

                    trigger, full_cmd_line = map(str.strip, line.split(":", 1))
                    name = sanitize_filename(trigger)
                    if not name:
                        continue

                    # Split commands at semicolons
                    individual_commands = full_cmd_line.split(";")
                    for cmd in individual_commands:
                        cmd = cmd.strip()
                        if not cmd:
                            continue

                        # Detect command prefix
                        _overlay_match = re.match(r"@(\w+)>>", cmd)
                        if _overlay_match:
                            kind = "overlay"
                            overlay_name = _overlay_match.group(1)
                            body = cmd[_overlay_match.end():].strip()
                        elif cmd.startswith(">>"):
                            kind = "overlay"
                            overlay_name = "default"
                            body = cmd[2:].strip()
                        elif cmd.startswith("!"):
                            kind = "rcon"
                            body = cmd[1:].strip()
                        elif cmd.startswith("$"):
                            kind = "script"
                            body = cmd[1:].strip()
                        elif cmd.startswith("/"):
                            kind = "vanilla"
                            body = cmd[1:].strip()
                        else:
                            log.error(f"Invalid command without prefix on line {line_num}: {cmd}")
                            continue

                        # Parse multiplier (e.g. "command x3")
                        multi_match = re.search(r"\s+x(\d+)\s*$", body)
                        if multi_match:
                            base_cmd = body[:multi_match.start()].replace("{user}", "@a")
                            times = int(multi_match.group(1))
                        else:
                            base_cmd = body.replace("{user}", "@a")
                            times = 1
                        if times < 1:
                            times = 1

                        # Sort into the appropriate action list
                        if kind == "overlay":
                            # Store (overlay_name, raw body) — no multiplier
                            ctx.overlay_actions.setdefault(name, []).append((overlay_name, body))
                            ctx.valid_functions.add(name)
                        else:
                            for _ in range(times):
                                if kind == "script":
                                    ctx.script_actions.setdefault(name, []).append(base_cmd)
                                    ctx.valid_functions.add(name)
                                elif kind == "rcon":
                                    ctx.rcon_only_actions.setdefault(name, []).append(base_cmd)
                                    ctx.valid_functions.add(name)
                                elif kind == "vanilla":
                                    collected_vanilla.setdefault(name, []).append(base_cmd)
                                    ctx.valid_functions.add(name)
                                    ctx.vanilla_functions.add(name)

        # === Write datapack files (vanilla commands only) ===
        for name, commands in collected_vanilla.items():
            if not commands:
                continue
            file_path = functions_path / f"{name}.mcfunction"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("w", encoding="utf-8") as out:
                out.write("\n".join(commands) + "\n")

        # Meta file
        meta_file = full_dp_path / "pack.mcmeta"
        with meta_file.open("w", encoding="utf-8") as f:
            f.write('{"pack": {"pack_format": 15, "description": "TikTok Streaming Tool"}}')

        # Create ZIP archive
        zip_path = Path(ctx.datapack_root) / ctx.datapack_name
        shutil.make_archive(str(zip_path), "zip", full_dp_path)

    except Exception as e:
        traceback.print_exc()
        log.error(f"Datapack build failed: {e}")

# ================================
# RCON WORKER
# ================================

async def rcon_worker():
    """Background worker that dequeues RCON commands and sends them to the Minecraft server."""
    log.info("[RCON-QUEUE] Worker started.")
    while True:
        commands, source_user = await ctx.rcon_queue.get()
        try:
            if not ctx.queue_active:
                retry_key = f"queue_active_{repr((commands, source_user))}"
                retries = ctx.rcon_queue_retries.get(retry_key, 0) + 1
                if retries <= ctx.max_rcon_retries:
                    ctx.rcon_queue_retries[retry_key] = retries
                    await ctx.rcon_queue.put((commands, source_user))
                else:
                    log.info(f"[RCON] Dropping commands after queue inactive for {retries} attempts: {commands}")
                    ctx.rcon_queue_retries.pop(retry_key, None)
                await asyncio.sleep(1)
                continue

            q_size = ctx.rcon_queue.qsize()
            wait_time = ctx.throttle_time
            inner_pause = 0.01 
            
            # Dynamic throttling based on queue depth
            if q_size > 100:
                wait_time, inner_pause = 0.01, 0.001
            elif q_size > 50:
                wait_time, inner_pause = 0.05, 0.005
            elif q_size > 20:
                wait_time, inner_pause = 0.1, 0.01

            async with ctx.rcon_pool_lock:
                if ctx.rcon_connection is None:
                    now = time.time()
                    if now - ctx.last_rcon_attempt < 5:
                        raise ConnectionError("Reconnect cooldown active")
                    
                    ctx.last_rcon_attempt = now
                    try:
                        ctx.rcon_connection = await asyncio.wait_for(
                            asyncio.to_thread(lambda: MCRcon(ctx.mc_host, ctx.mc_pass, port=ctx.mc_port)),
                            timeout=3.0
                        )
                        await asyncio.wait_for(
                            asyncio.to_thread(ctx.rcon_connection.connect),
                            timeout=3.0
                        )
                    except Exception as e:
                        ctx.rcon_connection = None
                        raise ConnectionError(f"Server unreachable: {e}")

                for cmd in commands:
                    await asyncio.to_thread(ctx.rcon_connection.command, cmd)
                    if inner_pause > 0:
                        await asyncio.sleep(inner_pause)

        except Exception as e:
            log.info(f"[RCON OFFLINE] {e}")
            ctx.rcon_connection = None
            await asyncio.sleep(5)
            retry_key = repr((commands, source_user))
            retries = ctx.rcon_queue_retries.get(retry_key, 0) + 1
            if retries <= ctx.max_rcon_retries:
                ctx.rcon_queue_retries[retry_key] = retries
                try:
                    await ctx.rcon_queue.put((commands, source_user))
                except Exception as e:
                    log.info(f"RCON Queue Error: {e}")
            else:
                log.info(f"[RCON] Dropping commands after {retries} failed attempts: {commands}")
                ctx.rcon_queue_retries.pop(retry_key, None)
            await asyncio.sleep(wait_time)
            continue
        finally:
            ctx.rcon_queue.task_done()
            await asyncio.sleep(wait_time)

async def execute_global_command(trigger_name: str, source_user: str | dict, chain_depth: int = 0):
    """Resolves a trigger name into RCON commands and enqueues them."""
    name = sanitize_filename(trigger_name)
    
    if name not in ctx.valid_functions:
        return

    if isinstance(source_user, dict):
        comment_text = source_user.get('comment', '')
        user_display = source_user.get('user', '')
    else:
        comment_text = None
        user_display = source_user

    commands_to_send = []

    if name in ctx.script_actions:
        for action in ctx.script_actions[name]:
            if action in HOOK_ACTIONS:
                try:
                    ctx.hook_api.set_depth(chain_depth)
                    HOOK_ACTIONS[action](source_user, action, {})
                except Exception as e:
                    log.warning(f"[HOOK] Error in action '{action}': {e}")
            elif action:
                log.warning(f"[HOOK] Unknown script action: '{action}'") 

    # --- 0. OVERLAY TEXT ---

    if name in ctx.overlay_actions:
        for overlay_name, raw_body in ctx.overlay_actions[name]:
            parts = raw_body.split("|")
            title = parts[0].replace("{user}", user_display) if len(parts) > 0 else ""
            subtitle = parts[1].replace("{user}", user_display) if len(parts) > 1 else ""
            if comment_text is not None:
                title = title.replace("{comment}", comment_text)
                subtitle = subtitle.replace("{comment}", comment_text)
            try:
                duration = int(parts[2]) if len(parts) > 2 and parts[2].strip().isdigit() else 3
            except (ValueError, IndexError):
                duration = 3
            send_overlay_text(title, subtitle, duration, overlay_name)

    # --- 1. VANILLA COMMANDS ---
    if name in ctx.vanilla_functions:
        commands_to_send.append(f"execute as @a run function {ctx.namespace}:{name}")

    # --- 2. RCON-ONLY COMMANDS ---
    if name in ctx.rcon_only_actions:
        commands_to_send.extend(ctx.rcon_only_actions[name])

    if not commands_to_send:
        return

    # --- 3. ENQUEUE ---
    def _enqueue():
        try:
            ctx.rcon_queue.put_nowait((commands_to_send, source_user))
        except asyncio.QueueFull:
            log.info(f"[RCON-QUEUE FULL] Trigger {name} dropped!")
    ctx.main_loop.call_soon_threadsafe(_enqueue)
    if ctx.rcon_queue.qsize() < 10: 
        log.info(f"[ACTION] Trigger: {name} | Commands: {len(commands_to_send)} (for {source_user}) enqueued.")

# ================================
# TRIGGER WORKER
# ================================
async def trigger_worker():
    """Processes TikTok events from the trigger queue and converts them into RCON commands."""
    log.info("[TRIGGER-QUEUE] Worker started.")
    while True:
        try:
            item = await ctx.trigger_queue.get()
            if len(item) == 3:
                trigger, source_user, chain_depth = item
            else:
                trigger, source_user = item
                chain_depth = 0
            try:
                await execute_global_command(trigger, source_user, chain_depth)
            except Exception as e:
                log.info(f"[TRIGGER WORKER ERROR] Error processing {trigger}/{source_user}: {e}")
            finally:
                ctx.trigger_queue.task_done()
        except Exception as e_outer:
            log.info(f"[TRIGGER-QUEUE LOOP ERROR] {e_outer}")
            await asyncio.sleep(0.1)  

# ==========================================
# HTTP actions loader
# ==========================================

def load_shell_actions(file_path=SHELL_ACTIONS_FILE):
    """Loads all HTTP actions into memory at startup."""
    ctx.shell_actions_cache = {}
    variables = {}

    if not file_path.exists():
        log.error(f"File not found: {file_path}")
        return

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_clean = line.split("#", 1)[0].strip()
            if not line_clean:
                continue

            # Variable definition: //define varname = value
            if line_clean.startswith("//define"):
                parts = line_clean[len("//define"):].strip().split("=", 1)
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    var_value = parts[1].strip()
                    if var_name and var_value:
                        variables[var_name] = var_value
                        log.info(f"[HTTP] Defined variable '{var_name}' = '{var_value}'")
                continue

            if ":" not in line_clean:
                continue

            trigger_id, cmd = map(str.strip, line_clean.split(":", 1))
            # Resolve variables in command
            for var_name, var_value in variables.items():
                cmd = cmd.replace(f"{{{var_name}}}", var_value)
            ctx.shell_actions_cache[trigger_id] = cmd

    log.info(f"Shell actions loaded: {len(ctx.shell_actions_cache)} entries")

# ==========================================
# Webhook endpoint for MinecraftServerAPI
# ==========================================
@app.route('/webhook', methods=['POST'])
def handle_minecraft_events():
    try:
        data = request.json
    except Exception as e:
        log.error(f"Webhook invalid JSON: {e}")
        return {"status": "invalid json"}, 400

    if not data:
        return {"status": "no data"}, 400

    event = data.get("event")

    if event == "player_death":
        ctx.queue_active = False
        log.info("\n[STATUS] [DEAD] Player died! Queue PAUSED.")
    
    elif event == "player_respawn":
        ctx.queue_active = True
        log.info("\n[STATUS] [OK] Player respawned! Queue RESUMED.")

    return {"status": "processed"}, 200

def _dispatch_comment_http(url_template, username, cmd_text):
    import urllib.request
    import urllib.parse
    try:
        url = url_template.replace("{user}", urllib.parse.quote(username, safe=""))
        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
        req = urllib.request.Request(url, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        log.info(f"[COMMENT CMD] HTTP dispatch failed: {e}")


def _dispatch_comment_http_sync(url_template, username, cmd_text):
    """Sends a conditional HTTP command and returns the JSON response.
    Returns None on failure."""
    import urllib.request
    import urllib.parse
    import json
    try:
        url = url_template.replace("{user}", urllib.parse.quote(username, safe=""))
        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.info(f"[COMMENT CMD] Conditional HTTP dispatch failed: {e}")
        return None


def _ping_channel_points(user):
    """Pings the channel points plugin to mark a user as active."""
    if not ctx.config.get("channel_points", {}).get("enabled", False):
        return
    port = ctx.config.get("channel_points", {}).get("port", 29195)
    import urllib.request
    import json
    try:
        url = f"http://127.0.0.1:{port}/ping"
        data = json.dumps({"user": user}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=2)
    except Exception as e:
        log.info(f"[CHANNEL POINTS] Ping failed for {user}: {e}")


def _process_follow(username: str, persist: bool = True):
    """Shared follow dedup: cache check, persist (optional), enqueue trigger once per user."""
    user_lower = username.lower()
    if user_lower in ctx._followed_cache:
        log.info(f"[FOLLOW] {username} already tracked — follow trigger skipped")
        return
    ctx._followed_cache.add(user_lower)
    if persist:
        try:
            with open(ctx.follow_tracking_file, "a") as f:
                f.write(user_lower + "\n")
        except Exception as e:
            log.info(f"[FOLLOW] Could not write to {ctx.follow_tracking_file}: {e}")
    if "follow" in ctx.valid_functions:
        ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("follow", username))


def _get_channel_points_port():
    return ctx.config.get("channel_points", {}).get("port", 29195)


def _get_user_points(user):
    """Returns the point balance for a user, or 0 on error."""
    port = _get_channel_points_port()
    import urllib.request
    import urllib.parse
    import json
    try:
        url = f"http://127.0.0.1:{port}/points?user={urllib.parse.quote(user)}"
        resp = urllib.request.urlopen(url, timeout=3)
        data = json.loads(resp.read())
        return data.get("points", 0)
    except Exception as e:
        log.info(f"[CHANNEL POINTS] Failed to get points for {user}: {e}")
        return 0


def _deduct_user_points(user, amount):
    """Deducts points from a user. Returns True on success."""
    port = _get_channel_points_port()
    import urllib.request
    import json
    try:
        url = f"http://127.0.0.1:{port}/spend"
        data = json.dumps({"user": user, "amount": amount}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=3)
        return json.loads(resp.read()).get("success", False)
    except Exception as e:
        log.info(f"[CHANNEL POINTS] Failed to deduct points for {user}: {e}")
        return False


# ==========================================
# Custom trigger + test comment endpoints
# ==========================================
@app.route('/test_comment', methods=['POST'])
def handle_test_comment():
    try:
        data = request.json
        if not data:
            return {"status": "error", "message": "No JSON body provided."}, 400
        username = str(data.get("user", "TestUser")).strip() or "TestUser"
        comment_text = str(data.get("text", "")).strip()
        if not comment_text:
            return {"status": "error", "message": "Field 'text' is required."}, 400
        is_moderator = bool(data.get("moderator", False))
        is_super_fan = bool(data.get("superfan", False))
        in_fanclub = bool(data.get("fanclub", False))

        log.info(f"[TEST COMMENT] {username}: {comment_text}")
        log.info(f"  Moderator: {is_moderator}, Superfan: {is_super_fan}, Fanclub: {in_fanclub}")

        if ctx.comment_cmd_all_prefixes:
            matched_prefix = None
            for p in ctx.comment_cmd_all_prefixes:
                if comment_text.startswith(p):
                    matched_prefix = p
                    break
            if matched_prefix:
                cmd_part = comment_text[len(matched_prefix):].strip()
                if cmd_part:
                    group_enabled = any(g["prefix"] == matched_prefix for g in ctx.comment_cmd_groups)
                    if not ctx.comment_cmd_enable:
                        log.info(f"[TEST COMMENT] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but comment_commands is disabled globally")
                    elif not group_enabled:
                        log.info(f"[TEST COMMENT] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but that command group is disabled")

        if ctx.comment_cmd_enable and ctx.comment_cmd_groups:
            now = time.time()
            gcd = ctx.comment_cmd_global_cooldown
            if gcd > 0 and now - ctx.comment_cmd_global_last < gcd:
                remaining = gcd - (now - ctx.comment_cmd_global_last)
                log.info(f"[TEST COMMENT] {username} blocked by global cooldown ({remaining:.1f}s left)")
                return {"status": "ok", "message": "Blocked by global cooldown"}
            gucd = ctx.comment_cmd_global_user_cooldown
            if gucd > 0:
                last_user = ctx.comment_cmd_global_user_last.get(username, 0)
                if now - last_user < gucd:
                    remaining = gucd - (now - last_user)
                    log.info(f"[TEST COMMENT] {username} blocked by global user cooldown ({remaining:.1f}s left)")
                    return {"status": "ok", "message": "Blocked by global user cooldown"}
            for group in ctx.comment_cmd_groups:
                prefix = group["prefix"]
                if not prefix or not comment_text.startswith(prefix):
                    continue
                cmd_text = comment_text[len(prefix):].strip()
                if not cmd_text:
                    continue

                allowed = False
                if "all" in group["roles"]:
                    allowed = True
                elif "moderator" in group["roles"] and is_moderator:
                    allowed = True
                elif "superfan" in group["roles"] and is_super_fan:
                    allowed = True
                elif "fanclub" in group["roles"] and in_fanclub:
                    allowed = True

                if not allowed:
                    log.info(f"[TEST COMMENT] {username} no permission for prefix '{prefix}' (roles: {group['roles']})")
                    continue

                base_cmd = cmd_text.split()[0].lower()
                if group["mode"] == "deny-all":
                    if base_cmd not in group["commands"]:
                        log.info(f"[TEST COMMENT] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' not allowed (deny-all)")
                        continue
                else:
                    if base_cmd in group["commands"]:
                        log.info(f"[TEST COMMENT] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' blocked (allow-all)")
                        continue

                ccfg = group.get("commands_config", {}).get(base_cmd, {})

                # Per-command role override
                cmd_roles = ccfg.get("roles")
                if cmd_roles:
                    cmd_allowed = False
                    if "all" in cmd_roles:
                        cmd_allowed = True
                    elif "moderator" in cmd_roles and is_moderator:
                        cmd_allowed = True
                    elif "superfan" in cmd_roles and is_super_fan:
                        cmd_allowed = True
                    elif "fanclub" in cmd_roles and in_fanclub:
                        cmd_allowed = True
                    if not cmd_allowed:
                        log.info(f"[TEST COMMENT] {username} no permission for '{base_cmd}' (per-command roles: {cmd_roles})")
                        continue

                cd = ccfg.get("cooldown", group["cooldown"])
                ucd = ccfg.get("user_cooldown", group["user_cooldown"])
                if cd > 0:
                    last = ctx.comment_cmd_last_global.get(prefix, 0)
                    if now - last < cd:
                        remaining = cd - (now - last)
                        log.info(f"[TEST COMMENT] {username} blocked by global cooldown ({remaining:.1f}s left)")
                        continue
                if ucd > 0:
                    last_user = ctx.comment_cmd_last_user.setdefault(prefix, {}).get(username, 0)
                    if now - last_user < ucd:
                        remaining = ucd - (now - last_user)
                        log.info(f"[TEST COMMENT] {username} blocked by user cooldown ({remaining:.1f}s left)")
                        continue

                # Points check & deduction
                points_cost = ccfg.get("points_cost", 0)
                conditional = ccfg.get("conditional", False)

                if points_cost > 0:
                    balance = _get_user_points(username)
                    if balance < points_cost:
                        log.info(f"[TEST COMMENT] {username} → not enough points for '{base_cmd}' (has {balance}, needs {points_cost})")
                        continue
                    if not conditional:
                        if not _deduct_user_points(username, points_cost):
                            log.info(f"[TEST COMMENT] {username} points deduction failed for '{base_cmd}'")
                            continue
                        log.info(f"[TEST COMMENT] {username} spent {points_cost} points on '{base_cmd}'")

                cmd_url = ccfg.get("url", group["url"])
                cmd_handler = ccfg.get("handler", group["handler"])
                log.info(f"[TEST COMMENT] {username} -> {cmd_text} (prefix '{prefix}', handler {cmd_handler})")

                if not conditional:
                    ctx.comment_cmd_last_global[prefix] = now
                    ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now
                    ctx.comment_cmd_global_last = now
                    ctx.comment_cmd_global_user_last[username] = now

                if cmd_handler == "rcon":
                    ctx.main_loop.call_soon_threadsafe(ctx.rcon_queue.put_nowait, ([cmd_text], username))
                elif cmd_handler == "http" and cmd_url:
                    if conditional:
                        resp_data = _dispatch_comment_http_sync(cmd_url, username, cmd_text)
                        if resp_data and resp_data.get("found", False):
                            ctx.comment_cmd_last_global[prefix] = now
                            ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now
                            ctx.comment_cmd_global_last = now
                            ctx.comment_cmd_global_user_last[username] = now
                            if points_cost > 0:
                                if _deduct_user_points(username, points_cost):
                                    log.info(f"[TEST COMMENT] {username} spent {points_cost} points on '{base_cmd}'")
                                else:
                                    log.info(f"[TEST COMMENT] {username} points deduction failed for '{base_cmd}'")
                            mode_label = resp_data.get("mode", "replace")
                            if mode_label == "queue":
                                log.info(f"[TEST COMMENT] {username} → '{base_cmd}' successful — song added to queue")
                            else:
                                log.info(f"[TEST COMMENT] {username} → '{base_cmd}' successful — song found and played")
                        else:
                            log.info(f"[TEST COMMENT] {username} → '{base_cmd}' song not found — no points deducted, no cooldown triggered")
                    else:
                        import urllib.request, urllib.parse
                        url = cmd_url.replace("{user}", urllib.parse.quote(username, safe=""))
                        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
                        threading.Thread(
                            target=_dispatch_comment_http,
                            args=(url, username, cmd_text),
                            daemon=True
                        ).start()

        return {"status": "ok", "message": f"Comment '{comment_text}' from '{username}' processed."}

    except Exception as e:
        log.info(f"[TEST COMMENT] Error: {e}")
        return {"status": "error", "message": str(e)}, 500


# ==========================================
# Webhook endpoint for custom trigger injection (test/simulation)
# ==========================================
@app.route('/custom_trigger', methods=['POST'])
def handle_custom_trigger():
    try:
        data = request.json
        if not data:
            return {"status": "error", "message": "No JSON body provided."}, 400

        trigger = data.get("trigger", "")
        user = data.get("user", "System").strip() or "System"

        if isinstance(trigger, int):
            sanitized = str(trigger)
        elif isinstance(trigger, str):
            trigger = trigger.strip()
            if not trigger:
                return {"status": "error", "message": "Field 'trigger' is required and must not be empty."}, 400
            sanitized = sanitize_filename(trigger)
            if not sanitized:
                return {"status": "error", "message": f"Trigger '{trigger}' contains no valid characters after sanitizing."}, 400
        else:
            return {"status": "error", "message": "Field 'trigger' must be string or int."}, 400

        # Special toggle: if trigger is 'tiktok', toggle TikTok connection
        if sanitized == "tiktok":
            with ctx.tiktok_lock:
                ctx.disable_tiktok_connect = not ctx.disable_tiktok_connect
                new_state = ctx.disable_tiktok_connect
            log.info(f"[CUSTOM TRIGGER] TikTok connect toggled: {not new_state} -> {new_state}")
            return {"status": "ok", "message": f"TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT={new_state}"}, 200

        # Route 'follow' through the shared dedup logic so custom_trigger respects _followed_cache
        # persist=False damit Test-User nicht in followed_users.txt landen
        if sanitized == "follow":
            _process_follow(user, persist=False)
            return {"status": "ok", "trigger": sanitized, "user": user}, 200

        if ctx.main_loop is None:
            return {"status": "error", "message": "Bot event loop not ready yet."}, 503

        if sanitized in ctx.valid_functions:
            try:
                ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, (sanitized, user))
            except asyncio.QueueFull:
                return {"status": "error", "message": "Trigger queue is full. Try again later."}, 503
            log.info(f"[CUSTOM TRIGGER] Injected: '{sanitized}' (user: {user})")
            return {"status": "ok", "trigger": sanitized, "user": user}, 200

        raw_trigger = str(data.get("trigger", "")).strip()
        cmd = ctx.shell_actions_cache.get(raw_trigger) or ctx.shell_actions_cache.get(sanitized)
        if cmd:
            try:
                asyncio.run_coroutine_threadsafe(execute_http_command(cmd), ctx.main_loop)
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500
            log.info(f"[CUSTOM TRIGGER] HTTP action for '{raw_trigger}' executed")
            return {"status": "ok", "trigger": raw_trigger, "user": user}, 200

        return {"status": "error", "message": f"Trigger '{sanitized}' does not exist or is not valid."}, 400

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
# =========================================

# --- Start webhook server in its own thread ---
def run_signal_server():
    app.run(host=ctx.server_host, port=ctx.mcserver_api_port, threaded=True, debug=False, use_reloader=False)

# ==========================================
# HTTP command executor
# ==========================================

def execute_http_command_sync(cmd: str):
    try:
        args = shlex.split(cmd)
        subprocess.run(args, check=True)
        log.info(f"Success: {cmd}")
    except subprocess.CalledProcessError as e:
        log.info(f"[FAIL] Error: {cmd} ({e})")

async def execute_http_command(cmd: str):
    await asyncio.to_thread(execute_http_command_sync, cmd)

def execute_gift_action(gift_id: str):
    """Executes an HTTP action for a gift asynchronously."""
    cmd = ctx.shell_actions_cache.get(gift_id)
    if not cmd:
        return

    try:
        asyncio.run_coroutine_threadsafe(execute_http_command(cmd), ctx.main_loop)
        log.info(f"[HTTP] Action for gift {gift_id} started")
    except Exception as e:
        log.info(f"[HTTP ERROR] {e}")
        traceback.print_exc()

# ==========================================
# User-friendly name extraction
# =========================================
def get_safe_username(user):
    name = getattr(user, 'unique_id', None) or getattr(user, 'nickname', None) or "Unknown"
    return name

# =========================================
# Likegoal worker (forwards like counts)
# =========================================
async def likegoal_worker():
    timeout = aiohttp.ClientTimeout(total=2)
    log.info("[LIKEGOAL-QUEUE] Worker started.")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            delta_val = await ctx.likegoal_queue.get()
            try:
                url = f"http://127.0.0.1:{ctx.like_goal_port}/update_likes?add={delta_val}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        pass
            except Exception as e:
                log.info(f"[LIKEGOAL ERROR] {e}")
            finally:
                ctx.likegoal_queue.task_done()

# =========================================
# Like trigger validation
# =========================================

def validate_like_triggers(raw_triggers):
    """
    Validates and normalizes like_triggers from the config.

    Rules:
    - id: required, non-empty string
    - every: required, int > 0 (accepts "100_000")
    - function: required, string
    - payload: optional, default "Community"
    - enable: optional, default True (cast to bool)
    """

    valid_triggers = []
    seen_ids = set()

    for i, rule in enumerate(raw_triggers):
        if not isinstance(rule, dict):
            log.info(f"[CONFIG ERROR] Entry #{i} is not an object: {rule}")
            continue

        # --- ID ---
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            log.info(f"[CONFIG ERROR] Invalid or missing 'id': {rule}")
            continue

        if rule_id in seen_ids:
            log.info(f"[CONFIG ERROR] Duplicate id '{rule_id}'")
            continue
        seen_ids.add(rule_id)

        # --- EVERY (trigger interval) ---
        raw_every = rule.get("every")
        if raw_every is None:
            log.info(f"[CONFIG ERROR] 'every' missing for {rule_id}")
            continue

        try:
            if isinstance(raw_every, str):
                raw_every = raw_every.replace("_", "")
            every = int(raw_every)

            if every <= 0:
                raise ValueError()

        except Exception:
            log.info(f"[CONFIG ERROR] Invalid 'every' value for {rule_id}: {raw_every}")
            continue

        # --- FUNCTION (action to execute) ---
        function_name = rule.get("function")
        if not isinstance(function_name, str) or not function_name.strip():
            log.info(f"[CONFIG ERROR] Invalid or missing 'function' for {rule_id}")
            continue

        # --- PAYLOAD (user label, optional) ---
        payload = rule.get("payload", "Community")
        if not isinstance(payload, str):
            log.info(f"[CONFIG ERROR] 'payload' must be a string for {rule_id}")
            continue

        # --- ENABLE (on/off toggle, optional) ---
        enable = rule.get("enabled", True)

        # Cast to bool (handles strings like "true", "false")
        if isinstance(enable, str):
            enable = enable.lower() in ("true", "1", "yes", "on")

        enable = bool(enable)

        # --- Final cleaned rule ---
        clean_rule = {
            "id": rule_id,
            "every": every,
            "function": function_name,
            "payload": payload,
            "enable": enable,
        }

        valid_triggers.append(clean_rule)

    return valid_triggers

def prepare_like_triggers(raw_triggers):
    prepared = []

    for rule in raw_triggers:
        if not rule["enable"]:
            continue

        if rule["function"] not in ctx.valid_functions:
            log.info(f"[CONFIG ERROR] Unknown function: {rule['function']}")
            continue

        prepared.append({
            "id": rule["id"],
            "every": rule["every"],
            "function": rule["function"],
            "payload": rule["payload"],
            "last_blocks": 0
        })

    return prepared

# =========================================
# Daily revenue logger
# =========================================

def update_daily_revenue():
    file_path = BASE_DIR.parent / "data" / "revenue_log.jsonl"
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    with ctx.gift_lock:
        if ctx.gift_current_log_date != today:
            ctx.gift_day_start_value = ctx.gift_value_usd
            ctx.gift_current_log_date = today
        daily_value = ctx.gift_value_usd - ctx.gift_day_start_value

        new_entry = {
            "date": today,
            "estimated_revenue_usd": round(daily_value, 2)
        }
        entries = []
        if file_path.exists():
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        updated = False
        for i, entry in enumerate(entries):
            if entry.get("date") == today:
                entries[i] = new_entry
                updated = True
                break
        if not updated:
            entries.append(new_entry)
        with file_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ==========================================
# TIKTOK CLIENT
# ==========================================

def create_client(user):
    client = TikTokLiveClient(unique_id=user)

    _connect_time = [None]
    COMMENT_WARMUP_SECONDS = 1

    # =========================
    # GIFT events
    # =========================
    @client.on(GiftEvent)
    def on_gift(event: GiftEvent):
        try:
            if event.gift.combo:
                if getattr(event, 'streaking', False):
                    return

                count = event.repeat_count
            else:
                count = 1

            gift_name = sanitize_filename(event.gift.name)
            gift_id = str(event.gift.id)

            with ctx.gift_lock:
                ctx.gift_value_usd += event.value

            execute_gift_action(gift_id)

            username = get_safe_username(event.user)
            _ping_channel_points(username)

            target = None
            if gift_name in ctx.valid_functions:
                target = gift_name
            elif gift_id in ctx.valid_functions:
                target = gift_id

            if not target:
                return

            for _ in range(count):
                ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, (target, username))

        except Exception:
            log.error("\n" + "!"*30)
            log.error("ERROR IN ON_GIFT EVENT:")
            traceback.print_exc()
            log.error("!"*30 + "\n")

    # =========================
    # FOLLOW events
    # =========================
    @client.on(FollowEvent)
    def on_follow(event: FollowEvent):
        username = get_safe_username(event.user)
        _ping_channel_points(username)
        _process_follow(username)

    # =========================
    # LIKE events
    # =========================
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        username = get_safe_username(event.user) if hasattr(event, 'user') else None
        if username:
            _ping_channel_points(username)
        with ctx.like_lock:
            if ctx.start_likes is None:
                ctx.start_likes = event.total
                log.info(f"[LIKE] Initial count set: {ctx.start_likes}")
                return
            total_since_start = event.total - ctx.start_likes
        try:
            with ctx.like_lock:
                for rule in ctx.like_triggers:
                    every = rule["every"]
                    if every <= 0: continue
                    current_blocks = total_since_start // every
                    last_blocks = rule["last_blocks"]
                    if current_blocks > last_blocks:
                        diff = current_blocks - last_blocks
                        rule["last_blocks"] = current_blocks
                        log.info(f"[LIKE] Trigger '{rule['id']}' -> +{diff}")
                        for _ in range(diff):
                            ctx.main_loop.call_soon_threadsafe(
                                ctx.trigger_queue.put_nowait,
                                (rule["function"], rule["payload"])
                            )
            now = time.time()
            delta = total_since_start - ctx.last_likegoal_sent
            if delta > 0 and (now - ctx.last_likegoal_time) >= ctx.likegoal_interval:
                try:
                    ctx.main_loop.call_soon_threadsafe(ctx.likegoal_queue.put_nowait, delta)
                    ctx.last_likegoal_sent = total_since_start
                    ctx.last_likegoal_time = now
                except asyncio.QueueFull:
                    log.info("[LIKEGOAL] Queue full, like delta dropped")
        except Exception as e:
            log.info(f"[EVENT ERROR] Error in like handling: {e}")

    # ========================
    # Join events
    # ========================
    @client.on(JoinEvent)
    def on_join(event):
        username = get_safe_username(event.user)
        _ping_channel_points(username)
        if "join" in ctx.valid_functions:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("join", username))

    # =========================
    # COMMENT events
    # =========================
    @client.on(CommentEvent)
    def on_comment(event):
        if _connect_time[0] is None or (time.time() - _connect_time[0]) < COMMENT_WARMUP_SECONDS:
            return

        username = get_safe_username(event.user)
        _ping_channel_points(username)
        comment_text = getattr(event, 'comment', '')

        is_super_fan = getattr(event, 'user_is_super_fan', None)

        in_fanclub = False
        fan_ticket_count = getattr(event.user, 'fan_ticket_count', None)
        fans_club = getattr(event.user, 'fans_club', None)
        fans_club_info = getattr(event.user, 'fans_club_info', None)
        if fan_ticket_count and fan_ticket_count > 0:
            in_fanclub = True
        elif hasattr(fans_club, 'club_name') or hasattr(fans_club_info, 'club_name'):
            in_fanclub = True

        is_moderator = getattr(event.user, 'is_moderator', None)

        log.info(f"[COMMENT] {username}: {comment_text}")
        log.info(f"  Superfan: {is_super_fan}")
        log.info(f"  Fanclub-Mitglied: {in_fanclub}")
        log.info(f"  Moderator: {is_moderator}")

        if ctx.comment_cmd_all_prefixes:
            matched_prefix = None
            for p in ctx.comment_cmd_all_prefixes:
                if comment_text.startswith(p):
                    matched_prefix = p
                    break
            if matched_prefix:
                cmd_part = comment_text[len(matched_prefix):].strip()
                if cmd_part:
                    group_enabled = any(g["prefix"] == matched_prefix for g in ctx.comment_cmd_groups)
                    if not ctx.comment_cmd_enable:
                        log.info(f"[COMMENT CMD] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but comment_commands is disabled globally")
                    elif not group_enabled:
                        log.info(f"[COMMENT CMD] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but that command group is disabled")

        suppress_comment_trigger = False
        if ctx.comment_cmd_enable and ctx.comment_cmd_groups:
            now = time.time()
            gcd = ctx.comment_cmd_global_cooldown
            if gcd > 0 and now - ctx.comment_cmd_global_last < gcd:
                remaining = gcd - (now - ctx.comment_cmd_global_last)
                log.info(f"[COMMENT CMD] {username} blocked by global cooldown ({remaining:.1f}s left)")
                return
            gucd = ctx.comment_cmd_global_user_cooldown
            if gucd > 0:
                last_user = ctx.comment_cmd_global_user_last.get(username, 0)
                if now - last_user < gucd:
                    remaining = gucd - (now - last_user)
                    log.info(f"[COMMENT CMD] {username} blocked by global user cooldown ({remaining:.1f}s left)")
                    return
            for group in ctx.comment_cmd_groups:
                prefix = group["prefix"]
                if not prefix or not comment_text.startswith(prefix):
                    continue
                cmd_text = comment_text[len(prefix):].strip()
                if not cmd_text:
                    continue

                allowed = False
                if "all" in group["roles"]:
                    allowed = True
                elif "moderator" in group["roles"] and is_moderator:
                    allowed = True
                elif "superfan" in group["roles"] and is_super_fan:
                    allowed = True
                elif "fanclub" in group["roles"] and in_fanclub:
                    allowed = True

                if not allowed:
                    log.info(f"[COMMENT CMD] {username} no permission for prefix '{prefix}' (roles: {group['roles']})")
                    if not group.get("trigger_comment_event", True):
                        suppress_comment_trigger = True
                    continue

                base_cmd = cmd_text.split()[0].lower()
                if group["mode"] == "deny-all":
                    if base_cmd not in group["commands"]:
                        log.info(f"[COMMENT CMD] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' not allowed (deny-all)")
                        if not group.get("trigger_comment_event", True):
                            suppress_comment_trigger = True
                        continue
                else:
                    if base_cmd in group["commands"]:
                        log.info(f"[COMMENT CMD] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' blocked (allow-all)")
                        if not group.get("trigger_comment_event", True):
                            suppress_comment_trigger = True
                        continue

                ccfg = group.get("commands_config", {}).get(base_cmd, {})

                # Per-command role override
                cmd_roles = ccfg.get("roles")
                if cmd_roles:
                    cmd_allowed = False
                    if "all" in cmd_roles:
                        cmd_allowed = True
                    elif "moderator" in cmd_roles and is_moderator:
                        cmd_allowed = True
                    elif "superfan" in cmd_roles and is_super_fan:
                        cmd_allowed = True
                    elif "fanclub" in cmd_roles and in_fanclub:
                        cmd_allowed = True
                    if not cmd_allowed:
                        log.info(f"[COMMENT CMD] {username} no permission for '{base_cmd}' (per-command roles: {cmd_roles})")
                        if not group.get("trigger_comment_event", True):
                            suppress_comment_trigger = True
                        continue

                cd = ccfg.get("cooldown", group["cooldown"])
                ucd = ccfg.get("user_cooldown", group["user_cooldown"])
                if cd > 0:
                    last = ctx.comment_cmd_last_global.get(prefix, 0)
                    if now - last < cd:
                        remaining = cd - (now - last)
                        log.info(f"[COMMENT CMD] {username} blocked by global cooldown ({remaining:.1f}s left)")
                        if not group.get("trigger_comment_event", True):
                            suppress_comment_trigger = True
                        continue
                if ucd > 0:
                    last_user = ctx.comment_cmd_last_user.setdefault(prefix, {}).get(username, 0)
                    if now - last_user < ucd:
                        remaining = ucd - (now - last_user)
                        log.info(f"[COMMENT CMD] {username} blocked by user cooldown ({remaining:.1f}s left)")
                        if not group.get("trigger_comment_event", True):
                            suppress_comment_trigger = True
                        continue

                # Points check & deduction
                points_cost = ccfg.get("points_cost", 0)
                conditional = ccfg.get("conditional", False)

                if points_cost > 0:
                    balance = _get_user_points(username)
                    if balance < points_cost:
                        log.info(f"[COMMENT CMD] {username} → not enough points for '{base_cmd}' (has {balance}, needs {points_cost})")
                        if not group.get("trigger_comment_event", True):
                            suppress_comment_trigger = True
                        continue
                    if not conditional:
                        if not _deduct_user_points(username, points_cost):
                            log.info(f"[COMMENT CMD] {username} points deduction failed for '{base_cmd}'")
                            if not group.get("trigger_comment_event", True):
                                suppress_comment_trigger = True
                            continue
                        log.info(f"[COMMENT CMD] {username} spent {points_cost} points on '{base_cmd}'")

                cmd_url = ccfg.get("url", group["url"])
                cmd_handler = ccfg.get("handler", group["handler"])
                log.info(f"[COMMENT CMD] {username} -> {cmd_text} (prefix '{prefix}', handler {cmd_handler})")

                if not conditional:
                    ctx.comment_cmd_last_global[prefix] = now
                    ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now
                    ctx.comment_cmd_global_last = now
                    ctx.comment_cmd_global_user_last[username] = now

                if cmd_handler == "rcon":
                    ctx.main_loop.call_soon_threadsafe(ctx.rcon_queue.put_nowait, ([cmd_text], username))
                elif cmd_handler == "http" and cmd_url:
                    if conditional:
                        resp_data = _dispatch_comment_http_sync(cmd_url, username, cmd_text)
                        if resp_data and resp_data.get("found", False):
                            ctx.comment_cmd_last_global[prefix] = now
                            ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now
                            ctx.comment_cmd_global_last = now
                            ctx.comment_cmd_global_user_last[username] = now
                            if points_cost > 0:
                                if _deduct_user_points(username, points_cost):
                                    log.info(f"[COMMENT CMD] {username} spent {points_cost} points on '{base_cmd}'")
                                else:
                                    log.info(f"[COMMENT CMD] {username} points deduction failed for '{base_cmd}'")
                            mode_label = resp_data.get("mode", "replace")
                            if mode_label == "queue":
                                log.info(f"[COMMENT CMD] {username} → '{base_cmd}' successful — song added to queue")
                            else:
                                log.info(f"[COMMENT CMD] {username} → '{base_cmd}' successful — song found and played")
                        else:
                            log.info(f"[COMMENT CMD] {username} → '{base_cmd}' song not found — no points deducted, no cooldown triggered")
                    else:
                        threading.Thread(
                            target=_dispatch_comment_http,
                            args=(cmd_url, username, cmd_text),
                            daemon=True
                        ).start()

                if not group.get("trigger_comment_event", True):
                    suppress_comment_trigger = True

        if "comment" in ctx.valid_functions and not suppress_comment_trigger:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("comment", {"user": username, "comment": comment_text}))

    # =========================
    # Share events
    # =========================
    @client.on(ShareEvent)
    def on_share(event):
        username = get_safe_username(event.user)
        _ping_channel_points(username)
        if "share" in ctx.valid_functions:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("share", username))

    # =========================
    # Live end events
    # =========================
    @client.on(LiveEndEvent)
    def on_live_end(_):
        update_daily_revenue()
        log.info(f"Live ended for @{user}.")
        ctx.runtime_path_shutdown.touch(exist_ok=True)

    # =========================
    # CONNECT event
    # =========================
    @client.on(ConnectEvent)
    def on_connect(_):
        _connect_time[0] = time.time()
        log.info(f"Live connection established: @{user}")

    return client

# ========================
# Counter for gift revenue estimation
# ========================
async def gift_revenue_counter():
    while True:
        await asyncio.sleep(ctx.autosave_interval_seconds)
        update_daily_revenue()

# ==========================================
# MAIN ENTRY POINT
# ==========================================

async def run_bot():
    """Main async loop: initializes config, builds the datapack,
    starts all workers, and connects to TikTok Live."""
    ctx.main_loop = asyncio.get_running_loop()
    
    if not load_config():
        log.info("Error in load_config")
        sys.exit(1)

    # TikTok username check: ask user if still default
    default_user = "your_tiktok_username"
    if ctx.tiktok_user == default_user:
        log.info(f"\n[TIKTOK] Your TikTok username is still the default '{default_user}'.")
        inp = input("  Enter your TikTok username (press Enter to keep the default): ").strip()
        if inp:
            ctx.tiktok_user = inp
            log.info(f"[TIKTOK] Username set to @{ctx.tiktok_user} (session only).")
        else:
            log.info(f"[TIKTOK] No input - using default '{default_user}'.")

    try:
        diags = validate_file(ACTIONS_FILE, raise_on_error=False)
        if diags:
            log.info("[VALIDATOR] Validation result for actions.mca:")
            print_diagnostics(diags)
        if any(d.severity.name == "ERROR" for d in diags):
            log.info("[STOP] Errors found. Please fix actions.mca and restart.")
            if sys.stdin.isatty():
                try:
                    input("Press Enter to exit...\n\n\n")
                except (EOFError, OSError):
                    pass
            return
    except FileNotFoundError as e:
        log.error(f"{e}")
        return

    generate_datapack()
    ctx.like_triggers = prepare_like_triggers(ctx.like_triggers)
    load_shell_actions()

    EVENT_HOOKS_DIR = (BASE_DIR / ".." / "event_hooks").resolve()
    ctx.hook_api = HookAPI(ctx.rcon_queue, ctx.trigger_queue, ctx.main_loop, ctx.config, ctx.valid_functions)
    load_event_hooks(ctx.hook_api, EVENT_HOOKS_DIR)

    threading.Thread(target=run_signal_server, daemon=True).start()

    asyncio.create_task(trigger_worker())
    asyncio.create_task(rcon_worker())
    asyncio.create_task(likegoal_worker())
    asyncio.create_task(gift_revenue_counter())

    while True:
        with ctx.tiktok_lock:
            _disabled = ctx.disable_tiktok_connect
        if _disabled:
            await asyncio.sleep(ctx.reconnect_delay)
            continue

        client = create_client(ctx.tiktok_user)

        try:
            log.info(f"[*] Connecting to @{ctx.tiktok_user}...")
            await asyncio.to_thread(client.run)

        except Exception as e:
            log.info("\n" + "="*50)
            log.info("CRITICAL ERROR IN TIKTOK CLIENT:")
            traceback.print_exc() 
            log.info("="*50 + "\n")

            error_str = str(e)
            log.info(f"[..] Connection lost: {error_str}")

            _RE_ERR_CODE_200 = re.compile(r"\berr_code\b.*?\b200\b", re.IGNORECASE)
            if "DEVICE_BLOCKED" in error_str or bool(_RE_ERR_CODE_200.search(error_str)):
                log.info("[FAIL] TikTok block active (DEVICE_BLOCKED).")
                log.info("[TIP] Wait 15 minutes or restart your router.")
                await asyncio.sleep(900)
            else:
                log.info(f"[..] Reconnect in {ctx.reconnect_delay}s...")
                await asyncio.sleep(ctx.reconnect_delay)

        finally:
            try:
                client.stop()
            except Exception as e:
                log.info(f"[TIKTOK] Error stopping client: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("\n[STOP] Script stopped manually.")