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
import random
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

# Windows-specific fix for the event loop (prevents WinError 6)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==========================================
# CONFIGURATION & PATHS
# ==========================================

BASE_DIR = get_base_dir()

CONFIG_FILE = (BASE_DIR / ".." / "config" / "config.yaml").resolve()
ACTIONS_FILE = (BASE_DIR / ".." / "data" / "actions.mca").resolve()
HTTP_ACTIONS_FILE = (BASE_DIR / ".." / "data" / "http_actions.txt").resolve()

MC_HOST, MC_PORT, MC_PASS = "localhost", 25575, ""
DATAPACK_ROOT, CONFIG_TIKTOK_USER = "", ""
RECONNECT_DELAY = 30
# Server host for binding (default: local only; set to "0.0.0.0" to allow network access)
SERVER_HOST = "127.0.0.1"
LIKE_GOAL_PORT = 9797
LIKE_TRIGGERS = []
AUTOSAVE_INTERVAL_SECONDS = 60

# --- Queues & throttling (for optimal RCON performance) ---
trigger_queue = asyncio.Queue(maxsize=10_000)
rcon_queue = asyncio.Queue(maxsize=10_000)
likegoal_queue = asyncio.Queue()
THROTTLE_TIME = 0.5 

# --- Datapack constants ---
DATAPACK_NAME = "StreamingTool"
NAMESPACE = "streamingtool"
start_likes = None
valid_functions = set()
vanilla_functions = set()
http_actions_cache = {}
possible_random_actions = []
script_actions = {}
overlay_actions = {}
triggered_blocks = {}
like_lock = threading.Lock()

MAIN_LOOP = None
_hook_api = None

QUEUE_ACTIVE = True
MCSERVER_API_PORT = 7777

OVERLAYTXT_PORT = 5005

last_likegoal_sent = 0
last_likegoal_time = 0
LIKEGOAL_INTERVAL = 3

DISABLE_TIKTOK_CONNECT = False  # Toggle for disabling TikTok connection

# --- Comment commands ---
COMMENT_CMD_ENABLE = False
COMMENT_CMD_PREFIX = "!"
COMMENT_CMD_ROLES = ["moderator"]
COMMENT_CMD_WHITELIST = []  # Only these commands allowed (empty = all allowed)
COMMENT_CMD_BLACKLIST = []  # These commands are blocked

RANDOM_TRIGGER_WHITELIST = []
RANDOM_TRIGGER_BLACKLIST = []

GIFT_VALUE_USD = 0
RUNTIME_PATH_SHUTDOWN = (BASE_DIR / "runtime" / "shutdown").resolve()

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ==========================================
# SETUP & HELPER FUNCTIONS
# ==========================================

