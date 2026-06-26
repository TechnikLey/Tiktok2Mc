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
import os
import asyncio
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
import urllib.parse
import urllib.request
from pathlib import Path
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, FollowEvent, ConnectEvent, LikeEvent, CommentEvent, JoinEvent, ShareEvent, LiveEndEvent
from mcrcon import MCRcon
from flask import Flask, request
from core.validator import validate_file, print_diagnostics, Severity
from core.paths import get_base_dir, get_runtime_dir
from core.hook_api import HookAPI, HOOK_ACTIONS
from core.hook_loader import load_event_hooks
from core.overlay_utils import send_overlay_text
from core.yaml_utils import load_yaml
from core.api.eventbus import event_bus
from core.api.plugin_overlay import command_queue
from core.plugin_config import discover_plugins_dir, load_plugin_manifest
from core.logger import initialize_logging, install_global_exception_hook, start_heartbeat, handle_unhandled_exception

log = initialize_logging(__name__)

# ==========================================
# CONFIGURATION & PATHS
# ==========================================

BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR.parent / "config" / "config.yaml").resolve()
ACTIONS_FILE = (BASE_DIR.parent / "data" / "actions.mca").resolve()
FOLLOWED_USERS_FILE = (BASE_DIR.parent / "data" / "followed_users.txt").resolve()
RUNTIME_DIR = get_runtime_dir()
RELOAD_CONFIG_SIGNAL = (RUNTIME_DIR / "reload_config").resolve()
RELOAD_ACTIONS_SIGNAL = (RUNTIME_DIR / "reload_actions").resolve()

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
        self.mcserver_api_port = 29188
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
        self.comment_handler_map: dict[str, str] = {}  # prefix → plugin_name
        self.comment_cmd_global_cooldown = 0
        self.comment_cmd_global_last = 0.0
        self.comment_cmd_global_user_cooldown = 0
        self.comment_cmd_global_user_last = {}
        self.comment_cmd_last_global = {}
        self.comment_cmd_last_user = {}

        # Queues
        self.trigger_queue = asyncio.Queue(maxsize=10_000)
        self.rcon_queue = asyncio.Queue(maxsize=10_000)

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
        self.follow_lock = threading.Lock()
        self.comment_cmd_lock = threading.Lock()
        self.rcon_pool_lock = asyncio.Lock()

        # RCON state
        self.rcon_connection = None
        self.last_rcon_attempt = 0
        self.rcon_enabled = False

        # TikTok state
        self.disable_tiktok_connect = False
        self.tiktok_client = None

        # Event bridge subscriptions (reloaded at runtime)
        self.event_subscriptions = {}

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

_RE_ERR_CODE_200 = re.compile(r"\berr_code\b.*?\b200\b", re.IGNORECASE)

# ==========================================
# SETUP & HELPER FUNCTIONS
# ==========================================

def _validate_dup_cmd_config():
    """Validate raw YAML for duplicate keys in commands_config sections.

    Raises ``ValueError`` if duplicates are found so callers can decide
    whether to exit the process or simply abort a runtime reload.
    """
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
        raise ValueError("Duplicate keys detected in commands_config sections")


def _check_dup_cmd_config():
    """Startup check: abort the process if duplicate command keys exist."""
    try:
        _validate_dup_cmd_config()
    except ValueError as exc:
        log.error(str(exc))
        if sys.stdin.isatty():
            try:
                input("Press Enter to exit...")
            except (EOFError, OSError):
                pass
        sys.exit(1)


