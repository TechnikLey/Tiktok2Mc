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

# ==========================================
# CONFIGURATION & PATHS
# ==========================================

BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR / ".." / "config" / "config.yaml").resolve()
ACTIONS_FILE = (BASE_DIR / ".." / "data" / "actions.mca").resolve()
HTTP_ACTIONS_FILE = (BASE_DIR / ".." / "data" / "http_actions.txt").resolve()

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

        # Comment commands
        self.comment_cmd_enable = False
        self.comment_cmd_groups = []
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
        self.http_actions_cache = {}
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
        self.runtime_path_shutdown = (BASE_DIR / "runtime" / "shutdown").resolve()

        # RCON retry tracking (keyed by repr(commands) to limit re-queue loops)
        self.max_rcon_retries = 3
        self.rcon_queue_retries: dict[str, int] = {}


ctx = BotContext()

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ==========================================
# SETUP & HELPER FUNCTIONS
# ==========================================

def load_config():
    """Loads configuration values from the YAML config file."""
    if not CONFIG_FILE.exists():
        print(f"[ERROR] Config not found: {CONFIG_FILE}")
        return False

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

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

        ctx.like_triggers = validate_like_triggers(config.get("like_goal", {}).get("triggers", []))

        comment_cmd_cfg = config.get("comment_commands", {})
        ctx.comment_cmd_enable = bool(comment_cmd_cfg.get("enabled", False))
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
            print("[CONFIG] comment_commands: using legacy single-group format")
        ctx.comment_cmd_groups = []
        seen_prefixes = set()
        for g in raw_groups:
            prefix = str(g.get("prefix", "#"))
            enabled = bool(g.get("enabled", True))
            if not enabled:
                print(f"[CONFIG] comment_commands group '{prefix}': disabled by config")
                continue
            if prefix in seen_prefixes:
                print(f"[WARN] comment_commands: duplicate prefix '{prefix}' — keeping only first definition, skipping duplicate")
                continue
            seen_prefixes.add(prefix)
            raw_roles = g.get("allowed_roles", ["moderator"])
            roles = [str(r).strip().lower() for r in raw_roles if str(r).strip()] if isinstance(raw_roles, list) else ["moderator"]
            mode = str(g.get("mode", "deny-all")).lower()
            raw_commands = g.get("commands", [])
            commands = [str(c).strip() for c in raw_commands if str(c).strip()] if isinstance(raw_commands, list) else []
            handler = str(g.get("handler", "rcon")).lower()
            url = str(g.get("url", ""))
            spotify_port = config.get("spotify", {}).get("port", 29194)
            url = url.replace("{spotify_port}", str(spotify_port))
            cooldown = max(0, int(g.get("cooldown", 0)))
            user_cooldown = max(0, int(g.get("user_cooldown", 0)))
            if mode == "allow-all" and not commands and handler == "rcon":
                print(f"[WARN] comment_commands group '{prefix}': allow-all + empty list — ALL commands allowed!")
            ctx.comment_cmd_groups.append({
                "prefix": prefix,
                "roles": roles,
                "mode": mode,
                "commands": commands,
                "handler": handler,
                "url": url,
                "cooldown": cooldown,
                "user_cooldown": user_cooldown,
            })

        ctx.datapack_root = (BASE_DIR / ".." / "server" / "mc" / "world" / "datapacks").resolve()
        return ctx.datapack_root.exists() and ctx.datapack_root.is_dir()
    except Exception as e:
        print(f"[ERROR] Config error: {e}")
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
    print(f"\n[BUILD] Generating datapack in: {ctx.datapack_root}")

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
        print(f"[ERROR] Failed to create datapack directory: {e}")
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
                            print(f"[ERROR] Invalid command without prefix on line {line_num}: {cmd}")
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
        print(f"[ERROR] Datapack build failed: {e}")

# ================================
# RCON WORKER
# ================================