def load_config():
    """Loads configuration values from the YAML config file."""
    global MC_HOST, MC_PORT, MC_PASS, DATAPACK_ROOT, CONFIG_TIKTOK_USER, RECONNECT_DELAY, MCSERVER_API_PORT, OVERLAYTXT_PORT, LIKE_GOAL_PORT, LIKE_TRIGGERS, AUTOSAVE_INTERVAL_SECONDS
    global COMMENT_CMD_ENABLE, COMMENT_CMD_PREFIX, COMMENT_CMD_ROLES, COMMENT_CMD_WHITELIST, COMMENT_CMD_BLACKLIST
    global RANDOM_TRIGGER_WHITELIST, RANDOM_TRIGGER_BLACKLIST, SERVER_HOST

    if not CONFIG_FILE.exists():
        print(f"[ERROR] Config not found: {CONFIG_FILE}")
        return False

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        MC_PASS = config.get("RCON", {}).get("Password", "")
        MC_PORT = config.get("RCON", {}).get("Port", 25575)
        SERVER_HOST = config.get("server_host", "127.0.0.1")
        CONFIG_TIKTOK_USER = config.get("TikTok", {}).get("User", "")
        RECONNECT_DELAY = config.get("TikTok", {}).get("ReconnectDelaySeconds", 10)
        MCSERVER_API_PORT = config.get("MinecraftServerAPI", {}).get("WebServerPort", 7777)
        OVERLAYTXT_PORT = config.get("Overlaytxt", {}).get("Port", 5005)
        LIKE_GOAL_PORT = config.get("Gifts", {}).get("LIKE_GOAL_PORT", 9797)
        AUTOSAVE_INTERVAL_SECONDS = config.get("Gifts", {}).get("autosave_interval_seconds", 60)

        raw_included = config.get("Gifts", {}).get("random_included", [])
        RANDOM_TRIGGER_WHITELIST = [str(c).strip() for c in raw_included if str(c).strip()] if isinstance(raw_included, list) else []
        raw_exclude = config.get("Gifts", {}).get("random_exclude", [])
        RANDOM_TRIGGER_BLACKLIST = [str(c).strip() for c in raw_exclude if str(c).strip()] if isinstance(raw_exclude, list) else []

        LIKE_TRIGGERS = validate_like_triggers(config.get("Gifts", {}).get("like_triggers", []))

        comment_cmd_cfg = config.get("CommentCommands", {})
        COMMENT_CMD_ENABLE = bool(comment_cmd_cfg.get("Enable", False))
        COMMENT_CMD_PREFIX = str(comment_cmd_cfg.get("Prefix", "#"))
        raw_roles = comment_cmd_cfg.get("AllowedRoles", ["moderator"])
        if isinstance(raw_roles, list):
            COMMENT_CMD_ROLES = [str(r).strip().lower() for r in raw_roles if str(r).strip()]
        else:
            COMMENT_CMD_ROLES = ["moderator"]
        raw_whitelist = comment_cmd_cfg.get("Whitelist", [])
        COMMENT_CMD_WHITELIST = [str(c).strip() for c in raw_whitelist if str(c).strip()] if isinstance(raw_whitelist, list) else []
        raw_blacklist = comment_cmd_cfg.get("Blacklist", [])
        COMMENT_CMD_BLACKLIST = [str(c).strip() for c in raw_blacklist if str(c).strip()] if isinstance(raw_blacklist, list) else []
        if COMMENT_CMD_ENABLE and not COMMENT_CMD_WHITELIST and not COMMENT_CMD_BLACKLIST:
            print("[WARN] CommentCommands: Whitelist and Blacklist are both empty — ALL Minecraft commands are allowed!")

        DATAPACK_ROOT = (BASE_DIR / ".." / "server" / "mc" / "world" / "datapacks").resolve()
        return DATAPACK_ROOT.exists() and DATAPACK_ROOT.is_dir()
    except Exception as e:
        print(f"[ERROR] Config error: {e}")
        return False

def sanitize_filename(name):
    """Returns a Minecraft-safe name (only a-z, 0-9, _, -)."""
    name = str(name).lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_-]", "", name)

# Commands that cannot run inside datapacks and must be sent via RCON
rcon_only_actions = {}