def _apply_config(config: dict) -> None:
    """Apply a loaded config dict to the bridge context."""
    ctx.config = config

    ctx.mc_host = config.get("server_host", "127.0.0.1")
    ctx.mc_pass = config.get("rcon", {}).get("password", "")
    ctx.mc_port = config.get("rcon", {}).get("port", 25575)
    ctx.rcon_enabled = bool(config.get("rcon", {}).get("enabled", False))
    ctx.server_host = config.get("server_host", "127.0.0.1")
    ctx.tiktok_user = config.get("tiktok", {}).get("user", "")
    ctx.reconnect_delay = config.get("tiktok", {}).get("reconnect_delay_seconds", 10)
    ctx.mcserver_api_port = int(
        os.environ.get(
            "RESOLVED_PORT_WEBHOOK_PORT",
            config.get("minecraft_server_api", {}).get("web_server_port", 29188),
        )
    )
    ctx.autosave_interval_seconds = config.get("tiktok", {}).get("autosave_interval_seconds", 60)

    ft_cfg = config.get("tiktok", {}).get("follow_tracking", {})
    ctx.follow_tracking_mode = str(ft_cfg.get("mode", "all_time")).lower()
    raw_path = str(ft_cfg.get("file", "data/followed_users.txt"))
    ctx.follow_tracking_file = (BASE_DIR.parent / raw_path).resolve()
    ctx._followed_cache = set()
    if ctx.follow_tracking_file.exists():
        with open(ctx.follow_tracking_file, "r", encoding="utf-8") as f:
            ctx._followed_cache = set(line.strip().lower() for line in f if line.strip())
        log.info(f"[CONFIG] Follow tracking ({ctx.follow_tracking_mode}): {len(ctx._followed_cache)} known followers loaded")
    if ctx.follow_tracking_mode == "per_stream":
        ctx.follow_tracking_file.write_text("")
        ctx._followed_cache.clear()
        log.info("[CONFIG] Follow tracking mode 'per_stream' — follower list reset")

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
                    commands_config[cname] = ccfg
        handler = str(g.get("handler", "rcon")).lower()
        url = str(g.get("url", ""))
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