async def rcon_worker():
    """Background worker that dequeues RCON commands and sends them to the Minecraft server."""
    print("[RCON-QUEUE] Worker started.")
    while True:
        commands, source_user = await ctx.rcon_queue.get()
        try:
            if not ctx.queue_active:
                await ctx.rcon_queue.put((commands, source_user))
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
                            timeout=0.5
                        )
                        await asyncio.wait_for(
                            asyncio.to_thread(ctx.rcon_connection.connect),
                            timeout=0.5
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        ctx.rcon_connection = None
                        raise ConnectionError(f"Server unreachable: {e}")

                for cmd in commands:
                    await asyncio.to_thread(ctx.rcon_connection.command, cmd)
                    if inner_pause > 0:
                        await asyncio.sleep(inner_pause)

        except Exception as e:
            print(f"[RCON OFFLINE] {e}")
            ctx.rcon_connection = None
            await asyncio.sleep(5)
            retry_key = repr((commands, source_user))
            retries = ctx.rcon_queue_retries.get(retry_key, 0) + 1
            if retries <= ctx.max_rcon_retries:
                ctx.rcon_queue_retries[retry_key] = retries
                try:
                    await ctx.rcon_queue.put((commands, source_user))
                except Exception:
                    print("RCON Queue Error")
            else:
                print(f"[RCON] Dropping commands after {retries} failed attempts: {commands}")
                ctx.rcon_queue_retries.pop(retry_key, None)
            await asyncio.sleep(wait_time)
            continue
        finally:
            ctx.rcon_queue.task_done()
            await asyncio.sleep(wait_time)

async def execute_global_command(trigger_name: str, source_user: str, chain_depth: int = 0):
    """Resolves a trigger name into RCON commands and enqueues them."""
    name = sanitize_filename(trigger_name)
    
    if name not in ctx.valid_functions:
        return

    commands_to_send = []

    if name in ctx.script_actions:
        for action in ctx.script_actions[name]:
            if action in HOOK_ACTIONS:
                try:
                    ctx.hook_api._current_depth = chain_depth
                    HOOK_ACTIONS[action](source_user, action, {})
                except Exception as e:
                    print(f"[HOOK] [WARN] Error in action '{action}': {e}")
            elif action:
                print(f"[HOOK] [WARN] Unknown script action: '{action}'") 

    # --- 0. OVERLAY TEXT ---
    comment_text = None
    if isinstance(source_user, dict):
        comment_text = source_user.get('comment', '')
        user_display = source_user.get('user', '')
    else:
        user_display = source_user

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
    try:
        ctx.main_loop.call_soon_threadsafe(ctx.rcon_queue.put_nowait, (commands_to_send, source_user))
        if ctx.rcon_queue.qsize() < 10: 
            print(f"[ACTION] Trigger: {name} | Commands: {len(commands_to_send)} (for {source_user}) enqueued.")
    except asyncio.QueueFull:
        print(f"[RCON-QUEUE FULL] Trigger {name} dropped!")

# ================================
# TRIGGER WORKER
# ================================
async def trigger_worker():
    """Processes TikTok events from the trigger queue and converts them into RCON commands."""
    print("[TRIGGER-QUEUE] Worker started.")
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
                print(f"[TRIGGER WORKER ERROR] Error processing {trigger}/{source_user}: {e}")
            finally:
                ctx.trigger_queue.task_done()
        except Exception as e_outer:
            print(f"[TRIGGER-QUEUE LOOP ERROR] {e_outer}")
            await asyncio.sleep(0.1)  

# ==========================================
# HTTP actions loader
# ==========================================

def load_http_actions(file_path=HTTP_ACTIONS_FILE):
    """Loads all HTTP actions into memory at startup."""
    ctx.http_actions_cache = {}

    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_clean = line.split("#", 1)[0].strip()
            if not line_clean or ":" not in line_clean:
                continue

            trigger_id, cmd = map(str.strip, line_clean.split(":", 1))
            ctx.http_actions_cache[trigger_id] = cmd

    print(f"[INFO] HTTP actions loaded: {len(ctx.http_actions_cache)} entries")

# ==========================================
# Webhook endpoint for MinecraftServerAPI
# ==========================================
@app.route('/webhook', methods=['POST'])
def handle_minecraft_events():
    try:
        data = request.json
    except Exception as e:
        print(f"[ERROR] Webhook invalid JSON: {e}")
        return {"status": "invalid json"}, 400

    if not data:
        return {"status": "no data"}, 400

    event = data.get("event")

    if event == "player_death":
        ctx.queue_active = False
        print("\n[STATUS] [DEAD] Player died! Queue PAUSED.")
    
    elif event == "player_respawn":
        ctx.queue_active = True
        print("\n[STATUS] [OK] Player respawned! Queue RESUMED.")

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
        print(f"[COMMENT CMD] HTTP dispatch failed: {e}")

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

        print(f"[TEST COMMENT] {username}: {comment_text}")
        print(f"  Moderator: {is_moderator}, Superfan: {is_super_fan}, Fanclub: {in_fanclub}")

        if ctx.comment_cmd_enable and ctx.comment_cmd_groups:
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
                    print(f"[TEST COMMENT] {username} no permission for prefix '{prefix}' (roles: {group['roles']})")
                    continue

                base_cmd = cmd_text.split()[0].lower()
                if group["mode"] == "deny-all":
                    if base_cmd not in group["commands"]:
                        print(f"[TEST COMMENT] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' not allowed (deny-all)")
                        continue
                else:
                    if base_cmd in group["commands"]:
                        print(f"[TEST COMMENT] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' blocked (allow-all)")
                        continue

                now = time.time()
                cd = group["cooldown"]
                ucd = group["user_cooldown"]
                if cd > 0:
                    last = ctx.comment_cmd_last_global.get(prefix, 0)
                    if now - last < cd:
                        remaining = cd - (now - last)
                        print(f"[TEST COMMENT] {username} blocked by global cooldown ({remaining:.1f}s left)")
                        continue
                if ucd > 0:
                    last_user = ctx.comment_cmd_last_user.setdefault(prefix, {}).get(username, 0)
                    if now - last_user < ucd:
                        remaining = ucd - (now - last_user)
                        print(f"[TEST COMMENT] {username} blocked by user cooldown ({remaining:.1f}s left)")
                        continue

                print(f"[TEST COMMENT] {username} -> {cmd_text} (prefix '{prefix}', handler {group['handler']})")

                ctx.comment_cmd_last_global[prefix] = now
                ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now

                if group["handler"] == "rcon":
                    ctx.main_loop.call_soon_threadsafe(ctx.rcon_queue.put_nowait, ([cmd_text], username))
                elif group["handler"] == "http" and group["url"]:
                    import urllib.request, urllib.parse
                    url = group["url"].replace("{user}", urllib.parse.quote(username, safe=""))
                    url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
                    threading.Thread(
                        target=_dispatch_comment_http,
                        args=(group["url"], username, cmd_text),
                        daemon=True
                    ).start()

        return {"status": "ok", "message": f"Comment '{comment_text}' from '{username}' processed."}
    except Exception as e:
        print(f"[TEST COMMENT] Error: {e}")
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
            print(f"[CUSTOM TRIGGER] TikTok connect toggled: {not new_state} -> {new_state}")
            return {"status": "ok", "message": f"TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT={new_state}"}, 200

        if ctx.main_loop is None:
            return {"status": "error", "message": "Bot event loop not ready yet."}, 503

        if sanitized in ctx.valid_functions:
            try:
                ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, (sanitized, user))
            except asyncio.QueueFull:
                return {"status": "error", "message": "Trigger queue is full. Try again later."}, 503
            print(f"[CUSTOM TRIGGER] Injected: '{sanitized}' (user: {user})")
            return {"status": "ok", "trigger": sanitized, "user": user}, 200

        raw_trigger = str(data.get("trigger", "")).strip()
        cmd = ctx.http_actions_cache.get(raw_trigger) or ctx.http_actions_cache.get(sanitized)
        if cmd:
            try:
                asyncio.run_coroutine_threadsafe(execute_http_command(cmd), ctx.main_loop)
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500
            print(f"[CUSTOM TRIGGER] HTTP action for '{raw_trigger}' executed")
            return {"status": "ok", "trigger": raw_trigger, "user": user}, 200

        return {"status": "error", "message": f"Trigger '{sanitized}' does not exist or is not valid."}, 400

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
# =========================================