def generate_datapack():
    """Generates datapack files for vanilla commands and stores
    plugin/script commands separately.
    Supported command prefixes: '!' (RCON), '$' (script), '/' (vanilla).
    Multiplier ' xN' applies to all types.
    """
    global valid_functions, rcon_only_actions, vanilla_functions, possible_random_actions, script_actions, overlay_actions
    print(f"\n[BUILD] Generating datapack in: {DATAPACK_ROOT}")

    full_dp_path = DATAPACK_ROOT / DATAPACK_NAME
    functions_path = full_dp_path / "data" / NAMESPACE / "function"

    # Reset globals
    rcon_only_actions = {}
    valid_functions = set()
    collected_vanilla = {}
    vanilla_functions = set()
    script_actions = {}
    overlay_actions = {}
    possible_random_actions = []

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
                            overlay_actions.setdefault(name, []).append((overlay_name, body))
                            valid_functions.add(name)
                        else:
                            for _ in range(times):
                                if kind == "script":
                                    script_actions.setdefault(name, []).append(base_cmd)
                                    valid_functions.add(name)
                                elif kind == "rcon":
                                    rcon_only_actions.setdefault(name, []).append(base_cmd)
                                    valid_functions.add(name)
                                elif kind == "vanilla":
                                    collected_vanilla.setdefault(name, []).append(base_cmd)
                                    valid_functions.add(name)
                                    vanilla_functions.add(name)

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

        # =============================================================
        # === Build possible_random_actions (safe pool for $random) ===
        # =============================================================
        exclude = set(RANDOM_TRIGGER_BLACKLIST)
        random_sources = {n for n, acts in script_actions.items() if "random" in acts}
        exclude |= random_sources
        # Base pool
        base_random_actions = [cmd for cmd in sorted(valid_functions) if cmd not in exclude]
        # === Apply whitelist / blacklist logic ===
        # === Apply whitelist / blacklist logic with debug ===
        for cmd in base_random_actions:
            if RANDOM_TRIGGER_WHITELIST and cmd not in RANDOM_TRIGGER_WHITELIST:
                print(f"[RANDOM] {cmd} is not in the witelist, excluding from $random pool.")
            elif RANDOM_TRIGGER_BLACKLIST and cmd in RANDOM_TRIGGER_BLACKLIST:
                print(f"[RANDOM] {cmd} is in the blacklist, excluding from $random pool.")
            else:
                possible_random_actions.append(cmd)

        # Create ZIP archive
        zip_path = Path(DATAPACK_ROOT) / DATAPACK_NAME
        shutil.make_archive(str(zip_path), "zip", full_dp_path)

        # === Debug summary (commented out) ===
        #print("\n[TRIGGER OVERVIEW]")

        #print(f"\nTotal valid triggers ({len(valid_functions)}):")
        #for name in sorted(valid_functions):
            #print(f"  - {name}")

        #print(f"\nVanilla triggers ({len(vanilla_functions)}):")
        #for name in sorted(vanilla_functions):
            #print(f"  - {name}")

        #real_rcon = {n: cmds for n, cmds in rcon_only_actions.items() if cmds}
        #print(f"\nRCON-only Trigger ({len(real_rcon)}):")
        #for name in sorted(real_rcon.keys()):
            #print(f"  - {name} -> {real_rcon[name]}")

        #print(f"\nPossible $random actions ({len(possible_random_actions)}):")
        #for name in sorted(possible_random_actions):
            #print(f"  - {name}")

        #print("\nPossible script actions:")
        #for name in sorted(script_actions.keys()):
            #print(f"  - {name} -> {script_actions[name]}")

    except Exception as e:
        traceback.print_exc()
        print(f"[ERROR] Datapack build failed: {e}")

rcon_pool_lock = asyncio.Lock()
rcon_connection = None

# ================================
# RCON WORKER
# ================================
LAST_RCON_ATTEMPT = 0