def load_config():
    """Loads configuration values from the YAML config file."""
    if not CONFIG_FILE.exists():
        log.error(f"Config not found: {CONFIG_FILE}")
        return False

    _check_dup_cmd_config()

    try:
        config = load_yaml(CONFIG_FILE)
        _apply_config(config)
        return True
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
    Supported command prefixes: '!' (RCON), '$' (script), '/' (vanilla), '&' (shell).
    Multiplier ' xN' applies to all types.
    """
    log.info(f"\n[BUILD] Generating datapack in: {ctx.datapack_root}")

    if not ctx.datapack_root.exists() or not ctx.datapack_root.is_dir():
        log.error(f"[BUILD] Datapack root does not exist or is not a directory: {ctx.datapack_root}")
        return

    full_dp_path = ctx.datapack_root / ctx.datapack_name
    functions_path = full_dp_path / "data" / ctx.namespace / "function"

    # Reset state
    ctx.rcon_only_actions = {}
    ctx.valid_functions = set()
    collected_vanilla = {}
    ctx.vanilla_functions = set()
    ctx.script_actions = {}
    ctx.overlay_actions = {}
    ctx.shell_actions_cache = {}

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
                        elif cmd.startswith("&"):
                            kind = "shell"
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

                        overlay_body = body[:multi_match.start()] if multi_match else body
                        if kind == "overlay":
                            ctx.overlay_actions.setdefault(name, []).append((overlay_name, overlay_body))
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
                                elif kind == "shell":
                                    # shell commands keep the raw body (do not replace {user})
                                    shell_cmd = body[:multi_match.start()] if multi_match else body
                                    ctx.shell_actions_cache.setdefault(name, []).append(shell_cmd)
                                    ctx.valid_functions.add(name)

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
        log.exception("Datapack build failed: %s", e)

# ================================
# RCON WORKER
# ================================

async def rcon_worker():
    """Background worker that dequeues RCON commands and sends them to the Minecraft server."""
    log.info("[RCON-QUEUE] Worker started.")
    while True:
        wait_time = ctx.throttle_time
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

    # --- 3. SHELL COMMANDS ---
    if name in ctx.shell_actions_cache:
        cmds = ctx.shell_actions_cache[name]
        if cmds:
            try:
                asyncio.create_task(execute_shell_commands(cmds))
            except Exception as e:
                log.warning(f"[SHELL] Error scheduling shell commands for '{name}': {e}")

    if not commands_to_send:
        return

    # --- 4. ENQUEUE ---
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
# Webhook endpoint for MinecraftServerAPI
# ==========================================
def _publish_event(event_type: str, event_data: dict) -> None:
    """Forward a Minecraft event to the central EventBus via API."""
    body = json.dumps({"type": event_type, "data": event_data}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/events",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception as exc:
        log.info("Failed to publish event '%s' to EventBus: %s", event_type, exc)


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
    if not event:
        return {"status": "no event"}, 400

    # Legacy: local TikTok queue pause / resume
    if event == "player_death":
        ctx.queue_active = False
        log.info("\n[STATUS] [DEAD] Player died! Queue PAUSED.")
    elif event == "player_respawn":
        ctx.queue_active = True
        log.info("\n[STATUS] [OK] Player respawned! Queue RESUMED.")

    # Publish every Minecraft event to the central EventBus generically.
    # Any plugin, hook, or the Event-Command Mapper can react without
    # hardcoded coupling.
    _publish_event(f"minecraft.{event}", dict(data))

    return {"status": "processed"}, 200


API_BASE = "http://127.0.0.1:29185/api/v1"


# ==========================================
# Webhook endpoint for MinecraftServerAPI
# ==========================================
def _publish_event(event_type: str, event_data: dict) -> None:
    """Forward a Minecraft event to the central EventBus via API."""
    body = json.dumps({"type": event_type, "data": event_data}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/events",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception as exc:
        log.info("Failed to publish event '%s' to EventBus: %s", event_type, exc)


def _dispatch_comment_to_plugin(plugin_name: str, cmd_text: str, username: str) -> None:
    """Post a comment command to a plugin's command queue via the API."""
    url = f"{API_BASE}/plugins/{plugin_name}/command"
    body = json.dumps({
        "command": "comment",
        "args": {"text": cmd_text, "username": username},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=3)
        log.debug("Routed '%s' to plugin '%s'", cmd_text, plugin_name)
    except Exception as exc:
        log.info("Failed to route comment to plugin '%s': %s", plugin_name, exc)



def _fetch_comment_handlers() -> dict[str, str]:
    """Fetch ``{prefix: plugin_name}`` from the API registry.

    Called once at startup so the bridge can route chat commands
    to the correct plugin's command queue.
    """
    try:
        req = urllib.request.Request(f"{API_BASE}/comment-handlers")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("handlers") or {}
    except Exception as exc:
        log.info("No comment handlers from API (plugins may not be registered yet): %s", exc)
        return {}


def _dispatch_comment_http(cmd_url, username, cmd_text):
    import urllib.request
    import urllib.parse
    try:
        url = cmd_url.replace("{user}", urllib.parse.quote(username, safe=""))
        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
        req = urllib.request.Request(url, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        log.info(f"[COMMENT CMD] HTTP dispatch failed: {e}")


def _dispatch_comment_http_sync(cmd_url, username, cmd_text):
    import urllib.request
    import urllib.parse
    import json
    try:
        url = cmd_url.replace("{user}", urllib.parse.quote(username, safe=""))
        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.info(f"[COMMENT CMD] Conditional HTTP dispatch failed: {e}")
        return None





def _publish_tiktok_event(event_type: str, user: str, **extra):
    """Publish a TikTok event to the EventBus for plugins to consume."""
    if ctx.main_loop is not None:
        data = {"type": event_type, "user": user, **extra}
        asyncio.run_coroutine_threadsafe(
            event_bus.publish(f"tiktok.{event_type}", data), ctx.main_loop
        )


def _load_event_subscriptions() -> dict[str, list[str]]:
    """Scan all plugin manifests and build event_type → [plugin_names] mapping.

    Supports wildcards in subscriptions:
      "tiktok.*" matches "tiktok.gift", "tiktok.like", etc.
      "tiktok.gift" matches only "tiktok.gift"
    """
    subs: dict[str, list[str]] = {}
    plugins_dir = discover_plugins_dir()
    if not plugins_dir.is_dir():
        return subs

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_plugin_manifest(child)
        if not manifest:
            continue
        plugin_name = manifest.get("name", "")
        if not plugin_name:
            continue
        for pattern in manifest.get("event_subscriptions", []):
            subs.setdefault(pattern, []).append(plugin_name)

    log.info("[EVENT-BRIDGE] Loaded subscriptions for %d pattern(s)", len(subs))
    for pattern, names in sorted(subs.items()):
        log.info("  %s → %s", pattern, names)
    return subs


def _match_event(event_type: str, pattern: str) -> bool:
    """Check if an event type matches a subscription pattern."""
    if pattern == event_type:
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return event_type.startswith(prefix + ".")
    return False


async def _event_bridge_worker():
    """Declarative event bridge.

    Reads event_subscriptions from every plugin.json manifest.
    Routes matching TikTok events to all subscribing plugins via
    CommandQueue with a standardized tiktok_event command.

    No plugin names are hardcoded — third-party plugins work the
    same way as official ones by declaring subscriptions.
    """
    q = event_bus.subscribe()  # all events — tiktok events now have individual types
    ctx.event_subscriptions = _load_event_subscriptions()
    log.info("[EVENT-BRIDGE] Started (declarative).")
    while True:
        msg = await q.get()
        try:
            event_type = msg.get("type", "")
            if not event_type.startswith("tiktok."):
                continue

            data = msg.get("data", {})
            ev_type = data.get("type")
            user = data.get("user")
            if not user or not ev_type:
                continue

            # Normalize event type: gift → tiktok.gift
            full_event_type = f"tiktok.{ev_type}"

            # Find all plugins that subscribe to this event
            recipients: set[str] = set()
            subscriptions = ctx.event_subscriptions
            for pattern, plugin_names in subscriptions.items():
                if _match_event(full_event_type, pattern):
                    recipients.update(plugin_names)

            # Enqueue standardized tiktok_event command to each recipient
            for plugin_name in recipients:
                command_queue.enqueue(
                    plugin_name,
                    "tiktok_event",
                    event_type=full_event_type,
                    user=user,
                    data={k: v for k, v in data.items() if k not in ("type", "user")},
                )

        except Exception as e:
            log.info(f"[EVENT-BRIDGE] Error handling event: {e}")
        finally:
            q.task_done()


def _process_follow(username: str, persist: bool = True):
    """Shared follow dedup: cache check, persist (optional), enqueue trigger once per user."""
    user_lower = username.lower()
    with ctx.follow_lock:
        if user_lower in ctx._followed_cache:
            log.info(f"[FOLLOW] {username} already tracked — follow trigger skipped")
            return
        ctx._followed_cache.add(user_lower)
    if persist:
        try:
            with open(ctx.follow_tracking_file, "a", encoding="utf-8") as f:
                f.write(user_lower + "\n")
        except Exception as e:
            log.info(f"[FOLLOW] Could not write to {ctx.follow_tracking_file}: {e}")
    if "follow" in ctx.valid_functions:
        ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("follow", username))


def _process_comment_command(username, comment_text, is_moderator, is_super_fan, in_fanclub, log_prefix="[COMMENT CMD]"):
    """Shared comment command processing. Returns True if 'comment' event trigger should be suppressed."""
    suppress = False
    if not ctx.comment_cmd_enable or not ctx.comment_cmd_groups:
        return suppress

    # The cooldown dicts are mutated from multiple TikTok event threads and
    # the /test_comment Flask endpoint; guard them with a lock.
    with ctx.comment_cmd_lock:
        now = time.time()
        gcd = ctx.comment_cmd_global_cooldown
        if gcd > 0 and now - ctx.comment_cmd_global_last < gcd:
            remaining = gcd - (now - ctx.comment_cmd_global_last)
            log.info(f"{log_prefix} {username} blocked by global cooldown ({remaining:.1f}s left)")
            return True

        gucd = ctx.comment_cmd_global_user_cooldown
        if gucd > 0:
            last_user = ctx.comment_cmd_global_user_last.get(username, 0)
            if now - last_user < gucd:
                remaining = gucd - (now - last_user)
                log.info(f"{log_prefix} {username} blocked by global user cooldown ({remaining:.1f}s left)")
                return True

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
                log.info(f"{log_prefix} {username} no permission for prefix '{prefix}' (roles: {group['roles']})")
                if not group.get("trigger_comment_event", True):
                    suppress = True
                continue

            base_cmd = cmd_text.split()[0].lower()
            if group["mode"] == "deny-all":
                if base_cmd not in group["commands"]:
                    log.info(f"{log_prefix} {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' not allowed (deny-all)")
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue
            else:
                if base_cmd in group["commands"]:
                    log.info(f"{log_prefix} {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' blocked (allow-all)")
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue

            ccfg = group.get("commands_config", {}).get(base_cmd, {})

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
                    log.info(f"{log_prefix} {username} no permission for '{base_cmd}' (per-command roles: {cmd_roles})")
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue

            cd = ccfg.get("cooldown", group["cooldown"])
            ucd = ccfg.get("user_cooldown", group["user_cooldown"])
            if cd > 0:
                last = ctx.comment_cmd_last_global.get(prefix, 0)
                if now - last < cd:
                    remaining = cd - (now - last)
                    log.info(f"{log_prefix} {username} blocked by global cooldown ({remaining:.1f}s left)")
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue
            if ucd > 0:
                last_user = ctx.comment_cmd_last_user.setdefault(prefix, {}).get(username, 0)
                if now - last_user < ucd:
                    remaining = ucd - (now - last_user)
                    log.info(f"{log_prefix} {username} blocked by user cooldown ({remaining:.1f}s left)")
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue

            conditional = ccfg.get("conditional", False)

            cmd_url = ccfg.get("url", group.get("url", ""))
            cmd_handler = ccfg.get("handler", group.get("handler", ""))
            log.info(f"{log_prefix} {username} -> {cmd_text} (prefix '{prefix}')")

            if not conditional:
                ctx.comment_cmd_last_global[prefix] = now
                ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now
                ctx.comment_cmd_global_last = now
                ctx.comment_cmd_global_user_last[username] = now

            if len(ctx.comment_cmd_last_global) > 1000:
                cutoff = now - 3600
                ctx.comment_cmd_last_global = {k: v for k, v in ctx.comment_cmd_last_global.items() if v >= cutoff}
            if len(ctx.comment_cmd_last_user) > 1000:
                cutoff = now - 3600
                ctx.comment_cmd_last_user = {k: {u: t for u, t in v.items() if t >= cutoff} for k, v in ctx.comment_cmd_last_user.items()}

            # 1. API-registered handler (declarative, dynamic)
            plugin_name = ctx.comment_handler_map.get(prefix)
            if plugin_name:
                _dispatch_comment_to_plugin(plugin_name, cmd_text, username)
            # 2. Legacy RCON handler
            elif cmd_handler == "rcon":
                ctx.main_loop.call_soon_threadsafe(ctx.rcon_queue.put_nowait, ([cmd_text], username))
            # 3. Legacy HTTP handler (backward compat)
            elif cmd_handler == "http" and cmd_url:
                if conditional:
                    resp_data = _dispatch_comment_http_sync(cmd_url, username, cmd_text)
                    if resp_data and resp_data.get("found", False):
                        ctx.comment_cmd_last_global[prefix] = now
                        ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now
                        ctx.comment_cmd_global_last = now
                        ctx.comment_cmd_global_user_last[username] = now
                        mode_label = resp_data.get("mode", "replace")
                        if mode_label == "queue":
                            log.info(f"{log_prefix} {username} → '{base_cmd}' successful — conditional response: mode={mode_label}")
                    else:
                        log.info(f"{log_prefix} {username} → '{base_cmd}' conditional response negative — no cooldown triggered")
                else:
                    url = cmd_url.replace("{user}", urllib.parse.quote(username, safe=""))
                    url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
                    threading.Thread(
                        target=_dispatch_comment_http,
                        args=(url, username, cmd_text),
                        daemon=True
                    ).start()

            if not group.get("trigger_comment_event", True):
                suppress = True

    return suppress


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
            for p in sorted(ctx.comment_cmd_all_prefixes, key=len, reverse=True):
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

        _process_comment_command(username, comment_text, is_moderator, is_super_fan, in_fanclub, log_prefix="[TEST COMMENT]")

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
        cmds = ctx.shell_actions_cache.get(raw_trigger) or ctx.shell_actions_cache.get(sanitized)
        if cmds:
            try:
                asyncio.run_coroutine_threadsafe(execute_shell_commands(cmds), ctx.main_loop)
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500
            log.info(f"[CUSTOM TRIGGER] Shell action for '{raw_trigger}' executed ({len(cmds)} command(s))")
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

async def execute_shell_commands(cmds: list[str]):
    """Execute a list of shell commands sequentially."""
    for cmd in cmds:
        await execute_http_command(cmd)

# ==========================================
# User-friendly name extraction
# =========================================
def get_safe_username(user):
    name = getattr(user, 'unique_id', None) or getattr(user, 'nickname', None) or "Unknown"
    return name

# =========================================
# Like trigger validation
# =========================================

# ==========================================
# Custom trigger + test comment endpoints
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

            username = get_safe_username(event.user)
            _publish_tiktok_event("gift", username, gift_name=gift_name, gift_id=gift_id, count=count)

            target = None
            if gift_name in ctx.valid_functions:
                target = gift_name
            elif gift_id in ctx.valid_functions:
                target = gift_id

            if not target:
                return

            for _ in range(count):
                try:
                    ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, (target, username))
                except asyncio.QueueFull:
                    log.info(f"[GIFT] Queue full, gift '{gift_name}' dropped")

        except Exception:
            log.exception("ERROR IN ON_GIFT EVENT")

    # =========================
    # FOLLOW events
    # =========================
    @client.on(FollowEvent)
    def on_follow(event: FollowEvent):
        username = get_safe_username(event.user)
        _publish_tiktok_event("follow", username)
        _process_follow(username)

    # =========================
    # LIKE events
    # =========================
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        username = get_safe_username(event.user) if hasattr(event, 'user') else None
        if username:
            _publish_tiktok_event("like", username)
        with ctx.like_lock:
            if ctx.start_likes is None:
                ctx.start_likes = event.total
                log.info(f"[LIKE] Initial count set: {ctx.start_likes}")
                return
            total_since_start = event.total - ctx.start_likes
        try:
            now = time.time()
            # Throttle like events to ~1 per 3 seconds
            if not hasattr(ctx, "_last_like_event"):
                ctx._last_like_event = 0
            if now - ctx._last_like_event >= 3:
                delta = total_since_start
                _publish_tiktok_event("like", username or "unknown", delta=delta, total=event.total)
                ctx._last_like_event = now
        except Exception as e:
            log.info(f"[EVENT ERROR] Error in like handling: {e}")

    # ========================
    # Join events
    # ========================
    @client.on(JoinEvent)
    def on_join(event):
        username = get_safe_username(event.user)
        _publish_tiktok_event("join", username)
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
        _publish_tiktok_event("comment", username)
        comment_text = getattr(event, 'comment', '')

        is_super_fan = bool(getattr(event, 'user_is_super_fan', None))

        in_fanclub = False
        fan_ticket_count = getattr(event.user, 'fan_ticket_count', None)
        fans_club = getattr(event.user, 'fans_club', None)
        fans_club_info = getattr(event.user, 'fans_club_info', None)
        if fan_ticket_count and fan_ticket_count > 0:
            in_fanclub = True
        elif hasattr(fans_club, 'club_name') or hasattr(fans_club_info, 'club_name'):
            in_fanclub = True

        is_moderator = bool(getattr(event.user, 'is_moderator', None))

        log.info(f"[COMMENT] {username}: {comment_text}")
        log.info(f"  Superfan: {is_super_fan}")
        log.info(f"  Fanclub-Mitglied: {in_fanclub}")
        log.info(f"  Moderator: {is_moderator}")

        if ctx.comment_cmd_all_prefixes:
            matched_prefix = None
            for p in sorted(ctx.comment_cmd_all_prefixes, key=len, reverse=True):
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

        suppress_comment_trigger = _process_comment_command(username, comment_text, is_moderator, is_super_fan, in_fanclub, log_prefix="[COMMENT CMD]")

        if "comment" in ctx.valid_functions and not suppress_comment_trigger:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("comment", {"user": username, "comment": comment_text}))

    # =========================
    # Share events
    # =========================
    @client.on(ShareEvent)
    def on_share(event):
        username = get_safe_username(event.user)
        _publish_tiktok_event("share", username)
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
def update_daily_revenue():
    """Persist the estimated daily gift revenue to a JSONL log.

    The log lives at ``data/revenue_log.jsonl``. Each day gets one entry
    with the difference between the current ``ctx.gift_value_usd`` and the
    value recorded at the start of that day.
    """
    file_path = BASE_DIR.parent / "data" / "revenue_log.jsonl"
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    with ctx.gift_lock:
        if ctx.gift_current_log_date != today:
            ctx.gift_day_start_value = ctx.gift_value_usd
            ctx.gift_current_log_date = today

        daily_value = ctx.gift_value_usd - ctx.gift_day_start_value

        new_entry = {
            "date": today,
            "estimated_revenue_usd": round(daily_value, 2),
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

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def gift_revenue_counter():
    while True:
        await asyncio.sleep(ctx.autosave_interval_seconds)
        await asyncio.to_thread(update_daily_revenue)


# ==========================================
# RUNTIME RELOAD
# ==========================================

async def reload_config():
    """Reload config.yaml at runtime without restarting the bridge."""
    log.info("[RELOAD] Config reload requested")
    try:
        _validate_dup_cmd_config()
        new_config = load_yaml(CONFIG_FILE)
        old_user = ctx.tiktok_user
        _apply_config(new_config)

        if ctx.hook_api is not None:
            ctx.hook_api.update_runtime_state(
                config=ctx.config,
                valid_functions=ctx.valid_functions,
            )

        ctx.comment_handler_map = _fetch_comment_handlers()
        ctx.event_subscriptions = _load_event_subscriptions()

        # Force the RCON worker to reconnect with the new settings.
        ctx.rcon_connection = None

        if old_user != ctx.tiktok_user and ctx.tiktok_client is not None:
            try:
                ctx.tiktok_client.stop()
            except Exception:
                pass

        log.info("[RELOAD] Config reloaded successfully")
    except Exception as e:
        log.error("[RELOAD] Config reload failed: %s", e)


async def reload_actions(send_minecraft_reload: bool = False):
    """Reload actions.mca at runtime without restarting the bridge.

    ``send_minecraft_reload`` asks the bridge to push ``/reload`` to the
    Minecraft server via RCON after the datapack has been regenerated.
    """
    log.info("[RELOAD] Actions reload requested (send /reload: %s)", send_minecraft_reload)
    try:
        diags = validate_file(ACTIONS_FILE, raise_on_error=False)
        if any(d.severity == Severity.ERROR for d in diags):
            log.error("[RELOAD] actions.mca contains errors; reload aborted")
            print_diagnostics(diags)
            return

        generate_datapack()
        if ctx.hook_api is not None:
            ctx.hook_api.update_runtime_state(valid_functions=ctx.valid_functions)

        if send_minecraft_reload:
            if ctx.rcon_enabled:
                try:
                    ctx.rcon_queue.put_nowait((["/reload"], "system"))
                    log.info("[RELOAD] Sent /reload to Minecraft server")
                except asyncio.QueueFull:
                    log.warning("[RELOAD] RCON queue full; could not send /reload")
            else:
                log.info(
                    "[RELOAD] /reload requested but RCON disabled; "
                    "vanilla action changes require a Minecraft server restart or manual /reload"
                )

        log.info("[RELOAD] Actions reloaded successfully")
    except Exception as e:
        log.error("[RELOAD] Actions reload failed: %s", e)


def _read_signal_options(path: Path) -> dict:
    """Read a JSON signal payload, defaulting to ``send_minecraft_reload=True``."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if text.startswith("{"):
            return json.loads(text)
    except Exception:
        pass
    return {"send_minecraft_reload": True}


async def _reload_signal_watcher():
    """Poll runtime signal files and trigger in-process reloads."""
    while True:
        await asyncio.sleep(1)
        try:
            if RELOAD_CONFIG_SIGNAL.exists():
                try:
                    RELOAD_CONFIG_SIGNAL.unlink()
                except Exception:
                    pass
                await reload_config()
            if RELOAD_ACTIONS_SIGNAL.exists():
                options = _read_signal_options(RELOAD_ACTIONS_SIGNAL)
                try:
                    RELOAD_ACTIONS_SIGNAL.unlink()
                except Exception:
                    pass
                await reload_actions(send_minecraft_reload=options.get("send_minecraft_reload", True))
        except Exception as e:
            log.error("[RELOAD] Signal watcher error: %s", e)


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

    # TikTok username check: warn if still default, but do not block startup.
    default_user = "your_tiktok_username"
    if ctx.tiktok_user == default_user:
        log.warning(
            "[TIKTOK] Username is still the default '%s'. "
            "Set it via the GUI wizard or config.yaml; the bridge will connect once it is provided.",
            default_user,
        )

    # Fetch registered comment handlers from API for prefix→plugin routing
    ctx.comment_handler_map = _fetch_comment_handlers()
    if ctx.comment_handler_map:
        log.info("[COMMENT] Registered handlers: %s", ctx.comment_handler_map)

    try:
        diags = validate_file(ACTIONS_FILE, raise_on_error=False)
        if diags:
            log.info("[VALIDATOR] Validation result for actions.mca:")
            print_diagnostics(diags)
        if any(d.severity == Severity.ERROR for d in diags):
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

    ctx.hook_api = HookAPI(
        ctx.rcon_queue, ctx.trigger_queue, ctx.main_loop,
        ctx.config, ctx.valid_functions,
    )
    load_event_hooks(ctx.hook_api, config=ctx.config)

    # Clear any stale reload signals from a previous run before the watcher starts.
    for sig in (RELOAD_CONFIG_SIGNAL, RELOAD_ACTIONS_SIGNAL):
        try:
            sig.unlink(missing_ok=True)
        except Exception:
            pass

    threading.Thread(target=run_signal_server, daemon=True).start()

    asyncio.create_task(trigger_worker())
    asyncio.create_task(rcon_worker())
    asyncio.create_task(_event_bridge_worker())
    asyncio.create_task(gift_revenue_counter())
    asyncio.create_task(_reload_signal_watcher())

    while True:
        with ctx.tiktok_lock:
            _disabled = ctx.disable_tiktok_connect
        if _disabled:
            await asyncio.sleep(ctx.reconnect_delay)
            continue

        if ctx.tiktok_user == default_user or not ctx.tiktok_user:
            log.info("[TIKTOK] No valid username configured yet. Waiting for config reload...")
            await asyncio.sleep(ctx.reconnect_delay)
            continue

        ctx.start_likes = None
        client = create_client(ctx.tiktok_user)
        ctx.tiktok_client = client

        try:
            log.info(f"[*] Connecting to @{ctx.tiktok_user}...")
            await asyncio.to_thread(client.run)

        except Exception as e:
            log.exception("CRITICAL ERROR IN TIKTOK CLIENT")

            error_str = str(e)
            log.info(f"[..] Connection lost: {error_str}")

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
    install_global_exception_hook("main")
    heartbeat = start_heartbeat(log, interval=60.0)
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("\n[STOP] Script stopped manually.")
    except Exception:
        handle_unhandled_exception("main")
        sys.exit(1)
    finally:
        heartbeat.stop()