# --- Start webhook server in its own thread ---
def run_signal_server():
    app.run(host=ctx.server_host, port=ctx.mcserver_api_port, debug=False, use_reloader=False)

# ==========================================
# HTTP command executor
# ==========================================

def execute_http_command_sync(cmd: str):
    try:
        subprocess.run(cmd, shell=True, check=True)
        print(f"[OK] Success: {cmd}")
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] Error: {cmd} ({e})")

async def execute_http_command(cmd: str):
    await asyncio.to_thread(execute_http_command_sync, cmd)

def execute_gift_action(gift_id: str):
    """Executes an HTTP action for a gift asynchronously."""
    cmd = ctx.http_actions_cache.get(gift_id)
    if not cmd:
        return

    try:
        asyncio.run_coroutine_threadsafe(execute_http_command(cmd), ctx.main_loop)
        print(f"[HTTP] Action for gift {gift_id} started")
    except Exception as e:
        print(f"[HTTP ERROR] {e}")

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
    print("[LIKEGOAL-QUEUE] Worker started.")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            delta_val = await ctx.likegoal_queue.get()
            try:
                url = f"http://127.0.0.1:{ctx.like_goal_port}/update_likes?add={delta_val}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        pass
            except Exception as e:
                print(f"[LIKEGOAL ERROR] {e}")
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
            print(f"[CONFIG ERROR] Entry #{i} is not an object: {rule}")
            continue

        # --- ID ---
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            print(f"[CONFIG ERROR] Invalid or missing 'id': {rule}")
            continue

        if rule_id in seen_ids:
            print(f"[CONFIG ERROR] Duplicate id '{rule_id}'")
            continue
        seen_ids.add(rule_id)

        # --- EVERY (trigger interval) ---
        raw_every = rule.get("every")
        if raw_every is None:
            print(f"[CONFIG ERROR] 'every' missing for {rule_id}")
            continue

        try:
            if isinstance(raw_every, str):
                raw_every = raw_every.replace("_", "")
            every = int(raw_every)

            if every <= 0:
                raise ValueError()

        except Exception:
            print(f"[CONFIG ERROR] Invalid 'every' value for {rule_id}: {raw_every}")
            continue

        # --- FUNCTION (action to execute) ---
        function_name = rule.get("function")
        if not isinstance(function_name, str) or not function_name.strip():
            print(f"[CONFIG ERROR] Invalid or missing 'function' for {rule_id}")
            continue

        # --- PAYLOAD (user label, optional) ---
        payload = rule.get("payload", "Community")
        if not isinstance(payload, str):
            print(f"[CONFIG ERROR] 'payload' must be a string for {rule_id}")
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
            print(f"[CONFIG ERROR] Unknown function: {rule['function']}")
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

            target = None
            if gift_name in ctx.valid_functions:
                target = gift_name
            elif gift_id in ctx.valid_functions:
                target = gift_id

            if not target:
                return

            username = get_safe_username(event.user)

            for _ in range(count):
                ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, (target, username))

        except Exception:
            print("\n" + "!"*30)
            print("ERROR IN ON_GIFT EVENT:")
            traceback.print_exc()
            print("!"*30 + "\n")

    # =========================
    # FOLLOW events
    # =========================
    @client.on(FollowEvent)
    def on_follow(event: FollowEvent):
        username = get_safe_username(event.user)
        if "follow" in ctx.valid_functions:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("follow", username))

    # =========================
    # LIKE events
    # =========================
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        with ctx.like_lock:
            if ctx.start_likes is None:
                ctx.start_likes = event.total
                print(f"[LIKE] Initial count set: {ctx.start_likes}")
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
                        print(f"[LIKE] Trigger '{rule['id']}' -> +{diff}")
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
                    pass
        except Exception as e:
            print(f"[EVENT ERROR] Error in like handling: {e}")

    # ========================
    # Join events
    # ========================
    @client.on(JoinEvent)
    def on_join(event):
        username = get_safe_username(event.user)
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

        print(f"[COMMENT] {username}: {comment_text}")
        print(f"  Superfan: {is_super_fan}")
        print(f"  Fanclub-Mitglied: {in_fanclub}")
        print(f"  Moderator: {is_moderator}")

        if ctx.comment_cmd_enable and ctx.comment_cmd_groups:
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
                    print(f"[COMMENT CMD] {username} no permission for prefix '{prefix}' (roles: {group['roles']})")
                    continue

                base_cmd = cmd_text.split()[0].lower()
                if group["mode"] == "deny-all":
                    if base_cmd not in group["commands"]:
                        print(f"[COMMENT CMD] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' not allowed (deny-all)")
                        continue
                else:
                    if base_cmd in group["commands"]:
                        print(f"[COMMENT CMD] {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' blocked (allow-all)")
                        continue

                now = time.time()
                cd = group["cooldown"]
                ucd = group["user_cooldown"]
                if cd > 0:
                    last = ctx.comment_cmd_last_global.get(prefix, 0)
                    if now - last < cd:
                        remaining = cd - (now - last)
                        print(f"[COMMENT CMD] {username} blocked by global cooldown ({remaining:.1f}s left)")
                        continue
                if ucd > 0:
                    last_user = ctx.comment_cmd_last_user.setdefault(prefix, {}).get(username, 0)
                    if now - last_user < ucd:
                        remaining = ucd - (now - last_user)
                        print(f"[COMMENT CMD] {username} blocked by user cooldown ({remaining:.1f}s left)")
                        continue

                print(f"[COMMENT CMD] {username} -> {cmd_text} (prefix '{prefix}', handler {group['handler']})")

                ctx.comment_cmd_last_global[prefix] = now
                ctx.comment_cmd_last_user.setdefault(prefix, {})[username] = now

                if group["handler"] == "rcon":
                    ctx.main_loop.call_soon_threadsafe(ctx.rcon_queue.put_nowait, ([cmd_text], username))
                elif group["handler"] == "http" and group["url"]:
                    threading.Thread(
                        target=_dispatch_comment_http,
                        args=(group["url"], username, cmd_text),
                        daemon=True
                    ).start()

        if "comment" in ctx.valid_functions:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("comment", {"user": username, "comment": comment_text}))

    # =========================
    # Share events
    # =========================
    @client.on(ShareEvent)
    def on_share(event):
        username = get_safe_username(event.user)
        if "share" in ctx.valid_functions:
            ctx.main_loop.call_soon_threadsafe(ctx.trigger_queue.put_nowait, ("share", username))

    # =========================
    # Live end events
    # =========================
    @client.on(LiveEndEvent)
    def on_live_end(_):
        update_daily_revenue()
        print(f"[STATUS] Live ended for @{user}.")
        ctx.runtime_path_shutdown.touch(exist_ok=True)

    # =========================
    # CONNECT event
    # =========================
    @client.on(ConnectEvent)
    def on_connect(_):
        _connect_time[0] = time.time()
        print(f"[OK] Live connection established: @{user}")

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
        print("Error in load_config")
        sys.exit(0)

    # TikTok username check: ask user if still default
    default_user = "your_tiktok_username"
    if ctx.tiktok_user == default_user:
        print(f"\n[TIKTOK] Your TikTok username is still the default '{default_user}'.")
        inp = input("  Enter your TikTok username (press Enter to keep the default): ").strip()
        if inp:
            ctx.tiktok_user = inp
            print(f"[TIKTOK] Username set to @{ctx.tiktok_user} (session only).")
        else:
            print(f"[TIKTOK] No input – using default '{default_user}'.")

    try:
        diags = validate_file(ACTIONS_FILE, raise_on_error=False)
        if diags:
            print("[VALIDATOR] Validation result for actions.mca:")
            print_diagnostics(diags)
        if any(d.severity.name == "ERROR" for d in diags):
            print("[STOP] Errors found. Please fix actions.mca and restart.")
            input("Press Enter to exit...\n\n\n")
            return
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return

    generate_datapack()
    ctx.like_triggers = prepare_like_triggers(ctx.like_triggers)
    load_http_actions()

    EVENT_HOOKS_DIR = (BASE_DIR / ".." / "event_hooks").resolve()
    ctx.hook_api = HookAPI(ctx.rcon_queue, ctx.trigger_queue, ctx.main_loop, ctx.config, ctx.valid_functions)
    load_event_hooks(ctx.hook_api, EVENT_HOOKS_DIR)

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
            print(f"[*] Connecting to @{ctx.tiktok_user}...")
            await asyncio.to_thread(client.run)

        except Exception as e:
            print("\n" + "="*50)
            print("CRITICAL ERROR IN TIKTOK CLIENT:")
            traceback.print_exc() 
            print("="*50 + "\n")

            error_str = str(e)
            print(f"[..] Connection lost: {error_str}")

            if "DEVICE_BLOCKED" in error_str or bool(re.search(r"\b(err_code|code|status)\b.*?\b200\b", error_str, re.IGNORECASE)):
                print("[FAIL] TikTok block active (DEVICE_BLOCKED).")
                print("[TIP] Wait 15 minutes or restart your router.")
                await asyncio.sleep(900)
            else:
                print(f"[..] Reconnect in {ctx.reconnect_delay}s...")
                await asyncio.sleep(ctx.reconnect_delay)

        finally:
            try:
                client.stop()
            except Exception:
                pass
            await asyncio.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=run_signal_server, daemon=True).start()

    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n[STOP] Script stopped manually.")