async def rcon_worker():
    """Background worker that dequeues RCON commands and sends them to the Minecraft server."""
    global rcon_connection, LAST_RCON_ATTEMPT
    print("[RCON-QUEUE] Worker started.")
    while True:
        commands, source_user = await rcon_queue.get()
        
        if not QUEUE_ACTIVE:
            await asyncio.sleep(1)
            await rcon_queue.put((commands, source_user))
            rcon_queue.task_done()
            continue

        q_size = rcon_queue.qsize()
        wait_time = THROTTLE_TIME
        inner_pause = 0.01 
        
        # Dynamic throttling based on queue depth
        if q_size > 100:
            wait_time, inner_pause = 0.01, 0.001
        elif q_size > 50:
            wait_time, inner_pause = 0.05, 0.005
        elif q_size > 20:
            wait_time, inner_pause = 0.1, 0.01

        try:
            async with rcon_pool_lock:
                if rcon_connection is None:
                    now = time.time()
                    if now - LAST_RCON_ATTEMPT < 5:
                        raise ConnectionError("Reconnect cooldown active")
                    
                    LAST_RCON_ATTEMPT = now
                    try:
                        rcon_connection = await asyncio.wait_for(
                            asyncio.to_thread(lambda: MCRcon(MC_HOST, MC_PASS, port=MC_PORT)),
                            timeout=0.5
                        )
                        await asyncio.wait_for(
                            asyncio.to_thread(rcon_connection.connect),
                            timeout=0.5
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        rcon_connection = None
                        raise ConnectionError(f"Server unreachable: {e}")

                for cmd in commands:
                    await asyncio.to_thread(rcon_connection.command, cmd)
                    if inner_pause > 0:
                        await asyncio.sleep(inner_pause)

        except Exception as e:
            print(f"[RCON OFFLINE] {e}")
            rcon_connection = None
            await asyncio.sleep(5)
            try:
                await rcon_queue.put((commands, source_user))
            except Exception:
                print("RCON Queue Error") 

        finally:
            await asyncio.sleep(wait_time)
            rcon_queue.task_done()

async def execute_global_command(trigger_name: str, source_user: str, chain_depth: int = 0):
    """Resolves a trigger name into RCON commands and enqueues them."""
    name = sanitize_filename(trigger_name)
    
    if name not in valid_functions:
        return

    commands_to_send = []

    # When you add a built-in command also add it to _RESERVED_NAMES in hook_api.py to prevent overrides by other hooks
    if name in script_actions:
        for action in script_actions[name]:
            if action == "random" and possible_random_actions:
                chosen = random.choice(possible_random_actions)
                await execute_global_command(chosen, source_user, chain_depth)
            elif action == "random" and not possible_random_actions:
                print(f"[HOOK] [WARN] No possible actions available for $random trigger.")
            elif action in HOOK_ACTIONS:
                try:
                    _hook_api._current_depth = chain_depth
                    HOOK_ACTIONS[action](source_user, action, {})
                except Exception as e:
                    print(f"[HOOK] [WARN] Error in action '{action}': {e}")
            elif action:
                print(f"[HOOK] [WARN] Unknown script action: '{action}'") 

    # --- 0. OVERLAY TEXT ---
    # Allow {comment} as a placeholder for overlay text
    comment_text = None
    # If source_user is a dict, a comment text can be passed (for comment triggers)
    if isinstance(source_user, dict):
        comment_text = source_user.get('comment', '')
        user_display = source_user.get('user', '')
    else:
        user_display = source_user

    if name in overlay_actions:
        for overlay_name, raw_body in overlay_actions[name]:
            parts = raw_body.split("|")
            # {user} ersetzen
            title = parts[0].replace("{user}", user_display) if len(parts) > 0 else ""
            subtitle = parts[1].replace("{user}", user_display) if len(parts) > 1 else ""
            # {comment} ersetzen, falls vorhanden
            if comment_text is not None:
                title = title.replace("{comment}", comment_text)
                subtitle = subtitle.replace("{comment}", comment_text)
            try:
                duration = int(parts[2]) if len(parts) > 2 and parts[2].strip().isdigit() else 3
            except (ValueError, IndexError):
                duration = 3
            send_overlay_text(title, subtitle, duration, overlay_name)

    # --- 1. VANILLA COMMANDS ---
    if name in vanilla_functions:
        commands_to_send.append(f"execute as @a run function {NAMESPACE}:{name}")

    # --- 2. RCON-ONLY COMMANDS ---
    if name in rcon_only_actions:
        commands_to_send.extend(rcon_only_actions[name])

    if not commands_to_send:
        return

    # --- 3. ENQUEUE ---
    try:
        MAIN_LOOP.call_soon_threadsafe(rcon_queue.put_nowait, (commands_to_send, source_user))
        if rcon_queue.qsize() < 10: 
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
            item = await trigger_queue.get()
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
                trigger_queue.task_done()
        except Exception as e_outer:
            print(f"[TRIGGER-QUEUE LOOP ERROR] {e_outer}")
            await asyncio.sleep(0.1)  

# ==========================================
# HTTP actions loader
# ==========================================

def load_http_actions(file_path=HTTP_ACTIONS_FILE):
    """Loads all HTTP actions into memory at startup."""
    global http_actions_cache
    http_actions_cache = {}

    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_clean = line.split("#", 1)[0].strip()  # Strip comments
            if not line_clean or ":" not in line_clean:
                continue

            trigger_id, cmd = map(str.strip, line_clean.split(":", 1))
            http_actions_cache[trigger_id] = cmd

    print(f"[INFO] HTTP actions loaded: {len(http_actions_cache)} entries")

# ==========================================
# Webhook endpoint for MinecraftServerAPI
# ==========================================
@app.route('/webhook', methods=['POST'])
def handle_minecraft_events():
    global QUEUE_ACTIVE
    try:
        data = request.json
        if not data:
            return {"status": "no data"}, 400

        event = data.get("event")

        if event == "player_death":
            QUEUE_ACTIVE = False
            print("\n[STATUS] [DEAD] Player died! Queue PAUSED.")
        
        elif event == "player_respawn":
            QUEUE_ACTIVE = True
            print("\n[STATUS] [OK] Player respawned! Queue RESUMED.")

    except Exception as e:
        print(f"[ERROR] Webhook error: {e}")

    return {"status": "processed"}, 200

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

        # Accept int or str for trigger, convert int to str
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

        global DISABLE_TIKTOK_CONNECT
        # Special toggle: if trigger is 'tiktok', toggle TikTok connection
        if sanitized == "tiktok":
            DISABLE_TIKTOK_CONNECT = not DISABLE_TIKTOK_CONNECT
            print(f"[CUSTOM TRIGGER] TikTok connect toggled: {not DISABLE_TIKTOK_CONNECT} -> {DISABLE_TIKTOK_CONNECT}")
            return {"status": "ok", "message": f"TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT={DISABLE_TIKTOK_CONNECT}"}, 200

        if sanitized not in valid_functions:
            return {"status": "error", "message": f"Trigger '{sanitized}' does not exist or is not valid."}, 400

        if MAIN_LOOP is None:
            return {"status": "error", "message": "Bot event loop not ready yet."}, 503

        try:
            MAIN_LOOP.call_soon_threadsafe(trigger_queue.put_nowait, (sanitized, user))
        except asyncio.QueueFull:
            return {"status": "error", "message": "Trigger queue is full. Try again later."}, 503

        print(f"[CUSTOM TRIGGER] Injected: '{sanitized}' (user: {user})")
        return {"status": "ok", "trigger": sanitized, "user": user}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
# =========================================

# --- Start webhook server in its own thread ---
def run_signal_server():
    app.run(port=MCSERVER_API_PORT, debug=False, use_reloader=False)

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
    cmd = http_actions_cache.get(gift_id)
    if not cmd:
        return

    try:
        MAIN_LOOP.call_soon_threadsafe(asyncio.ensure_future, execute_http_command(cmd))
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
            delta_val = await likegoal_queue.get()
            try:
                url = f"http://127.0.0.1:{LIKE_GOAL_PORT}/update_likes?add={delta_val}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        pass
            except Exception:
                pass
            finally:
                likegoal_queue.task_done()

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
        enable = rule.get("enable", True)

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

def prepare_like_triggers(raw_triggers, valid_functions):
    prepared = []

    for rule in raw_triggers:
        if not rule["enable"]:
            continue

        if rule["function"] not in valid_functions:
            print(f"[CONFIG ERROR] Unknown function: {rule['function']}")
            continue

        prepared.append({
            "id": rule["id"],
            "every": rule["every"],
            "function": rule["function"],
            "payload": rule["payload"],
            "last_blocks": 0  # Track state per trigger
        })

    return prepared

def initialize_likes(total_likes):
    """Called once to set the initial like count baseline."""
    global start_likes
    with like_lock:
        if start_likes is None:
            start_likes = total_likes
            print(f"[LIKE] Initial count set: {start_likes}")
            return True
    return False

# =========================================
# Daily revenue logger
# =========================================

def update_daily_revenue():
    file_path = BASE_DIR.parent / "data" / "revenue_log.jsonl"
    today = datetime.now().strftime("%Y-%m-%d")
    new_entry = {
        "date": today,
        "estimated_revenue_usd": GIFT_VALUE_USD
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

    _connect_time = [None]  # Tracks when the live connection was established
    COMMENT_WARMUP_SECONDS = 1  # Ignore comments arriving within this window after connect

    # =========================
    # GIFT events
    # =========================
    @client.on(GiftEvent)
    def on_gift(event: GiftEvent):
        global GIFT_VALUE_USD
        try:
            # Combo gift: check if still streaking (intermediate update)
            if event.gift.combo:
                if getattr(event, 'streaking', False) == True:
                    try:
                        if event.streaking: return
                    except AttributeError:
                        pass    

                count = event.repeat_count
            else:
                count = 1

            gift_name = sanitize_filename(event.gift.name)
            gift_id = str(event.gift.id)

            GIFT_VALUE_USD += event.value

            # Execute associated HTTP action
            execute_gift_action(gift_id)

            # Check if this gift has a registered trigger
            target = None
            if gift_name in valid_functions:
                target = gift_name
            elif gift_id in valid_functions:
                target = gift_id

            if not target:
                return

            username = get_safe_username(event.user)

            # Enqueue commands for processing
            for _ in range(count):
                MAIN_LOOP.call_soon_threadsafe(trigger_queue.put_nowait, (target, username))

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
        if "follow" in valid_functions:
            MAIN_LOOP.call_soon_threadsafe(trigger_queue.put_nowait, ("follow", username))

    # =========================
    # LIKE events
    # =========================
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        global start_likes, last_likegoal_sent, last_likegoal_time
        # 1. Quick initialization check
        if start_likes is None:
            initialize_likes(event.total)
            return
        try:
            total_since_start = event.total - start_likes
            # 2. Critical section: trigger logic (thread-safe)
            with like_lock:
                for rule in LIKE_TRIGGERS:
                    every = rule["every"]
                    # Avoid division by zero or negative values
                    if every <= 0: continue
                    current_blocks = total_since_start // every
                    last_blocks = rule["last_blocks"]
                    if current_blocks > last_blocks:
                        diff = current_blocks - last_blocks
                        rule["last_blocks"] = current_blocks
                        # Enqueue trigger functions
                        print(f"[LIKE] Trigger '{rule['id']}' -> +{diff}")
                        # Push trigger functions into the queue
                        for _ in range(diff):
                            MAIN_LOOP.call_soon_threadsafe(
                                trigger_queue.put_nowait,
                                (rule["function"], rule["payload"])
                            )
            # 3. Likegoal logic (outside the lock, uses atomic values)
            now = time.time()
            delta = total_since_start - last_likegoal_sent
            if delta > 0 and (now - last_likegoal_time) >= LIKEGOAL_INTERVAL:
                try:
                    MAIN_LOOP.call_soon_threadsafe(likegoal_queue.put_nowait, delta)
                    last_likegoal_sent = total_since_start
                    last_likegoal_time = now
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
        if "join" in valid_functions:
            MAIN_LOOP.call_soon_threadsafe(trigger_queue.put_nowait, ("join", username))

    # =========================
    # COMMENT events
    # =========================
    @client.on(CommentEvent)
    def on_comment(event):
        # Skip the initial burst of historical comments TikTok sends on connect
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

        # --- Comment commands ---
        if COMMENT_CMD_ENABLE and COMMENT_CMD_PREFIX and comment_text.startswith(COMMENT_CMD_PREFIX):
            cmd_text = comment_text[len(COMMENT_CMD_PREFIX):].strip()
            if cmd_text:
                allowed = False
                if "all" in COMMENT_CMD_ROLES:
                    allowed = True
                elif "moderator" in COMMENT_CMD_ROLES and is_moderator:
                    allowed = True
                elif "superfan" in COMMENT_CMD_ROLES and is_super_fan:
                    allowed = True
                elif "fanclub" in COMMENT_CMD_ROLES and in_fanclub:
                    allowed = True

                if allowed:
                    base_cmd = cmd_text.split()[0].lower()
                    # Whitelist: if not empty, only commands whose first word is listed pass
                    if COMMENT_CMD_WHITELIST and base_cmd not in COMMENT_CMD_WHITELIST:
                        print(f"[COMMENT CMD] {username} tried '{cmd_text}' — '{base_cmd}' not in whitelist")
                    # Blacklist: if not empty, block commands whose first word is listed
                    elif COMMENT_CMD_BLACKLIST and base_cmd in COMMENT_CMD_BLACKLIST:
                        print(f"[COMMENT CMD] {username} tried '{cmd_text}' — '{base_cmd}' blocked by blacklist")
                    else:
                        print(f"[COMMENT CMD] {username} -> {cmd_text}")
                        MAIN_LOOP.call_soon_threadsafe(rcon_queue.put_nowait, ([cmd_text], username))
                else:
                    print(f"[COMMENT CMD] {username} has no permission (roles: {COMMENT_CMD_ROLES})")

        if "comment" in valid_functions:
            # For overlay: allow {comment} as a placeholder
            MAIN_LOOP.call_soon_threadsafe(trigger_queue.put_nowait, ("comment", {"user": username, "comment": comment_text}))

    # =========================
    # Share events
    # =========================
    @client.on(ShareEvent)
    def on_share(event):
        username = get_safe_username(event.user)
        if "share" in valid_functions:
            MAIN_LOOP.call_soon_threadsafe(trigger_queue.put_nowait, ("share", username))

    # =========================
    # Live end events
    # =========================
    @client.on(LiveEndEvent)
    def on_live_end(_):
        update_daily_revenue()
        print(f"[STATUS] Live ended for @{user}.")
        RUNTIME_PATH_SHUTDOWN.touch(exist_ok=True)

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
        await asyncio.sleep(AUTOSAVE_INTERVAL_SECONDS)
        update_daily_revenue()

# ==========================================
# MAIN ENTRY POINT
# ==========================================

async def run_bot():
    """Main async loop: initializes config, builds the datapack,
    starts all workers, and connects to TikTok Live."""
    global MAIN_LOOP, LIKE_TRIGGERS
    MAIN_LOOP = asyncio.get_running_loop()
    
    load_config()

    # Validate actions.mca before proceeding
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
    LIKE_TRIGGERS = prepare_like_triggers(LIKE_TRIGGERS, valid_functions)
    load_http_actions()

    # Load event_hooks scripts ($-command handlers)
    global _hook_api
    EVENT_HOOKS_DIR = (BASE_DIR / ".." / "event_hooks").resolve()
    _hook_api = HookAPI(rcon_queue, trigger_queue, MAIN_LOOP, {}, valid_functions)
    load_event_hooks(_hook_api, EVENT_HOOKS_DIR)

    # Start all background workers
    asyncio.create_task(trigger_worker())
    asyncio.create_task(rcon_worker())
    asyncio.create_task(likegoal_worker())
    asyncio.create_task(gift_revenue_counter())

    while True:
        if DISABLE_TIKTOK_CONNECT:
            await asyncio.sleep(RECONNECT_DELAY)
            continue

        client = create_client(CONFIG_TIKTOK_USER)

        try:
            print(f"[*] Connecting to @{CONFIG_TIKTOK_USER}...")
            # Run blocking TikTok client in a separate thread
            await asyncio.to_thread(client.run)

        except Exception as e:
            print("\n" + "="*50)
            print("CRITICAL ERROR IN TIKTOK CLIENT:")
            traceback.print_exc() 
            print("="*50 + "\n")

            error_str = str(e)
            print(f"[..] Connection lost: {error_str}")

            if "DEVICE_BLOCKED" in error_str or "200" in error_str:
                print("[FAIL] TikTok block active (DEVICE_BLOCKED).")
                print("[TIP] Wait 15 minutes or restart your router.")
                await asyncio.sleep(900)
            else:
                print(f"[..] Reconnect in {RECONNECT_DELAY}s...")
                await asyncio.sleep(RECONNECT_DELAY)

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