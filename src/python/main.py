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

import asyncio
import concurrent.futures
import datetime
import ipaddress
import json
import logging
import os
import queue
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, request
from mcrcon import MCRcon
from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent,
    FollowEvent,
    GiftEvent,
    JoinEvent,
    LikeEvent,
    LiveEndEvent,
    ShareEvent,
)

from core.api.services.datapack import sync_datapack
from core.config_lock import read_config_version
from core.crash_manager import get_crash_manager
from core.error_codes import (
    HOOK_0006,
    MC_0004,
    MC_0006,
    TIKTOK_0001,
    TIKTOK_0002,
    TIKTOK_0003,
    TIKTOK_0004,
    TIKTOK_0005,
)
from core.health_monitor import HealthState, get_health_monitor
from core.hook_api import HOOK_ACTIONS, HookAPI, HookContext
from core.hook_loader import (
    fire_hook_event,
    fire_hook_lifecycle,
    load_event_hooks,
    reload_event_hooks,
)
from core.logger import (
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
    start_heartbeat,
)
from core.mca_parser import parse_mca
from core.overlay_utils import send_overlay_text
from core.paths import get_base_dir, get_runtime_dir
from core.tiktok_chatbot import get_chatbot
from core.validator import Severity, print_diagnostics, validate_file
from core.yaml_utils import load_yaml

log = initialize_logging(__name__)

if os.environ.get("TIKTOK2MC_DEBUG"):  # troubleshooting: unveil TikTokLive internals
    for _dbg_name in (
        "TikTokLive",
        "TikTokLive.web",
        "TikTokLive.ws",
        "python.main",
        "core.tiktok_chatbot",
    ):
        logging.getLogger(_dbg_name).setLevel(logging.DEBUG)
    try:
        # TikTokLive 6.6.x resets its logger to ERROR inside TikTokLiveClient.__init__
        # via TikTokLiveLogHandler.get_logger(level=...). Force DEBUG at the source.
        from TikTokLive.client.logger import LogLevel, TikTokLiveLogHandler

        _orig_get_logger = TikTokLiveLogHandler.get_logger

        @classmethod
        def _force_debug_get_logger(cls, level=None, stream=None):
            return _orig_get_logger.__func__(cls, LogLevel.DEBUG, stream)

        TikTokLiveLogHandler.get_logger = _force_debug_get_logger
    except Exception:
        pass
    log.info("[DEBUG] TIKTOK2MC_DEBUG=1 — TikTokLive debug logging enabled")


# ==========================================
# CONFIGURATION & PATHS
# ==========================================

BASE_DIR = get_base_dir()


# Debug/sandbox override for tests and troubleshooting (see tools/bridge_debug.py):
#   TIKTOK2MC_BASE_PARENT  — replaces BASE_DIR.parent, i.e. where "config/" and
#                           "data/" live. Lets the bridge run fully inside a
#                           disposable sandbox dir without touching the real
#                           repo config/data.
#   TIKTOK2MC_RUNTIME_DIR  — overrides the runtime signal files dir.
# Both are opt-in; with them unset the behaviour is byte-identical to before.
def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).resolve() if value else None


_BASE_PARENT = _env_path("TIKTOK2MC_BASE_PARENT") or BASE_DIR.parent
CONFIG_FILE = (_BASE_PARENT / "config" / "config.yaml").resolve()
ACTIONS_FILE = (_BASE_PARENT / "data" / "actions.mca").resolve()
COMMENT_COMMANDS_FILE = (_BASE_PARENT / "data" / "comment_commands.yaml").resolve()
FOLLOWED_USERS_FILE = (_BASE_PARENT / "data" / "followed_users.txt").resolve()
_RUNTIME_DIR_ENV = _env_path("TIKTOK2MC_RUNTIME_DIR")
RUNTIME_DIR = _RUNTIME_DIR_ENV or get_runtime_dir()
RELOAD_CONFIG_SIGNAL = (RUNTIME_DIR / "reload_config").resolve()
RELOAD_ACTIONS_SIGNAL = (RUNTIME_DIR / "reload_actions").resolve()
RELOAD_COMMENT_COMMANDS_SIGNAL = (RUNTIME_DIR / "reload_comment_commands").resolve()
RELOAD_CHATBOT_SIGNAL = (RUNTIME_DIR / "reload_chatbot").resolve()
RELOAD_HOOKS_SIGNAL = (RUNTIME_DIR / "reload_hooks").resolve()

_last_config_version: int = 0


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
        self.actions_valid = True
        self.start_likes = None
        self._last_like_total = None
        self._last_like_event = 0.0
        self.like_triggers: list[dict] = []

        # TikTok event diagnostics (raw-received counter + stall watchdog)
        self._last_tiktok_event_ts = 0.0
        self._tiktok_event_counters: dict[str, int] = {}
        self.valid_functions = set()
        self.vanilla_functions = set()
        self.shell_actions_cache = {}
        self.shell_tasks: set[asyncio.Task] = set()
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
        self.tiktok_client_loop = None
        self.tiktok_live = False

        # Gift tracking
        self.gift_value_usd = 0
        self.gift_day_start_value = 0
        self.gift_current_log_date = None

        # Session tracking (reset on each live connection)
        self.session_start_ts = None
        self.session_gifts = 0
        self.session_gift_value_usd = 0.0
        self.session_likes = 0
        self.session_follows = 0
        self.session_comments = 0
        self.session_shares = 0
        self.session_joins = 0
        self.session_end_ts = None

        # Runtime
        self.main_loop = None
        self.hook_api = None
        self.queue_active = True
        self.queue_pause_on_death = True
        self.config = {}
        self.runtime_path_shutdown = (
            (_RUNTIME_DIR_ENV / "shutdown").resolve()
            if _RUNTIME_DIR_ENV
            else (BASE_DIR / "runtime" / "shutdown").resolve()
        )

        # RCON retry tracking (keyed by repr(commands) to limit re-queue loops)
        self.max_rcon_retries = 3
        self.rcon_queue_retries: dict[str, int] = {}
        # Global outage budget: once this many consecutive failures occur,
        # failed commands are dropped instead of re-queued (prevents flooding).
        self.rcon_consecutive_failures = 0
        self.rcon_global_retry_budget = 5


ctx = BotContext()

app = Flask(__name__)

_LOCALHOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _webhook_request_authorized() -> bool:
    """Gate bridge webhook endpoints behind the configured API key.

    Mirrors the control plane (core/api/server.py): when an api_key is
    configured, all non-localhost requests must present it in the
    ``X-API-Key`` header.  Localhost stays exempt so local plugins and
    desktop-app integrations keep working without a key.  When no key is
    configured, authentication is disabled entirely.
    """
    remote = request.remote_addr or ""
    if remote in _LOCALHOSTS:
        return True
    api_key = (ctx.config or {}).get("api_key", "")
    if not api_key:
        return True
    return secrets.compare_digest(request.headers.get("X-API-Key", ""), api_key)


def _bridge_auth_check():
    if not _webhook_request_authorized():
        return {
            "status": "error",
            "message": "Unauthorized. Provide X-API-Key header.",
        }, 401


def _same_host_origin(origin: str, host: str) -> bool:
    """True when an Origin's netloc matches the request Host.

    Mirrors core/api/server.py (_same_host_origin).
    """
    if not origin or not host:
        return False
    try:
        parsed = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return parsed.netloc == host


def _is_local_machine_host(hostname: str | None) -> bool:
    """Whether a Host-header name refers to this machine.

    Mirrors core/api/server.py (_is_local_machine_host): loopback names
    and any IP literal pass; DNS names only when they are this machine's
    own hostname (detects DNS rebinding to 127.0.0.1).
    """
    if not hostname:
        return False
    if hostname in _LOCALHOSTS:
        return True
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return True
    return hostname.lower() == socket.gethostname().lower()


def _bridge_origin_check():
    """Reject browser requests that did not originate from a local client.

    Mirrors LocalOriginGuardMiddleware (core/api/server.py). A malicious
    web page can fire cross-site POSTs at http://127.0.0.1:29188 — such
    requests carry a foreign Origin header (and/or Sec-Fetch-Site:
    cross-site) and are rejected with 403 before any side effect runs.
    DNS-rebound requests arrive from localhost but with the attacker's
    hostname in the Host header. Non-browser clients (the control plane,
    plugins, curl) send neither header and are unaffected.
    """
    origin = request.headers.get("origin")
    if origin is not None and not _same_host_origin(origin, request.host):
        return {
            "status": "error",
            "message": "Cross-origin request rejected.",
        }, 403

    if request.headers.get("sec-fetch-site") == "cross-site":
        return {
            "status": "error",
            "message": "Cross-site request rejected.",
        }, 403

    if request.remote_addr in _LOCALHOSTS:
        hostname = (
            urllib.parse.urlsplit(f"//{request.host}").hostname
            if request.host
            else None
        )
        if not _is_local_machine_host(hostname):
            return {
                "status": "error",
                "message": "Invalid Host header.",
            }, 403

    return None


app.before_request(_bridge_auth_check)
app.before_request(_bridge_origin_check)

werkzeug_log = logging.getLogger("werkzeug")
werkzeug_log.setLevel(logging.WARNING)

_RE_ERR_CODE_200 = re.compile(r"\berr_code\b.*?\b200\b", re.IGNORECASE)

_BACKGROUND_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None
_BACKGROUND_EXECUTOR_LOCK = threading.Lock()


def _get_background_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Return the shared executor for fire-and-forget background work.

    Lazily created so no threads spawn unless a background job is actually
    submitted, and the bridge stays importable in tests.
    """
    global _BACKGROUND_EXECUTOR
    if _BACKGROUND_EXECUTOR is None:
        with _BACKGROUND_EXECUTOR_LOCK:
            if _BACKGROUND_EXECUTOR is None:
                _BACKGROUND_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="bridge-bg"
                )
    return _BACKGROUND_EXECUTOR


def _run_in_background(fn, *args):
    """Submit ``fn(*args)`` to the shared background executor (fire-and-forget).

    Keeps blocking network/file work off the asyncio loops and the TikTok
    client thread.  ``fn`` is responsible for its own error handling.
    """
    try:
        _get_background_executor().submit(fn, *args)
    except RuntimeError as exc:  # executor shut down during bridge shutdown
        log.warning("[BACKGROUND] Job dropped, executor unavailable: %s", exc)


# ==========================================
# SETUP & HELPER FUNCTIONS
# ==========================================


def _put_nowait_guarded(queue: asyncio.Queue, item: object, label: str) -> None:
    """Put an item on a bounded queue, catching ``QueueFull`` in the callback.

    ``call_soon_threadsafe(queue.put_nowait, ...)`` raises ``QueueFull`` inside
    the loop callback rather than in the calling thread, so a surrounding
    ``try/except asyncio.QueueFull`` never fires and drops are silently lost.
    This wrapper performs the put inside the callback so drops are logged.
    """
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        log.warning("[QUEUE] %s dropped — queue full", label)


def enqueue_threadsafe(
    item: object,
    *,
    queue: asyncio.Queue | None = None,
    label: str = "event",
) -> bool:
    """Schedule a bounded-queue put on the main loop.

    Used from TikTok event threads and the Flask webhook to push items into
    ``ctx.trigger_queue`` / ``ctx.rcon_queue``.  Returns ``True`` if the put
    was scheduled (the actual put may still be dropped and logged if the
    queue fills up in the meantime).
    """
    target = queue if queue is not None else ctx.trigger_queue
    loop = ctx.main_loop
    if loop is None:
        log.warning("[QUEUE] %s dropped — main loop not ready", label)
        return False
    try:
        loop.call_soon_threadsafe(_put_nowait_guarded, target, item, label)
        return True
    except RuntimeError:
        log.warning("[QUEUE] %s dropped — main loop not running", label)
        return False


def _make_hook_context(event: str, source: str = "tiktok", **extra) -> HookContext:
    """Build the structured hook-action context for a queued trigger.

    Hook handlers receive this context as their third argument
    (``fn(user, trigger, context)``). ``event`` is the trigger family
    ("gift", "follow", "like", "comment", "join", "share"), ``source``
    where the trigger originated ("tiktok", "webhook", "hook"). Extra
    keyword arguments are event-specific payload fields; ``None`` values
    are dropped so hooks can rely on present keys being meaningful.
    """
    data = HookContext(event=event, source=source)
    for key, value in extra.items():
        if value is not None:
            data[key] = value
    return data


def _unpack_trigger_item(item: tuple) -> tuple[str, str, int, HookContext]:
    """Normalize a trigger-queue item to ``(trigger, user, depth, context)``."""

    def _as_hook_context(context: object) -> HookContext:
        if isinstance(context, HookContext):
            return context
        if isinstance(context, dict):
            return HookContext(context)
        return HookContext()

    if len(item) == 4:
        trigger, source_user, chain_depth, context = item
        return (
            trigger,
            source_user if isinstance(source_user, str) else str(source_user),
            chain_depth,
            _as_hook_context(context),
        )
    if len(item) == 3:
        trigger, source_user, chain_depth = item
        return (
            trigger,
            source_user if isinstance(source_user, str) else str(source_user),
            chain_depth,
            HookContext(),
        )
    trigger, source_user = item
    return (
        trigger,
        source_user if isinstance(source_user, str) else str(source_user),
        0,
        HookContext(),
    )


def _validate_dup_cmd_config():
    """Validate raw YAML for duplicate keys in commands_config sections.

    Raises ``ValueError`` if duplicates are found so callers can decide
    whether to exit the process or simply abort a runtime reload.
    """
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
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
                    log.error(
                        f"command_config: Command '{key}' configured multiple times! (line {j + 1}, first at line {seen[key]})"
                    )
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
    ctx.queue_pause_on_death = bool(
        config.get("minecraft_server_api", {}).get("queue_pause_on_death", True)
    )
    ctx.autosave_interval_seconds = config.get("tiktok", {}).get(
        "autosave_interval_seconds", 60
    )

    ft_cfg = config.get("tiktok", {}).get("follow_tracking", {})
    ctx.follow_tracking_mode = str(ft_cfg.get("mode", "all_time")).lower()
    raw_path = str(ft_cfg.get("file", "data/followed_users.txt"))
    ctx.follow_tracking_file = (_BASE_PARENT / raw_path).resolve()
    ctx._followed_cache = set()
    if ctx.follow_tracking_file.exists():
        with open(ctx.follow_tracking_file, "r", encoding="utf-8") as f:
            ctx._followed_cache = {line.strip().lower() for line in f if line.strip()}
        log.info(
            f"[CONFIG] Follow tracking ({ctx.follow_tracking_mode}): {len(ctx._followed_cache)} known followers loaded"
        )
    if ctx.follow_tracking_mode == "per_stream":
        ctx.follow_tracking_file.write_text("")
        ctx._followed_cache.clear()
        log.info("[CONFIG] Follow tracking mode 'per_stream' — follower list reset")

    ctx.like_triggers = validate_like_triggers(
        config.get("like_triggers", config.get("tiktok", {}).get("like_triggers", []))
    )

    _apply_comment_commands_from_yaml()

    ctx.datapack_root = (_BASE_PARENT / "server" / "datapack").resolve()
    ctx.datapack_root.mkdir(parents=True, exist_ok=True)


def _apply_comment_commands_from_yaml() -> None:
    """Load comment_commands from data/comment_commands.yaml into BotContext."""
    if not COMMENT_COMMANDS_FILE.exists():
        ctx.comment_cmd_enable = False
        ctx.comment_cmd_groups = []
        ctx.comment_cmd_all_prefixes = set()
        return

    try:
        cc_cfg = load_yaml(COMMENT_COMMANDS_FILE).get("comment_commands", {})
    except Exception as e:
        log.error("[CONFIG] Failed to load comment_commands.yaml: %s", e)
        ctx.comment_cmd_enable = False
        ctx.comment_cmd_groups = []
        ctx.comment_cmd_all_prefixes = set()
        return

    ctx.comment_cmd_enable = bool(cc_cfg.get("enabled", False))
    ctx.comment_cmd_global_cooldown = max(0, int(cc_cfg.get("cooldown", 0)))
    ctx.comment_cmd_global_user_cooldown = max(0, int(cc_cfg.get("user_cooldown", 0)))
    raw_groups = cc_cfg.get("groups", [])
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
            log.warning(
                f"comment_commands: duplicate prefix '{prefix}' — keeping only first definition, skipping duplicate"
            )
            continue
        seen_prefixes.add(prefix)
        raw_roles = g.get("allowed_roles", ["moderator"])
        roles = (
            [str(r).strip().lower() for r in raw_roles if str(r).strip()]
            if isinstance(raw_roles, list)
            else ["moderator"]
        )
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
                                log.warning(
                                    f"comment_commands group '{prefix}': '{cname}' listed multiple times in commands"
                                )
                        seen_cmd.add(cname)
                        commands.append(cname)
        if dup_warn_count > dup_warn_max:
            remaining = dup_warn_count - dup_warn_max
            log.warning(
                f"comment_commands group '{prefix}': {remaining} further duplicate command warnings suppressed"
            )
        commands_config = {}
        raw_config = g.get("commands_config", {})
        if isinstance(raw_config, dict):
            for cname, ccfg in raw_config.items():
                cname = cname.strip().lower()
                if cname and isinstance(ccfg, dict):
                    commands_config[cname] = ccfg
        handler = str(g.get("handler", "rcon")).lower()
        plugin_name = str(g.get("plugin_name", "")).strip()
        url = str(g.get("url", ""))
        cooldown = max(0, int(g.get("cooldown", 0)))
        user_cooldown = max(0, int(g.get("user_cooldown", 0)))
        if mode == "allow-all" and not commands and handler == "rcon":
            log.warning(
                f"comment_commands group '{prefix}': allow-all + empty list — ALL commands allowed!"
            )
        if handler == "plugin" and not plugin_name:
            log.warning(
                f"comment_commands group '{prefix}': handler is 'plugin' but plugin_name is empty — group will be ignored"
            )
        trigger_comment = g.get("trigger_comment_event", True)

        cmd_warn_count = 0
        cmd_warn_max = 5
        for cname in commands_config:
            if mode == "deny-all" and cname not in commands:
                cmd_warn_count += 1
                if cmd_warn_count <= cmd_warn_max:
                    log.warning(
                        f"comment_commands group '{prefix}': '{cname}' in commands_config but NOT in commands list (deny-all) — will never match"
                    )
            elif mode == "allow-all" and cname in commands:
                cmd_warn_count += 1
                if cmd_warn_count <= cmd_warn_max:
                    log.warning(
                        f"comment_commands group '{prefix}': '{cname}' in commands_config AND in commands list (allow-all) — blocked by mode"
                    )
        if cmd_warn_count > cmd_warn_max:
            remaining = cmd_warn_count - cmd_warn_max
            log.warning(
                f"comment_commands group '{prefix}': {remaining} further command config warnings suppressed"
            )

        ctx.comment_cmd_groups.append(
            {
                "prefix": prefix,
                "roles": roles,
                "mode": mode,
                "commands": commands,
                "commands_config": commands_config,
                "handler": handler,
                "plugin_name": plugin_name,
                "url": url,
                "cooldown": cooldown,
                "user_cooldown": user_cooldown,
                "trigger_comment_event": trigger_comment,
            }
        )


def load_config():
    """Loads configuration values from the YAML config file."""
    global _last_config_version
    if not CONFIG_FILE.exists():
        log.error(f"Config not found: {CONFIG_FILE}")
        return False

    _check_dup_cmd_config()

    try:
        config = load_yaml(CONFIG_FILE)
        _apply_config(config)
        _last_config_version = read_config_version(CONFIG_FILE)
        return True
    except Exception as e:  # malformed user config must not crash the bridge
        log.error(f"Config error: {e}")
        return False


def sanitize_filename(name):
    """Returns a Minecraft-safe name (only a-z, 0-9, _, -)."""
    name = str(name).lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_-]", "", name)


def mc_safe_name(user: str) -> str:
    """Sanitize a TikTok username/nickname for use inside MC/RCON commands.

    unique_ids are [A-Za-z0-9._] and pass through unchanged; nicknames may
    contain spaces, quotes or control characters that would shift command
    arguments or break JSON text components when substituted into {user}.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(user))[:30]


def generate_datapack():
    """Generates datapack files for vanilla commands and stores
    plugin/script commands separately.
    Supported command prefixes: '!' (RCON), '$' (script), '/' (vanilla), '&' (shell).
    Multiplier ' xN' applies to all types.
    """
    log.info(f"\n[BUILD] Generating datapack in: {ctx.datapack_root}")

    try:
        ctx.datapack_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.error(
            f"[BUILD] Cannot create datapack root directory {ctx.datapack_root}: {e}"
        )
        return

    full_dp_path = ctx.datapack_root / ctx.datapack_name
    functions_path = full_dp_path / "data" / ctx.namespace / "function"

    # Reset state — build into locals and swap atomically at the end so
    # readers on the main loop never observe a half-rebuilt snapshot.
    rcon_only_actions: dict[str, list[str]] = {}
    valid_functions: set[str] = set()
    collected_vanilla: dict[str, list[str]] = {}
    vanilla_functions: set[str] = set()
    script_actions: dict[str, list[str]] = {}
    overlay_actions: dict[str, list[tuple[str, str]]] = {}
    shell_actions_cache: dict[str, list[str]] = {}

    # Prepare filesystem
    try:
        if full_dp_path.exists():
            shutil.rmtree(full_dp_path)
        functions_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.error(f"Failed to create datapack directory: {e}")
        return

    try:
        # === Parse actions.mca (shared parser: core.mca_parser) ===
        if ACTIONS_FILE.exists():
            parsed = parse_mca(ACTIONS_FILE.read_text(encoding="utf-8"))
            for diag in parsed.diagnostics:
                log.warning(f"[BUILD] actions.mca line {diag.line + 1}: {diag.message}")
            for trig in parsed.triggers:
                if not trig.enabled:
                    continue
                name = sanitize_filename(trig.raw_name)
                if not name:
                    continue

                for cmd in trig.commands:
                    if cmd.type in ("overlay", "named_overlay"):
                        overlay_actions.setdefault(name, []).append(
                            (cmd.overlay_name, cmd.body)
                        )
                        valid_functions.add(name)
                        continue

                    if cmd.dynamic_vanilla:
                        # dynamic vanilla via RCON: keep {user} literal, route to RCON
                        base_cmd = cmd.body
                        target = rcon_only_actions
                    elif cmd.type == "shell":
                        # shell commands keep the raw body (do not replace {user})
                        base_cmd = cmd.body
                        target = shell_actions_cache
                    elif cmd.type == "script":
                        base_cmd = cmd.body.replace("{user}", "@a")
                        target = script_actions
                    elif cmd.type == "rcon":
                        base_cmd = cmd.body.replace("{user}", "@a")
                        target = rcon_only_actions
                    elif cmd.type == "vanilla":
                        base_cmd = cmd.body.replace("{user}", "@a")
                        target = collected_vanilla
                        vanilla_functions.add(name)
                    else:
                        log.error(
                            f"[BUILD] Unhandled command type '{cmd.type}' on "
                            f"trigger '{trig.raw_name}'"
                        )
                        continue

                    for _ in range(max(cmd.multiplier, 1)):
                        target.setdefault(name, []).append(base_cmd)
                    valid_functions.add(name)

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
            f.write(
                '{"pack": {"pack_format": 15, "description": "TikTok Streaming Tool"}}'
            )

        # Create ZIP archive
        zip_path = Path(ctx.datapack_root) / ctx.datapack_name
        shutil.make_archive(str(zip_path), "zip", full_dp_path)

        # Publish the new snapshot atomically.
        ctx.rcon_only_actions = rcon_only_actions
        ctx.valid_functions = valid_functions
        ctx.vanilla_functions = vanilla_functions
        ctx.script_actions = script_actions
        ctx.overlay_actions = overlay_actions
        ctx.shell_actions_cache = shell_actions_cache

    except Exception as e:  # datapack build errors are logged; bridge keeps running
        log.exception("Datapack build failed")


# ================================
# RCON WORKER
# ================================


def _requeue_rcon(commands, source_user) -> None:
    """Re-queue a failed RCON command without ever blocking the worker.

    ``await asyncio.Queue.put`` is a deadlock hazard here: the worker is the
    only consumer of the bounded ``rcon_queue``, so a full queue would leave
    the worker stuck in ``put`` with nobody left to drain it.  Producers
    already drop on full (``enqueue_threadsafe``), so the worker must do the
    same via the guarded ``put_nowait``.
    """
    _put_nowait_guarded(ctx.rcon_queue, (commands, source_user), "rcon_requeue")


async def rcon_worker():
    """Background worker that dequeues RCON commands and sends them to the Minecraft server."""
    log.info("[RCON-QUEUE] Worker started.")
    while True:
        wait_time = ctx.throttle_time
        commands, source_user = await ctx.rcon_queue.get()
        try:
            if not ctx.queue_active:
                retry_key = f"queue_active_{(commands, source_user)!r}"
                retries = ctx.rcon_queue_retries.get(retry_key, 0) + 1
                if retries <= ctx.max_rcon_retries:
                    ctx.rcon_queue_retries[retry_key] = retries
                    _requeue_rcon(commands, source_user)
                else:
                    log.info(
                        f"[RCON] Dropping commands after queue inactive for {retries} attempts: {commands}"
                    )
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
                            asyncio.to_thread(
                                lambda: MCRcon(
                                    ctx.mc_host, ctx.mc_pass, port=ctx.mc_port
                                )
                            ),
                            timeout=3.0,
                        )
                        await asyncio.wait_for(
                            asyncio.to_thread(ctx.rcon_connection.connect), timeout=3.0
                        )
                    except (OSError, TimeoutError, ConnectionError) as e:
                        ctx.rcon_connection = None
                        raise ConnectionError(f"Server unreachable: {e}")

                for cmd in commands:
                    await asyncio.to_thread(ctx.rcon_connection.command, cmd)
                    if inner_pause > 0:
                        await asyncio.sleep(inner_pause)

                # Connection works again: reset retry counters and budget.
                ctx.rcon_consecutive_failures = 0
                ctx.rcon_queue_retries.clear()

        except (
            Exception
        ) as e:  # background worker must keep running; commands re-queued
            log.warning(f"[RCON OFFLINE] {e}")
            ctx.rcon_connection = None
            get_crash_manager().report_exception(
                MC_0004, exc=e, context_info={"source": "rcon_worker"}
            )
            await asyncio.sleep(5)
            ctx.rcon_consecutive_failures += 1
            retry_key = repr((commands, source_user))
            if ctx.rcon_consecutive_failures > ctx.rcon_global_retry_budget:
                log.error(
                    f"[RCON] Global retry budget exhausted — dropping: {commands}"
                )
                get_crash_manager().report_error(
                    MC_0006, detail=f"Outage budget exhausted: {commands}"
                )
                ctx.rcon_queue_retries.pop(retry_key, None)
            else:
                retries = ctx.rcon_queue_retries.get(retry_key, 0) + 1
                if retries <= ctx.max_rcon_retries:
                    ctx.rcon_queue_retries[retry_key] = retries
                    _requeue_rcon(commands, source_user)
                else:
                    log.error(
                        f"[RCON] Dropping commands after {retries} failed attempts: {commands}"
                    )
                    get_crash_manager().report_error(
                        MC_0006, detail=f"After {retries} attempts: {commands}"
                    )
                    ctx.rcon_queue_retries.pop(retry_key, None)
            await asyncio.sleep(wait_time)
            continue
        finally:
            ctx.rcon_queue.task_done()
            await asyncio.sleep(wait_time)


async def execute_global_command(
    trigger_name: str,
    source_user: str,
    chain_depth: int = 0,
    context: HookContext | dict | None = None,
):
    """Resolves a trigger name into RCON commands and enqueues them.

    ``source_user`` is always the plain username string; event payloads
    (e.g. the comment text) live in the structured ``context`` built by
    the event source (see :func:`_make_hook_context`). The context is
    passed unchanged to every hook action of the chain as the third
    handler argument. ``chain_depth`` stays internal queue/loop-guard
    machinery and is not exposed to hooks.
    """
    name = sanitize_filename(trigger_name)

    user_display = source_user

    # Structured context for hook actions. Always a fresh HookContext — the
    # caller's context object may be shared across several queued copies of
    # this trigger (e.g. combo gifts enqueue one item per gift) and must
    # never be mutated during dispatch. The comment text for {comment}
    # overlay placeholders also comes from here.
    hook_context = HookContext(context) if isinstance(context, dict) else HookContext()
    comment_text: str | None = hook_context.get("comment")

    commands_to_send = []

    if name in ctx.script_actions:
        vetoed_by: str | None = None
        for action in ctx.script_actions[name]:
            if action in HOOK_ACTIONS:
                try:
                    ctx.hook_api.set_depth(chain_depth)
                    # Hook actions are sync callables that may block (plugin
                    # I/O); run them on the executor so script triggers never
                    # stall the main loop.
                    result = await asyncio.to_thread(
                        HOOK_ACTIONS[action], source_user, action, hook_context
                    )
                    # Veto contract: a hook returning False aborts the rest of
                    # this trigger's chain — later hooks, overlays, vanilla,
                    # RCON and shell actions are all skipped. Returning True
                    # or None (the default) continues as before.
                    if result is False:
                        vetoed_by = action
                        break
                except (
                    Exception
                ) as e:  # third-party hook action must not crash the bridge
                    log.warning(f"[HOOK] Error in action '{action}': {e}")
                    get_crash_manager().report_exception(
                        HOOK_0006,
                        exc=e,
                        context_info={"action": action, "trigger": trigger_name},
                    )
            elif action:
                log.warning(f"[HOOK] Unknown script action: '{action}'")

        if vetoed_by is not None:
            log.info(f"[HOOK] Trigger '{trigger_name}' vetoed by action '{vetoed_by}'")
            return

    # --- 0. OVERLAY TEXT ---

    if name in ctx.overlay_actions:
        for overlay_name, raw_body in ctx.overlay_actions[name]:
            parts = raw_body.split("|")
            title = parts[0].replace("{user}", user_display) if len(parts) > 0 else ""
            subtitle = (
                parts[1].replace("{user}", user_display) if len(parts) > 1 else ""
            )
            if comment_text is not None:
                title = title.replace("{comment}", comment_text)
                subtitle = subtitle.replace("{comment}", comment_text)
            try:
                duration = (
                    int(parts[2])
                    if len(parts) > 2 and parts[2].strip().isdigit()
                    else 3
                )
            except (ValueError, IndexError):
                duration = 3
            # Offload the blocking overlay HTTP POST so a slow/unreachable
            # API cannot stall the whole trigger worker.
            await asyncio.to_thread(
                send_overlay_text, title, subtitle, duration, overlay_name
            )

    # --- 1. VANILLA COMMANDS ---
    if name in ctx.vanilla_functions:
        commands_to_send.append(f"execute as @a run function {ctx.namespace}:{name}")

    # --- 2. RCON-ONLY COMMANDS ---
    if name in ctx.rcon_only_actions:
        for cmd in ctx.rcon_only_actions[name]:
            # Substitute {user} placeholder for dynamic vanilla/RCON commands.
            # Sanitized: a nickname with spaces/quotes must not shift
            # arguments or break JSON components on the server.
            if "{user}" in cmd and user_display:
                cmd = cmd.replace("{user}", mc_safe_name(user_display))
            commands_to_send.append(cmd)

    # --- 3. SHELL COMMANDS ---
    if name in ctx.shell_actions_cache:
        cmds = ctx.shell_actions_cache[name]
        if cmds:
            # Store task reference to prevent silent exception loss
            task = asyncio.create_task(execute_shell_commands(cmds))
            ctx.shell_tasks.add(task)
            task.add_done_callback(ctx.shell_tasks.discard)

    if not commands_to_send:
        return

    # --- 4. ENQUEUE ---
    def _enqueue():
        try:
            ctx.rcon_queue.put_nowait((commands_to_send, source_user))
        except asyncio.QueueFull:
            log.warning(f"[RCON-QUEUE FULL] Trigger {name} dropped!")

    ctx.main_loop.call_soon_threadsafe(_enqueue)
    if ctx.rcon_queue.qsize() < 10:
        log.info(
            f"[ACTION] Trigger: {name} | Commands: {len(commands_to_send)} (for {source_user}) enqueued."
        )


# ================================
# TRIGGER WORKER
# ================================
async def trigger_worker():
    """Processes TikTok events from the trigger queue and converts them into RCON commands."""
    log.info("[TRIGGER-QUEUE] Worker started.")
    while True:
        try:
            item = await ctx.trigger_queue.get()
            trigger, source_user, chain_depth, hook_context = _unpack_trigger_item(item)
            try:
                await execute_global_command(
                    trigger, source_user, chain_depth, hook_context
                )
            except Exception as e:  # a failing trigger must not kill the worker
                log.error(
                    f"[TRIGGER WORKER ERROR] Error processing {trigger}/{source_user}: {e}"
                )
                get_crash_manager().report_exception(
                    TIKTOK_0005,
                    exc=e,
                    context_info={"trigger": trigger, "user": str(source_user)},
                )
            finally:
                ctx.trigger_queue.task_done()
        except Exception as e_outer:  # worker loop must never die
            log.error(f"[TRIGGER-QUEUE LOOP ERROR] {e_outer}")
            get_crash_manager().report_exception(
                TIKTOK_0005, exc=e_outer, context_info={"source": "trigger_queue_loop"}
            )
            await asyncio.sleep(0.1)


# Central API base URL. The supervisor exports RESOLVED_PORT_API_PORT when
# the port scanner had to relocate the API — honour it like the webhook
# port above instead of assuming the default.
API_BASE = "http://127.0.0.1:{}/api/v1".format(
    os.environ.get("RESOLVED_PORT_API_PORT", "29185")
)


# ==========================================
# EventBus publisher
# ==========================================
def _publish_event(event_type: str, event_data: dict) -> None:
    """Forward a Minecraft event to the central EventBus via API."""
    _run_in_background(_notify_hooks_of_event, event_type, dict(event_data))
    body = json.dumps({"type": event_type, "data": event_data}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/events",
            data=body,
            # Trusted-publisher marker: reserved core event families
            # (minecraft.*, tiktok.*) are rejected without it.
            headers={"Content-Type": "application/json", "X-T2M-Source": "bridge"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except (OSError, ValueError) as exc:
        log.warning("Failed to publish event '%s' to EventBus: %s", event_type, exc)
        get_crash_manager().report_exception(
            TIKTOK_0004,
            exc=exc,
            context_info={"event_type": event_type, "target": "eventbus_api"},
        )


@app.route("/health", methods=["GET"])
def handle_health():
    return {
        "status": "ok",
        "service": "bridge",
        "tiktok_disabled": ctx.disable_tiktok_connect,
    }, 200


@app.route("/metrics", methods=["GET"])
def handle_metrics():
    import time

    now = time.time()
    # Calculate events per minute (rolling window)
    # We track event counts in the last 60 seconds
    if not hasattr(handle_metrics, "_event_timestamps"):
        handle_metrics._event_timestamps = []
    # Clean old timestamps (older than 60 seconds)
    cutoff = now - 60
    handle_metrics._event_timestamps = [
        ts for ts in handle_metrics._event_timestamps if ts > cutoff
    ]
    events_per_minute = len(handle_metrics._event_timestamps)

    return {
        "rcon_queue_size": ctx.rcon_queue.qsize() if ctx.rcon_queue else 0,
        "trigger_queue_size": ctx.trigger_queue.qsize() if ctx.trigger_queue else 0,
        "events_per_minute": events_per_minute,
        "tiktok_connected": ctx.tiktok_client is not None and ctx.tiktok_live,
        "gift_value_usd_today": getattr(ctx, "gift_value_usd", 0)
        - getattr(ctx, "gift_day_start_value", 0),
        "gift_day_start_value": getattr(ctx, "gift_day_start_value", 0),
    }, 200


def _record_metrics_event():
    """Call this to record an event for metrics tracking."""
    import time

    now = time.time()
    if not hasattr(handle_metrics, "_event_timestamps"):
        handle_metrics._event_timestamps = []
    timestamps = handle_metrics._event_timestamps
    timestamps.append(now)
    # Prune here as well — GET /metrics may never be polled, and the list
    # would otherwise grow for the whole stream (likes alone can be
    # thousands per minute).
    if len(timestamps) > 10000 or len(timestamps) % 500 == 0:
        cutoff = now - 60
        handle_metrics._event_timestamps = [ts for ts in timestamps if ts > cutoff]


def _apply_mc_queue_semantics(event: str) -> None:
    """Apply Minecraft queue semantics for a webhook event.

    Pauses the TikTok command queue while the tracked player is dead and
    resumes it on respawn — but only when the user opted in via
    ``minecraft_server_api.queue_pause_on_death``. The webhook payload has
    no server identity, so this config gate scopes the behavior to the real
    Minecraft setup instead of any same-named event from a foreign game.
    """
    if event == "player_death" and ctx.queue_pause_on_death:
        ctx.queue_active = False
        log.info("\n[STATUS] [DEAD] Player died! Queue PAUSED.")
    elif event == "player_respawn" and ctx.queue_pause_on_death:
        ctx.queue_active = True
        log.info("\n[STATUS] [OK] Player respawned! Queue RESUMED.")


@app.route("/webhook", methods=["POST"])
def handle_minecraft_events():
    try:
        data = request.json
    except Exception as e:  # malformed webhook JSON returns 400
        log.error(f"Webhook invalid JSON: {e}")
        return {"status": "invalid json"}, 400

    if not data:
        return {"status": "no data"}, 400

    event = data.get("event")
    if not event:
        return {"status": "no event"}, 400

    # Minecraft queue semantics (config-gated, see _apply_mc_queue_semantics)
    _apply_mc_queue_semantics(event)

    # Publish every Minecraft event to the central EventBus generically.
    # Any plugin, hook, or the Event-Command Mapper can react without
    # hardcoded coupling.
    _publish_event(f"minecraft.{event}", dict(data))

    return {"status": "processed"}, 200


def _dispatch_comment_to_plugin(plugin_name: str, cmd_text: str, username: str) -> None:
    """Post a comment command to a plugin's command queue via the API."""
    url = f"{API_BASE}/plugins/{plugin_name}/command"
    body = json.dumps(
        {
            "command": "comment",
            "args": {"text": cmd_text, "username": username},
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
        log.debug("Routed '%s' to plugin '%s'", cmd_text, plugin_name)
    except (OSError, ValueError) as exc:
        log.warning("Failed to route comment to plugin '%s': %s", plugin_name, exc)


def _dispatch_comment_http(cmd_url, username, cmd_text):
    try:
        url = cmd_url.replace("{user}", urllib.parse.quote(username, safe=""))
        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
        req = urllib.request.Request(url, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except (OSError, ValueError) as e:
        log.warning(f"[COMMENT CMD] HTTP dispatch failed: {e}")
        get_crash_manager().report_exception(
            TIKTOK_0005,
            exc=e,
            context_info={"source": "_dispatch_comment_http", "url": cmd_url},
        )


def _dispatch_comment_http_sync(cmd_url, username, cmd_text):
    try:
        url = cmd_url.replace("{user}", urllib.parse.quote(username, safe=""))
        url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning(f"[COMMENT CMD] Conditional HTTP dispatch failed: {e}")
        return None


def _publish_tiktok_event(event_type: str, user: str, **extra):
    """Publish a TikTok event to the API-side EventBus.

    The API process owns the bus every consumer reads from (plugins via
    ECM / event_subscriptions, GUI live feed, live tracker), so events are
    forwarded there over HTTP — the same path used for ``tiktok.live_status``
    and ``minecraft.*`` webhook events.  Delivery is best-effort and runs in
    the shared background executor so trigger dispatch never blocks.
    """
    _record_metrics_event()
    data = {"user": user, **extra}
    _run_in_background(_notify_hooks_of_event, f"tiktok.{event_type}", data)
    body = json.dumps({"type": f"tiktok.{event_type}", "data": data}).encode("utf-8")
    _run_in_background(_post_tiktok_event_api, body)


def _publish_tiktok_status(connected: bool):
    """Report the TikTok live connection state to the API EventBus (GUI).

    Runs the HTTP POST in the shared background executor so callers on any
    asyncio loop (heartbeat) or the TikTok client thread never block on the
    network call.
    """
    data = {
        "connected": bool(connected),
        "disabled": bool(ctx.disable_tiktok_connect),
        "source": "tiktok_bridge",
    }
    _run_in_background(_notify_hooks_of_event, "tiktok.live_status", data)
    body = json.dumps({"type": "tiktok.live_status", "data": data}).encode("utf-8")
    _run_in_background(_post_tiktok_status, body)


def _post_tiktok_status(body: bytes) -> None:
    try:
        req = urllib.request.Request(
            f"{API_BASE}/events",
            data=body,
            headers={"Content-Type": "application/json", "X-T2M-Source": "bridge"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except (OSError, ValueError) as exc:
        log.warning("Failed to publish TikTok live status to EventBus: %s", exc)
        get_crash_manager().report_exception(
            TIKTOK_0004, exc=exc, context_info={"target": "eventbus_api_live_status"}
        )


def _post_tiktok_event_api(body: bytes) -> None:
    """Deliver a TikTok event body to the API-side EventBus (best-effort)."""
    try:
        req = urllib.request.Request(
            f"{API_BASE}/events",
            data=body,
            headers={"Content-Type": "application/json", "X-T2M-Source": "bridge"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except (OSError, ValueError) as exc:
        log.warning("Failed to publish TikTok event to EventBus: %s", exc)
        get_crash_manager().report_exception(
            TIKTOK_0004, exc=exc, context_info={"target": "eventbus_api_event"}
        )


def _notify_hooks_of_event(event_type: str, data: dict) -> None:
    """Fan a published bus event out to subscribed hooks.

    Runs in the shared background executor — hook code must never block
    the trigger/TikTok threads. ``fire_hook_event`` isolates handler
    exceptions, so nothing extra needed here.
    """
    try:
        fire_hook_event(event_type, data)
    except Exception as exc:  # defensive: executor job must never raise
        log.warning("[HOOK] event fan-out for '%s' failed: %s", event_type, exc)


def _post_chatbot_status(status: dict) -> None:
    """Forward chatbot status to the API EventBus (GUI SSE), best-effort."""
    body = json.dumps({"type": "chatbot.status", "data": status}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/events",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except (OSError, ValueError) as exc:
        log.debug("[CHATBOT] Status POST failed: %s", exc)


def _stop_tiktok_client():
    """Disconnect an active TikTok client on its own event loop (best effort).

    Called from the webhook server thread; the disconnect is scheduled onto the
    client's dedicated asyncio loop so the reconnect loop unblocks promptly.
    """
    client = ctx.tiktok_client
    loop = ctx.tiktok_client_loop
    if client is None or loop is None:
        return
    try:
        if not client.connected:
            return
        future = asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
        future.result(timeout=5)
    except Exception as e:  # best-effort stop
        log.warning(f"[TIKTOK] Error stopping client: {e}")


async def _tiktok_status_heartbeat():
    """Periodically re-report the live state to the API.

    Re-publishes ``tiktok.live_status`` every 30s so the GUI stays accurate
    even if the API server restarts while the bridge stays connected (the
    connect/disconnect events are one-shot and would otherwise be missed).
    """
    while True:
        try:
            _publish_tiktok_status(bool(ctx.tiktok_live))
        except Exception as e:  # heartbeat must never die
            log.debug("[HEARTBEAT] TikTok status publish failed: %s", e)
        await asyncio.sleep(30)


def _append_follow_tracking(user_lower: str):
    try:
        with open(ctx.follow_tracking_file, "a", encoding="utf-8") as f:
            f.write(user_lower + "\n")
    except OSError as e:
        log.warning(f"[FOLLOW] Could not write to {ctx.follow_tracking_file}: {e}")


def _touch_runtime_shutdown():
    try:
        ctx.runtime_path_shutdown.touch(exist_ok=True)
    except OSError as e:
        log.warning(f"[LIVE] Could not write shutdown signal: {e}")


def _process_follow(
    username: str,
    persist: bool = True,
    context: dict | None = None,
    force: bool = False,
):
    """Shared follow dedup: cache check, persist (optional), enqueue trigger once per user.

    ``force=True`` bypasses the visited-cache entirely (neither checked nor
    recorded) so a *test* follow always fires and never poisons real dedup.
    """
    user_lower = username.lower()
    if not force:
        with ctx.follow_lock:
            if user_lower in ctx._followed_cache:
                log.info(
                    f"[FOLLOW] {username} already tracked — follow trigger skipped"
                )
                return
            ctx._followed_cache.add(user_lower)
    if persist:
        # File append runs on the background executor; dedup already happened
        # above, so an async write can never produce a duplicate trigger.
        _run_in_background(_append_follow_tracking, user_lower)
    if "follow" in ctx.valid_functions:
        hook_context = (
            context if isinstance(context, dict) else _make_hook_context("follow")
        )
        enqueue_threadsafe(
            ("follow", username, 0, hook_context),
            label="follow",
        )


def validate_like_triggers(raw_triggers: object) -> list[dict]:
    """Validate and normalize ``tiktok.like_triggers`` from the config.

    Rules per entry:
    - id       — required, non-empty string, must be unique
    - every    — required, int > 0 (accepts "100_000" strings)
    - function — required, non-empty string
    - payload  — optional, default "Community"
    - enabled  — optional, default True (strings are cast to bool)

    Invalid entries are logged and skipped.
    """
    valid_triggers: list[dict] = []
    seen_ids: set[str] = set()

    if not isinstance(raw_triggers, list):
        if raw_triggers:
            log.warning("[CONFIG] 'tiktok.like_triggers' must be a list — ignored")
        return valid_triggers

    log.info(f"[LIKE DEBUG] validate_like_triggers called: raw_triggers={raw_triggers}")
    for i, rule in enumerate(raw_triggers):
        if not isinstance(rule, dict):
            log.info(
                f"[CONFIG ERROR] like_triggers entry #{i} is not an object: {rule}"
            )
            continue

        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            log.info(f"[CONFIG ERROR] Invalid or missing 'id': {rule}")
            continue
        if rule_id in seen_ids:
            log.info(f"[CONFIG ERROR] Duplicate id '{rule_id}'")
            continue
        seen_ids.add(rule_id)

        raw_every = rule.get("every")
        if raw_every is None:
            log.info(f"[CONFIG ERROR] 'every' missing for {rule_id}")
            continue
        try:
            every = int(str(raw_every).replace("_", ""))
            if every <= 0:
                raise ValueError
        except (ValueError, TypeError):
            log.info(f"[CONFIG ERROR] Invalid 'every' value for {rule_id}: {raw_every}")
            continue

        function_name = rule.get("function")
        if not isinstance(function_name, str) or not function_name.strip():
            log.info(f"[CONFIG ERROR] Invalid or missing 'function' for {rule_id}")
            continue

        payload = rule.get("payload", "Community")
        if not isinstance(payload, str):
            log.info(f"[CONFIG ERROR] 'payload' must be a string for {rule_id}")
            continue

        enabled = rule.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("true", "1", "yes", "on")
        enabled = bool(enabled)

        valid_triggers.append(
            {
                "id": rule_id,
                "every": every,
                "function": function_name,
                "payload": payload,
                "enabled": enabled,
            }
        )

    log.info(
        f"[LIKE DEBUG] Validated {len(valid_triggers)} like triggers: {[r['id'] for r in valid_triggers]}"
    )
    return valid_triggers


def prepare_like_triggers(raw_triggers: list[dict]) -> list[dict]:
    """Filter validated like triggers down to enabled rules with actions.

    The prepared rules carry ``last_blocks`` so ``_enqueue_like_triggers``
    fires each function exactly once per crossed milestone.
    """
    prepared: list[dict] = []
    log.info(
        f"[LIKE DEBUG] prepare_like_triggers called: raw_triggers={len(raw_triggers)}, valid_functions={len(ctx.valid_functions)}"
    )
    for rule in raw_triggers:
        if not rule.get("enabled", True):
            log.info(
                f"[LIKE DEBUG] Skipping rule {rule.get('id', 'unknown')}: disabled"
            )
            continue
        if rule["function"] not in ctx.valid_functions:
            log.info(
                f"[CONFIG ERROR] Unknown function: {rule['function']} (available: {sorted(ctx.valid_functions)})"
            )
            continue
        prepared.append(
            {
                "id": rule["id"],
                "every": rule["every"],
                "function": rule["function"],
                "payload": rule["payload"],
                "last_blocks": 0,
            }
        )
    log.info(
        f"[LIKE DEBUG] Prepared {len(prepared)} like triggers: {[r['id'] for r in prepared]}"
    )
    return prepared


def _update_like_totals(
    previous_total: int | None, new_total: int, session_likes: int
) -> tuple[int, int]:
    """Accumulate real new likes from TikTok's cumulative count.

    TikTok can rewind / reset the total mid-stream (a baseline reload), so
    only positive deltas count as new likes. ``previous_total`` is the last
    reported total (``None`` on first reading); returns ``(session_likes,
    last_total)`` such that the accumulated value never goes negative.
    """
    if previous_total is None:
        return session_likes, new_total
    diff = new_total - previous_total
    if diff > 0:
        session_likes += diff
    return session_likes, new_total


def _enqueue_like_triggers(total_since_start: int, username: str | None) -> None:
    """Enqueue configured like triggers at their 'every' milestones.

    Each rule fires its ``function`` once per crossed milestone, using its
    ``payload`` as the subject (shown in logs and the ``{user}`` placeholder).
    Rules are filtered by ``ctx.valid_functions``, so triggers without an
    action in actions.mca never enqueue.

    Callers must hold ``ctx.like_lock`` (the sole critical section), matching
    the single-lock design so nested acquisition never deadlocks.
    """
    rules = ctx.like_triggers
    log.debug(
        f"[LIKE DEBUG] _enqueue_like_triggers called: total_since_start={total_since_start}, username={username}, rules={len(rules)}"
    )
    if not rules:
        log.debug("[LIKE DEBUG] No like_triggers configured, returning")
        return
    for rule in rules:
        every = rule["every"]
        if every <= 0:
            log.debug(f"[LIKE DEBUG] Skipping rule {rule['id']}: every={every} <= 0")
            continue
        blocks = total_since_start // every
        log.debug(
            f"[LIKE DEBUG] Rule '{rule['id']}': every={every}, total_since_start={total_since_start}, blocks={blocks}, last_blocks={rule['last_blocks']}"
        )
        if blocks > rule["last_blocks"]:
            diff = blocks - rule["last_blocks"]
            rule["last_blocks"] = blocks
            log.info(
                f"[LIKE] Trigger '{rule['id']}' -> +{diff} "
                f"(total_since_start={total_since_start})"
            )
            for _ in range(diff):
                enqueue_threadsafe(
                    (
                        rule["function"],
                        rule["payload"],
                        0,
                        _make_hook_context(
                            "like",
                            total_since_start=total_since_start,
                            milestone_every=every,
                            milestone_rule=rule["id"],
                        ),
                    ),
                    label=f"like:{rule['id']}",
                )
        else:
            log.debug(
                f"[LIKE DEBUG] Rule '{rule['id']}' not triggered: blocks ({blocks}) <= last_blocks ({rule['last_blocks']})"
            )


def _process_comment_command(
    username,
    comment_text,
    is_moderator,
    is_super_fan,
    in_fanclub,
    log_prefix="[COMMENT CMD]",
):
    """Shared comment command processing. Returns True if 'comment' event trigger should be suppressed."""
    suppress = False
    if not ctx.comment_cmd_enable or not ctx.comment_cmd_groups:
        return suppress

    # Conditional HTTP handlers block for up to 10 s. They are collected
    # here and executed AFTER the lock is released — never do blocking I/O
    # while holding ctx.comment_cmd_lock, or /test_comment and every other
    # comment stalls behind a slow endpoint.
    pending_conditional: list[tuple[str, str, str, str, float]] = []

    # The cooldown dicts are mutated from multiple TikTok event threads and
    # the /test_comment Flask endpoint; guard them with a lock.
    with ctx.comment_cmd_lock:
        now = time.time()
        gcd = ctx.comment_cmd_global_cooldown
        if gcd > 0 and now - ctx.comment_cmd_global_last < gcd:
            remaining = gcd - (now - ctx.comment_cmd_global_last)
            log.info(
                f"{log_prefix} {username} blocked by global cooldown ({remaining:.1f}s left)"
            )
            return True

        gucd = ctx.comment_cmd_global_user_cooldown
        if gucd > 0:
            last_user = ctx.comment_cmd_global_user_last.get(username, 0)
            if now - last_user < gucd:
                remaining = gucd - (now - last_user)
                log.info(
                    f"{log_prefix} {username} blocked by global user cooldown ({remaining:.1f}s left)"
                )
                return True

        for group in ctx.comment_cmd_groups:
            prefix = group["prefix"]
            if not prefix or not comment_text.startswith(prefix):
                continue
            cmd_text = comment_text[len(prefix) :].strip()
            # A leading "/" is accepted by RCON/console but would bypass the
            # first-word deny/allow match below ("/op" != "op") — strip it so
            # matching and dispatch see the same normalized command.
            cmd_text = cmd_text.lstrip("/").strip()
            if not cmd_text:
                continue

            allowed = False
            if (
                "all" in group["roles"]
                or ("moderator" in group["roles"] and is_moderator)
                or ("superfan" in group["roles"] and is_super_fan)
                or ("fanclub" in group["roles"] and in_fanclub)
            ):
                allowed = True

            if not allowed:
                log.info(
                    f"{log_prefix} {username} no permission for prefix '{prefix}' (roles: {group['roles']})"
                )
                if not group.get("trigger_comment_event", True):
                    suppress = True
                continue

            base_cmd = cmd_text.split()[0].lower()
            # A "minecraft:" namespace ("minecraft:op" runs the same command
            # as "op") would bypass the first-word deny/allow match below —
            # strip it so both spellings hit the same list entry.
            if base_cmd.startswith("minecraft:"):
                base_cmd = base_cmd.split(":", 1)[1]
                if not base_cmd:
                    continue
            if group["mode"] == "deny-all":
                if base_cmd not in group["commands"]:
                    log.info(
                        f"{log_prefix} {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' not allowed (deny-all)"
                    )
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue
            else:
                if base_cmd in group["commands"]:
                    log.info(
                        f"{log_prefix} {username} tried '{cmd_text}' via '{prefix}' — '{base_cmd}' blocked (allow-all)"
                    )
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue

            ccfg = group.get("commands_config", {}).get(base_cmd, {})

            cmd_roles = ccfg.get("roles")
            if cmd_roles:
                cmd_allowed = False
                if (
                    "all" in cmd_roles
                    or ("moderator" in cmd_roles and is_moderator)
                    or ("superfan" in cmd_roles and is_super_fan)
                    or ("fanclub" in cmd_roles and in_fanclub)
                ):
                    cmd_allowed = True
                if not cmd_allowed:
                    log.info(
                        f"{log_prefix} {username} no permission for '{base_cmd}' (per-command roles: {cmd_roles})"
                    )
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue

            cd = ccfg.get("cooldown", group["cooldown"])
            ucd = ccfg.get("user_cooldown", group["user_cooldown"])
            if cd > 0:
                last = ctx.comment_cmd_last_global.get(prefix, 0)
                if now - last < cd:
                    remaining = cd - (now - last)
                    log.info(
                        f"{log_prefix} {username} blocked by global cooldown ({remaining:.1f}s left)"
                    )
                    if not group.get("trigger_comment_event", True):
                        suppress = True
                    continue
            if ucd > 0:
                last_user = ctx.comment_cmd_last_user.setdefault(prefix, {}).get(
                    username, 0
                )
                if now - last_user < ucd:
                    remaining = ucd - (now - last_user)
                    log.info(
                        f"{log_prefix} {username} blocked by user cooldown ({remaining:.1f}s left)"
                    )
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
                ctx.comment_cmd_last_global = {
                    k: v for k, v in ctx.comment_cmd_last_global.items() if v >= cutoff
                }
            if len(ctx.comment_cmd_last_user) > 1000:
                cutoff = now - 3600
                ctx.comment_cmd_last_user = {
                    k: {u: t for u, t in v.items() if t >= cutoff}
                    for k, v in ctx.comment_cmd_last_user.items()
                }
            if len(ctx.comment_cmd_global_user_last) > 1000:
                cutoff = now - 3600
                ctx.comment_cmd_global_user_last = {
                    u: t
                    for u, t in ctx.comment_cmd_global_user_last.items()
                    if t >= cutoff
                }

            # 1. Plugin handler (configured via comment_commands.yaml)
            if cmd_handler == "plugin" and group.get("plugin_name"):
                _dispatch_comment_to_plugin(group["plugin_name"], cmd_text, username)
            # 2. RCON handler
            elif cmd_handler == "rcon":
                enqueue_threadsafe(
                    ([cmd_text], username),
                    queue=ctx.rcon_queue,
                    label=f"comment_rcon:{prefix}",
                )
            # 3. HTTP handler
            elif cmd_handler == "http" and cmd_url:
                if conditional:
                    pending_conditional.append(
                        (cmd_url, username, cmd_text, prefix, now)
                    )
                else:
                    url = cmd_url.replace(
                        "{user}", urllib.parse.quote(username, safe="")
                    )
                    url = url.replace("{text}", urllib.parse.quote(cmd_text, safe=""))
                    _run_in_background(_dispatch_comment_http, url, username, cmd_text)

            if not group.get("trigger_comment_event", True):
                suppress = True

    # Conditional HTTP runs without the lock. The comment worker is a
    # single thread, so comments are still processed sequentially — but
    # /test_comment and the TikTok event threads are never blocked by a
    # slow endpoint.
    for c_url, c_user, c_text, c_prefix, c_now in pending_conditional:
        resp_data = _dispatch_comment_http_sync(c_url, c_user, c_text)
        if resp_data and resp_data.get("found", False):
            with ctx.comment_cmd_lock:
                ctx.comment_cmd_last_global[c_prefix] = c_now
                ctx.comment_cmd_last_user.setdefault(c_prefix, {})[c_user] = c_now
                ctx.comment_cmd_global_last = c_now
                ctx.comment_cmd_global_user_last[c_user] = c_now
            mode_label = resp_data.get("mode", "replace")
            if mode_label == "queue":
                log.info(
                    f"{log_prefix} {c_user} → conditional response: mode={mode_label}"
                )
        else:
            log.info(
                f"{log_prefix} {c_user} → conditional response negative — no cooldown triggered"
            )

    return suppress


# ==========================================
# Comment worker thread
# ==========================================
# Comment command processing may block on HTTP requests (conditional
# handlers) and mutates shared cooldown state. Running it on a dedicated
# worker keeps the TikTok event loop responsive; the cooldown dicts stay
# guarded by ctx.comment_cmd_lock so the /test_comment Flask endpoint can
# still call _process_comment_command synchronously.
_COMMENT_QUEUE_MAX = 2000
_comment_queue: queue.Queue = queue.Queue(maxsize=_COMMENT_QUEUE_MAX)
_comment_worker_started = False
_comment_worker_lock = threading.Lock()


def _enqueue_comment(item: tuple) -> None:
    """Enqueue a comment event, dropping with a warning when full."""
    try:
        _comment_queue.put_nowait(item)
    except queue.Full:
        log.warning(
            "[COMMENT] Queue full (%d) — dropping comment from %s",
            _COMMENT_QUEUE_MAX,
            item[0] if item else "?",
        )


def _comment_worker_main():
    while True:
        item = _comment_queue.get()
        try:
            _handle_comment_event(*item)
        except Exception as e:  # worker must never die; log and keep draining
            log.error(f"[COMMENT] Worker error: {e}")
            get_crash_manager().report_exception(
                TIKTOK_0003, exc=e, context_info={"source": "comment_worker"}
            )
        finally:
            _comment_queue.task_done()


def _start_comment_worker():
    global _comment_worker_started
    with _comment_worker_lock:
        if _comment_worker_started:
            return
        threading.Thread(
            target=_comment_worker_main, name="comment-worker", daemon=True
        ).start()
        _comment_worker_started = True


def _handle_comment_event(
    username,
    comment_text,
    is_moderator,
    is_super_fan,
    in_fanclub,
):
    """Full comment handling, run on the dedicated comment worker thread."""
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
            cmd_part = comment_text[len(matched_prefix) :].strip()
            if cmd_part:
                group_enabled = any(
                    g["prefix"] == matched_prefix for g in ctx.comment_cmd_groups
                )
                if not ctx.comment_cmd_enable:
                    log.info(
                        f"[COMMENT CMD] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but comment_commands is disabled globally"
                    )
                elif not group_enabled:
                    log.info(
                        f"[COMMENT CMD] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but that command group is disabled"
                    )

    suppress_comment_trigger = _process_comment_command(
        username,
        comment_text,
        is_moderator,
        is_super_fan,
        in_fanclub,
        log_prefix="[COMMENT CMD]",
    )

    if "comment" in ctx.valid_functions and not suppress_comment_trigger:
        enqueue_threadsafe(
            (
                "comment",
                username,
                0,
                _make_hook_context(
                    "comment",
                    comment=comment_text,
                    is_moderator=is_moderator,
                    is_super_fan=is_super_fan,
                    in_fanclub=in_fanclub,
                ),
            ),
            label="comment",
        )


# ==========================================
# Custom trigger + test comment endpoints
# ==========================================
@app.route("/test_comment", methods=["POST"])
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
        log.info(
            f"  Moderator: {is_moderator}, Superfan: {is_super_fan}, Fanclub: {in_fanclub}"
        )

        if ctx.comment_cmd_all_prefixes:
            matched_prefix = None
            for p in sorted(ctx.comment_cmd_all_prefixes, key=len, reverse=True):
                if comment_text.startswith(p):
                    matched_prefix = p
                    break
            if matched_prefix:
                cmd_part = comment_text[len(matched_prefix) :].strip()
                if cmd_part:
                    group_enabled = any(
                        g["prefix"] == matched_prefix for g in ctx.comment_cmd_groups
                    )
                    if not ctx.comment_cmd_enable:
                        log.info(
                            f"[TEST COMMENT] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but comment_commands is disabled globally"
                        )
                    elif not group_enabled:
                        log.info(
                            f"[TEST COMMENT] {username} typed '{cmd_part}' (prefix '{matched_prefix}') but that command group is disabled"
                        )

        _process_comment_command(
            username,
            comment_text,
            is_moderator,
            is_super_fan,
            in_fanclub,
            log_prefix="[TEST COMMENT]",
        )

        return {
            "status": "ok",
            "message": f"Comment '{comment_text}' from '{username}' processed.",
        }

    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error(f"[TEST COMMENT] Error: {e}")
        return {"status": "error", "message": str(e)}, 500


# ==========================================
# Webhook endpoint for custom trigger injection (test/simulation)
# ==========================================
@app.route("/custom_trigger", methods=["POST"])
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
                return {
                    "status": "error",
                    "message": "Field 'trigger' is required and must not be empty.",
                }, 400
            sanitized = sanitize_filename(trigger)
            if not sanitized:
                return {
                    "status": "error",
                    "message": f"Trigger '{trigger}' contains no valid characters after sanitizing.",
                }, 400
        else:
            return {
                "status": "error",
                "message": "Field 'trigger' must be string or int.",
            }, 400

        # Special toggle: if trigger is 'tiktok', toggle TikTok connection
        if sanitized == "tiktok":
            with ctx.tiktok_lock:
                ctx.disable_tiktok_connect = not ctx.disable_tiktok_connect
                new_state = ctx.disable_tiktok_connect
            log.info(
                f"[CUSTOM TRIGGER] TikTok connect toggled: {not new_state} -> {new_state}"
            )
            if new_state:
                _stop_tiktok_client()
            _publish_tiktok_status(bool(ctx.tiktok_live))
            return {
                "status": "ok",
                "message": f"TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT={new_state}",
                # Structured state so the API does not have to parse the message
                "connected": not new_state,
            }, 200

        if sanitized == "follow":
            if "follow" not in ctx.valid_functions:
                return {
                    "status": "error",
                    "message": (
                        "Trigger 'follow' is not configured — add a 'follow:' action "
                        "to actions.mca."
                    ),
                }, 400
            # Test follows must always fire: bypass the real-follower dedup cache
            # (neither check nor record) so repeating the same test user still
            # triggers, and a later real follow of that user is not swallowed.
            # persist=False keeps the test user out of followed_users.txt.
            _process_follow(
                user,
                persist=False,
                force=True,
                context=_make_hook_context("follow", source="webhook"),
            )
            log.info(f"[CUSTOM TRIGGER] Injected: 'follow' (user: {user})")
            return {"status": "ok", "trigger": sanitized, "user": user}, 200

        if ctx.main_loop is None:
            return {"status": "error", "message": "Bot event loop not ready yet."}, 503

        if sanitized in ctx.valid_functions:
            # Best-effort synchronous full-check so the endpoint can still
            # report overload; the guarded put logs any drop that races in.
            if ctx.trigger_queue.full():
                return {
                    "status": "error",
                    "message": "Trigger queue is full. Try again later.",
                }, 503
            enqueue_threadsafe(
                (sanitized, user, 0, _make_hook_context(sanitized, source="webhook")),
                label=f"custom_trigger:{sanitized}",
            )
            log.info(f"[CUSTOM TRIGGER] Injected: '{sanitized}' (user: {user})")
            return {"status": "ok", "trigger": sanitized, "user": user}, 200

        raw_trigger = str(data.get("trigger", "")).strip()
        cmds = ctx.shell_actions_cache.get(raw_trigger) or ctx.shell_actions_cache.get(
            sanitized
        )
        if cmds:
            try:
                asyncio.run_coroutine_threadsafe(
                    execute_shell_commands(cmds), ctx.main_loop
                )
            except (RuntimeError, ValueError) as e:
                return {"status": "error", "message": str(e)}, 500
            log.info(
                f"[CUSTOM TRIGGER] Shell action for '{raw_trigger}' executed ({len(cmds)} command(s))"
            )
            return {"status": "ok", "trigger": raw_trigger, "user": user}, 200

        return {
            "status": "error",
            "message": f"Trigger '{sanitized}' does not exist or is not valid.",
        }, 400

    except Exception as e:  # any unexpected error becomes an HTTP 500
        return {"status": "error", "message": str(e)}, 500


# =========================================


# --- Start webhook server in its own thread ---
def run_signal_server():
    if ctx.server_host == "0.0.0.0":
        log.warning(
            "SECURITY: Webhook server binding to 0.0.0.0 (all interfaces). "
            "Ensure an API key is configured in the control plane (config.yaml: api_key) "
            "and consider restricting to localhost in production."
        )
    try:
        app.run(
            host=ctx.server_host,
            port=ctx.mcserver_api_port,
            threaded=True,
            debug=False,
            use_reloader=False,
        )
    except Exception as exc:  # best-effort webhook server thread; failure must not take down the bridge
        log.error(
            "Bridge webhook server failed to start on %s:%s: %s",
            ctx.server_host,
            ctx.mcserver_api_port,
            exc,
        )


# ==========================================
# HTTP command executor
# ==========================================


def execute_http_command_sync(cmd: str):
    try:
        args = shlex.split(cmd)
    except ValueError as e:
        log.warning(f"[SHELL] Invalid command syntax: {cmd} ({e})")
        return
    try:
        subprocess.run(args, check=True, timeout=30)
        log.info(f"Success: {cmd}")
    except subprocess.CalledProcessError as e:
        log.warning(f"[FAIL] Error: {cmd} ({e})")
    except subprocess.TimeoutExpired:
        log.warning(f"[SHELL] Command timed out after 30s: {cmd}")


async def execute_http_command(cmd: str):
    await asyncio.to_thread(execute_http_command_sync, cmd)


async def execute_shell_commands(cmds: list[str]):
    """Execute a list of shell commands sequentially."""
    for cmd in cmds:
        await execute_http_command(cmd)


# ==========================================
# User-friendly name extraction
# ==========================================
def get_safe_username(user):
    name = (
        getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "Unknown"
    )
    return name


def user_attr_safe(event, name, default=None):
    """Access an event's user attribute without letting TikTokLive's
    ``ExtendedUser.from_user`` raise. TikTok's user payload may include fields
    (e.g. ``nickName``) that the installed proto model does not know, which
    makes ``event.user`` itself throw a TypeError. Any single bad event must
    never kill the WebSocket loop, so resolve the user defensively.
    """
    try:
        user = event.user
    except Exception:
        return default
    return getattr(user, name, default)


def username_from_event_safe(event, default: str | None = "Unknown"):
    return (
        user_attr_safe(event, "unique_id", None)
        or user_attr_safe(event, "nickname", None)
        or default
    )


# ==========================================
# TIKTOK CLIENT
# ==========================================


def create_client(user):
    client = TikTokLiveClient(unique_id=user)

    # A single event-handler exception must never tear down the WebSocket
    # reader loop. pyee re-emits handler errors as an "error" event; without a
    # listener that propagation kills the whole stream (silence after the
    # initial burst). Registering a handler keeps the loop alive.
    def _on_client_event_error(exc):
        log.error("TikTok event handler error (recovered, loop kept alive): %s", exc)
        get_crash_manager().report_exception(
            TIKTOK_0003, exc=exc, context_info={"source": "client_event_handler"}
        )

    # Register the handler-error listener defensively: newer TikTokLive versions
    # (>=6.6.5) support a string event name in `add_listener`, but older builds
    # require a `Type[Event]` and call `.get_type()` on the argument, which
    # crashes on the "error" string. The listener is a best-effort safety net —
    # never let an unsupported registration tear down the whole bridge at client
    # creation.
    try:
        client.add_listener("error", _on_client_event_error)
    except (AttributeError, TypeError):
        log.warning(
            "[TIKTOK] Error-listener registration unsupported by this TikTokLive "
            "version; loop-crash recovery not registered"
        )

    # Raw-event diagnostics: proves whether the websocket actually delivers
    # events to the bridge before handler dispatch. Prints each event type on
    # first occurrence and then every 200th, so a silent loop (the old
    # "loop crash"/stranded-reader symptom) is visible in the logs.
    def _log_raw_event(etype: str) -> None:
        now = time.time()
        ctx._last_tiktok_event_ts = now
        cnt = ctx._tiktok_event_counters.get(etype, 0) + 1
        ctx._tiktok_event_counters[etype] = cnt
        if cnt <= 3 or cnt % 200 == 0:
            log.info(f"[TIKTOK][RAW] {etype} event #{cnt} received")

    _connect_time = [None]
    COMMENT_WARMUP_SECONDS = 1

    # =========================
    # GIFT events
    # =========================
    @client.on(GiftEvent)
    def on_gift(event: GiftEvent):
        _log_raw_event("gift")
        try:
            if event.gift.combo:
                if getattr(event, "streaking", False):
                    return

                count = event.repeat_count
            else:
                count = 1

            gift_name = sanitize_filename(event.gift.name)
            gift_id = str(event.gift.id)

            with ctx.gift_lock:
                ctx.gift_value_usd += event.value
                ctx.session_gift_value_usd += event.value
                ctx.session_gifts += count

            username = username_from_event_safe(event)
            _publish_tiktok_event(
                "gift", username, gift_name=gift_name, gift_id=gift_id, count=count
            )

            target = None
            if gift_name in ctx.valid_functions:
                target = gift_name
            elif gift_id in ctx.valid_functions:
                target = gift_id

            if not target:
                return

            gift_context = _make_hook_context(
                "gift",
                gift_name=gift_name,
                gift_id=gift_id,
                streak=count,
                combo=bool(getattr(event.gift, "combo", False)),
            )
            for _ in range(count):
                enqueue_threadsafe(
                    (target, username, 0, gift_context), label=f"gift:{target}"
                )

        except Exception as exc:  # TikTok event handler must not crash the client
            log.exception("ERROR IN ON_GIFT EVENT")
            get_crash_manager().report_exception(
                TIKTOK_0003, exc=exc, context_info={"source": "on_gift"}
            )

    # =========================
    # FOLLOW events
    # =========================
    @client.on(FollowEvent)
    def on_follow(event: FollowEvent):
        _log_raw_event("follow")
        username = username_from_event_safe(event)
        ctx.session_follows += 1
        _publish_tiktok_event("follow", username)
        _process_follow(username)

    # =========================
    # LIKE events
    # =========================
    @client.on(LikeEvent)
    def on_like(event: LikeEvent):
        _log_raw_event("like")
        username = username_from_event_safe(event, default=None)
        if username:
            _publish_tiktok_event("like", username)
        with ctx.like_lock:
            if ctx.start_likes is None:
                ctx.start_likes = event.total
                ctx._last_like_total = event.total
                ctx.session_likes = 0
                log.info(f"[LIKE] Initial count set: {ctx.start_likes}")
                log.debug(
                    f"[LIKE DEBUG] event.total={event.total}, start_likes={ctx.start_likes}, session_likes={ctx.session_likes}"
                )
                return
            # TikTok's cumulative count can rewind / reset mid-stream, so only
            # accumulate positive deltas (real new likes) instead of comparing
            # to a one-time baseline — otherwise total_since_start goes
            # negative and milestones never fire.
            ctx.session_likes, ctx._last_like_total = _update_like_totals(
                ctx._last_like_total, event.total, ctx.session_likes
            )
            total_since_start = ctx.session_likes
            log.debug(
                f"[LIKE DEBUG] event.total={event.total}, _last_like_total={ctx._last_like_total}, session_likes={ctx.session_likes}, total_since_start={total_since_start}, like_triggers={len(ctx.like_triggers)}"
            )
            try:
                now = time.time()
                # Throttle like events to ~1 per 3 seconds
                if now - ctx._last_like_event >= 3:
                    delta = total_since_start
                    ctx.session_likes = total_since_start
                    _publish_tiktok_event(
                        "like", username or "unknown", delta=delta, total=event.total
                    )
                    log.debug(
                        f"[LIKE DEBUG] Calling _enqueue_like_triggers with total_since_start={total_since_start}, username={username}"
                    )
                    _enqueue_like_triggers(total_since_start, username)
                    ctx._last_like_event = now
                else:
                    log.debug(
                        f"[LIKE DEBUG] Throttled: now={now}, _last_like_event={ctx._last_like_event}, diff={now - ctx._last_like_event:.2f}s"
                    )
            except Exception as e:  # TikTok event handler must not crash the client
                log.error(f"[EVENT ERROR] Error in like handling: {e}")
                get_crash_manager().report_exception(
                    TIKTOK_0003, exc=e, context_info={"source": "on_like"}
                )

    # ========================
    # Join events
    # ========================
    @client.on(JoinEvent)
    def on_join(event):
        _log_raw_event("join")
        username = username_from_event_safe(event)
        ctx.session_joins += 1
        _publish_tiktok_event("join", username)
        if "join" in ctx.valid_functions:
            enqueue_threadsafe(
                ("join", username, 0, _make_hook_context("join")), label="join"
            )

    # =========================
    # COMMENT events
    # =========================
    @client.on(CommentEvent)
    def on_comment(event):
        _log_raw_event("comment")
        if (
            _connect_time[0] is None
            or (time.time() - _connect_time[0]) < COMMENT_WARMUP_SECONDS
        ):
            return

        username = username_from_event_safe(event)
        ctx.session_comments += 1
        comment_text = getattr(event, "comment", "")
        _publish_tiktok_event("comment", username, comment=comment_text)

        is_super_fan = bool(getattr(event, "user_is_super_fan", None))

        # Resolve the user object ONCE per event: ``event.user`` is a property
        # that re-runs ExtendedUser.from_user (and may throw on unknown proto
        # fields) on every access, so fan/moderator checks share a single
        # lookup instead of re-triggering it (on-loop cost under high comment
        # flow delays the websocket ack/heartbeat -> reader stall).
        try:
            user = event.user
        except Exception:
            user = None

        def _ua(name, default=None):
            return getattr(user, name, default) if user is not None else default

        in_fanclub = False
        fan_ticket_count = _ua("fan_ticket_count", None)
        fans_club = _ua("fans_club", None)
        fans_club_info = _ua("fans_club_info", None)
        if (
            fan_ticket_count
            and fan_ticket_count > 0
            or hasattr(fans_club, "club_name")
            or hasattr(fans_club_info, "club_name")
        ):
            in_fanclub = True

        is_moderator = bool(_ua("is_moderator", None))

        # Heavy comment handling (logging, prefix matching, cooldowns, HTTP
        # conditional handlers) runs on a dedicated worker thread.
        _start_comment_worker()
        _enqueue_comment(
            (username, comment_text, is_moderator, is_super_fan, in_fanclub)
        )

    # =========================
    # Share events
    # =========================
    @client.on(ShareEvent)
    def on_share(event):
        _log_raw_event("share")
        username = username_from_event_safe(event)
        ctx.session_shares += 1
        _publish_tiktok_event("share", username)
        if "share" in ctx.valid_functions:
            enqueue_threadsafe(
                ("share", username, 0, _make_hook_context("share")), label="share"
            )

    # =========================
    # Live end events
    # =========================
    @client.on(LiveEndEvent)
    def on_live_end(_):
        log.info(f"Live ended for @{user}.")
        ctx.tiktok_live = False
        ctx.session_end_ts = time.time()
        _publish_tiktok_status(False)
        # Revenue persistence and the shutdown signal are plain file I/O —
        # run them on the background executor so live-end never blocks the
        # TikTok client thread.
        _run_in_background(update_daily_revenue)
        _run_in_background(_save_session_summary, _session_summary_entry())
        _run_in_background(_touch_runtime_shutdown)
        # Hook lifecycle callbacks run isolated per hook; also offloaded to
        # the background executor so slow hook code cannot stall live-end.
        _run_in_background(fire_hook_lifecycle, "live_end")

    # =========================
    # Live disconnect events
    # =========================
    @client.on(DisconnectEvent)
    def on_disconnect(_):
        log.info(f"Live disconnected: @{user}")
        ctx.tiktok_live = False
        _publish_tiktok_status(False)

    # =========================
    # CONNECT event
    # =========================
    @client.on(ConnectEvent)
    def on_connect(_):
        _connect_time[0] = time.time()
        log.info(f"Live connection established: @{user}")
        ctx.tiktok_live = True
        # Raw-event diagnostics baseline.
        ctx._last_tiktok_event_ts = time.time()
        if _should_start_new_session():
            _reset_session()
        _publish_tiktok_status(True)
        _run_in_background(fire_hook_lifecycle, "live_start")
        # Capture the client's event loop — this handler runs on it, exactly
        # like the reference's client.run() serves one loop in the worker
        # thread — so run_coroutine_threadsafe can still disconnect the client
        # externally (webhook toggle / config reload) and the chatbot can
        # schedule room chat on it.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        ctx.tiktok_client_loop = loop
        if loop is not None:
            get_chatbot().bind_client(client, loop)

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
    today = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d")

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


# ========================
# Session summary (per stream)
# ========================
def _should_start_new_session() -> bool:
    """Whether a fresh ``ConnectEvent`` begins a new session.

    TikTokLive's websocket disallows in-socket reconnects (signed URLs expire
    fast), so a dropped connection re-enters the bridge via a fresh
    ``ConnectEvent`` — even while the stream is still running. Resetting the
    session counters on such reconnects would split one stream into multiple
    records (only the last segment would ever be saved). Preserve the running
    session unless there was none yet or the previous one already ended.
    """
    return ctx.session_start_ts is None or ctx.session_end_ts is not None


def _reset_session():
    """Reset the per-session counters before a new live connection."""
    ctx.session_start_ts = time.time()
    ctx.session_gifts = 0
    ctx.session_gift_value_usd = 0.0
    ctx.session_likes = 0
    ctx.session_follows = 0
    ctx.session_comments = 0
    ctx.session_shares = 0
    ctx.session_joins = 0
    ctx.session_end_ts = None


def _session_summary_entry() -> dict:
    """Snapshot the finished session for persistence.

    Called synchronously on the TikTok client thread at live end so the
    counters cannot be clobbered by a reconnect before the write happens.
    Returns ``{}`` when no session was active.
    """
    start = ctx.session_start_ts
    if start is None:
        return {}
    end = ctx.session_end_ts or time.time()
    return {
        "start": datetime.datetime.fromtimestamp(start, tz=datetime.UTC).isoformat(),
        "end": datetime.datetime.fromtimestamp(end, tz=datetime.UTC).isoformat(),
        "duration_seconds": round(max(0.0, end - start), 1),
        "gifts": ctx.session_gifts,
        "gift_value_usd": round(ctx.session_gift_value_usd, 2),
        "likes": ctx.session_likes,
        "follows": ctx.session_follows,
        "comments": ctx.session_comments,
        "shares": ctx.session_shares,
        "joins": ctx.session_joins,
    }


def _save_session_summary(entry: dict) -> None:
    """Append one session summary line to ``data/sessions.jsonl``.

    Pure file I/O — run it on the background executor (never on the TikTok
    client thread). A missing/empty entry is ignored.
    """
    if not entry:
        return
    file_path = BASE_DIR.parent / "data" / "sessions.jsonl"
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.info("[SESSION] Summary saved: %s", file_path)
    except OSError as exc:
        log.warning("Failed to save session summary %s: %s", file_path, exc)


def _flush_active_session() -> None:
    """Persist an unfinished live session (e.g. bridge shutdown mid-stream).

    ``LiveEndEvent`` is the normal persistence point. This covers shutdowns
    and abrupt disconnects where the stream-end event never arrives. Sessions
    that already ended normally (``session_end_ts`` set) were persisted by the
    live-end handler and are skipped to avoid duplicate records.
    """
    if ctx.session_start_ts is None or ctx.session_end_ts is not None:
        return
    entry = _session_summary_entry()
    if entry:
        _save_session_summary(entry)


# ==========================================
# RUNTIME RELOAD
# ==========================================


async def reload_config():
    """Reload config.yaml at runtime without restarting the bridge."""
    global _last_config_version
    log.info("[RELOAD] Config reload requested")
    try:
        _validate_dup_cmd_config()
        new_config = load_yaml(CONFIG_FILE)
        old_user = ctx.tiktok_user
        _apply_config(new_config)
        _last_config_version = read_config_version(CONFIG_FILE)

        if ctx.hook_api is not None:
            ctx.hook_api.update_runtime_state(
                config=ctx.config,
                valid_functions=ctx.valid_functions,
            )

        # Force the RCON worker to reconnect with the new settings.
        ctx.rcon_connection = None

        if old_user != ctx.tiktok_user and ctx.tiktok_client is not None:
            try:
                ctx.tiktok_client.stop()
            except Exception as e:  # best-effort stop
                log.debug("[RELOAD] Failed to stop old TikTok client: %s", e)

        log.info("[RELOAD] Config reloaded successfully")
    except Exception as e:  # runtime reload is best-effort; old config stays active
        log.error("[RELOAD] Config reload failed: %s", e)


def _request_minecraft_restart() -> None:
    """Ask the supervisor to restart the Minecraft server.

    ``start.py`` polls the ``restart_server`` runtime signal and restarts the
    Minecraft Server program. Writing the signal from the bridge guarantees
    the datapack regeneration + world sync finished before the next boot.
    """
    signal = get_runtime_dir() / "restart_server"
    try:
        signal.write_text("actions reload", encoding="utf-8")
        log.info("[RELOAD] Datapack synced — Minecraft server restart requested")
    except OSError as exc:
        log.warning(
            "[RELOAD] Failed to request Minecraft server restart (%s) — "
            "restart the server manually so datapack changes take effect",
            exc,
        )


async def reload_actions(send_minecraft_reload: bool = False):
    """Reload actions.mca at runtime without restarting the bridge.

    ``send_minecraft_reload`` asks the bridge to restart the Minecraft server
    after the datapack has been regenerated: Minecraft only loads datapack
    functions when the server starts, so a plain ``/reload`` is not enough for
    function changes to take effect.
    """
    log.info(
        "[RELOAD] Actions reload requested (restart Minecraft: %s)",
        send_minecraft_reload,
    )
    try:
        # File validation and the datapack rebuild run in a thread; the
        # rebuild publishes its result atomically (see generate_datapack),
        # so the main loop stays responsive during a reload.
        diags = await asyncio.to_thread(validate_file, ACTIONS_FILE, False)
        if any(d.severity == Severity.ERROR for d in diags):
            log.error("[RELOAD] actions.mca contains errors; reload aborted")
            print_diagnostics(diags)
            ctx.actions_valid = False
            get_health_monitor().set_state("tiktok_bridge", HealthState.DEGRADED)
            return

        await asyncio.to_thread(generate_datapack)
        # Push the fresh datapack into the server world so the restart below
        # boots with the regenerated functions.
        try:
            sync_datapack(
                (_BASE_PARENT / "server" / "default").resolve(), ctx.datapack_root
            )
        except OSError as exc:
            log.warning("[RELOAD] Failed to sync datapack into the world: %s", exc)
        ctx.actions_valid = True
        get_health_monitor().set_state("tiktok_bridge", HealthState.RUNNING)
        ctx.like_triggers = prepare_like_triggers(ctx.like_triggers)
        if ctx.hook_api is not None:
            ctx.hook_api.update_runtime_state(valid_functions=ctx.valid_functions)

        if send_minecraft_reload:
            # Minecraft loads datapack functions only at server start — a
            # /reload does not pick up regenerated functions, so restart the
            # server (the world copy was already synced above).
            _request_minecraft_restart()
        else:
            log.info(
                "[RELOAD] No Minecraft server restart requested — "
                "datapack function changes require a restart to take effect"
            )

        log.info("[RELOAD] Actions reloaded successfully")
    except Exception as e:  # runtime reload is best-effort; previous state stays active
        log.error("[RELOAD] Actions reload failed: %s", e)


async def reload_hooks_runtime():
    """Reload all event hooks at runtime without restarting the bridge.

    Triggered by the ``reload_hooks`` runtime signal (hook enable/disable,
    hook config save, or POST /reload with ``hooks=true``). Discovery,
    module (re-)import and register() run in a worker thread so the main
    loop stays responsive.
    """
    if ctx.hook_api is None:
        log.warning("[RELOAD] Hook reload skipped — hooks not initialized yet")
        return
    log.info("[RELOAD] Event hooks reload requested")
    try:
        stats = await asyncio.to_thread(reload_event_hooks, ctx.hook_api, ctx.config)
        log.info(
            "[RELOAD] Event hooks reloaded (%d hook config(s))",
            len(stats),
        )
    except Exception as e:  # reload is best-effort; previous state stays active
        log.error("[RELOAD] Event hooks reload failed: %s", e)


def _read_signal_options(path: Path) -> dict:
    """Read a JSON signal payload, defaulting to ``send_minecraft_reload=True``."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if text.startswith("{"):
            return json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
                except OSError:
                    pass
                current_ver = read_config_version(CONFIG_FILE)
                if current_ver > 0 and current_ver == _last_config_version:
                    log.debug(
                        "[RELOAD] Config version unchanged (%d), skipping", current_ver
                    )
                else:
                    await reload_config()
            if RELOAD_ACTIONS_SIGNAL.exists():
                options = _read_signal_options(RELOAD_ACTIONS_SIGNAL)
                try:
                    RELOAD_ACTIONS_SIGNAL.unlink()
                except OSError:
                    pass
                await reload_actions(
                    send_minecraft_reload=options.get("send_minecraft_reload", True)
                )
            if RELOAD_COMMENT_COMMANDS_SIGNAL.exists():
                try:
                    RELOAD_COMMENT_COMMANDS_SIGNAL.unlink()
                except OSError:
                    pass
                _apply_comment_commands_from_yaml()
                log.info("[RELOAD] comment_commands reloaded from YAML")
            if RELOAD_CHATBOT_SIGNAL.exists():
                try:
                    RELOAD_CHATBOT_SIGNAL.unlink()
                except OSError:
                    pass
                get_chatbot().reload_config()
                log.info("[RELOAD] chatbot config reloaded")
            if RELOAD_HOOKS_SIGNAL.exists():
                try:
                    RELOAD_HOOKS_SIGNAL.unlink()
                except OSError:
                    pass
                await reload_hooks_runtime()
        except Exception as e:  # watcher must never die
            log.error("[RELOAD] Signal watcher error: %s", e)


# ==========================================
# MAIN ENTRY POINT
# ==========================================


async def run_bot():
    """Main async loop: initializes config, builds the datapack,
    starts all workers, and connects to TikTok Live."""
    ctx.main_loop = asyncio.get_running_loop()
    health = get_health_monitor()
    health.set_state("tiktok_bridge", HealthState.RUNNING)

    if not load_config():
        log.error("Error in load_config")
        health.set_state("tiktok_bridge", HealthState.FAILED)
        sys.exit(1)

    # TikTok username check: warn if still default, but do not block startup.
    default_user = "your_tiktok_username"
    if ctx.tiktok_user == default_user:
        log.warning(
            "[TIKTOK] Username is still the default '%s'. "
            "Set it via the GUI wizard or config.yaml; the bridge will connect once it is provided.",
            default_user,
        )

    try:
        diags = validate_file(ACTIONS_FILE, raise_on_error=False)
        if diags:
            log.info("[VALIDATOR] Validation result for actions.mca:")
            print_diagnostics(diags)
        if any(d.severity == Severity.ERROR for d in diags):
            n_errors = sum(1 for d in diags if d.severity == Severity.ERROR)
            log.error(
                "[ACTIONS] actions.mca contains %d error(s). Datapack generation is skipped, "
                "but the bridge keeps running so the API stays available. Fix the file and "
                "trigger a reload (or restart) to apply the actions.",
                n_errors,
            )
            ctx.actions_valid = False
            health.set_state("tiktok_bridge", HealthState.DEGRADED)
        else:
            ctx.actions_valid = True
    except FileNotFoundError as e:
        log.error(f"{e}")
        ctx.actions_valid = False
        health.set_state("tiktok_bridge", HealthState.DEGRADED)

    if ctx.actions_valid:
        generate_datapack()

    ctx.like_triggers = prepare_like_triggers(ctx.like_triggers)

    ctx.hook_api = HookAPI(
        ctx.rcon_queue,
        ctx.trigger_queue,
        ctx.main_loop,
        ctx.config,
        ctx.valid_functions,
    )
    load_event_hooks(ctx.hook_api, config=ctx.config)

    # Clear any stale reload signals from a previous run before the watcher starts.
    for sig in (
        RELOAD_CONFIG_SIGNAL,
        RELOAD_ACTIONS_SIGNAL,
        RELOAD_COMMENT_COMMANDS_SIGNAL,
        RELOAD_CHATBOT_SIGNAL,
        RELOAD_HOOKS_SIGNAL,
    ):
        try:
            sig.unlink(missing_ok=True)
        except OSError:
            pass

    threading.Thread(target=run_signal_server, daemon=True).start()

    crash_mgr = get_crash_manager()
    _chatbot = get_chatbot(
        status_sink=lambda s: _run_in_background(_post_chatbot_status, s)
    )
    for name, coro in [
        ("trigger_worker", trigger_worker()),
        ("rcon_worker", rcon_worker()),
        ("gift_revenue_counter", gift_revenue_counter()),
        ("_reload_signal_watcher", _reload_signal_watcher()),
        ("_tiktok_status_heartbeat", _tiktok_status_heartbeat()),
        ("chatbot_worker", _chatbot.run()),
    ]:
        task = asyncio.create_task(coro, name=name)
        crash_mgr.observe_task(task, component="tiktok_bridge")

    # Report initial state (incl. disabled flag) so the GUI syncs without waiting
    # for the first connect/disconnect event or the 30s heartbeat.
    _publish_tiktok_status(False)

    while True:
        with ctx.tiktok_lock:
            _disabled = ctx.disable_tiktok_connect
        if _disabled:
            await asyncio.sleep(ctx.reconnect_delay)
            continue

        if ctx.tiktok_user == default_user or not ctx.tiktok_user:
            log.info(
                "[TIKTOK] No valid username configured yet. Waiting for config reload..."
            )
            await asyncio.sleep(ctx.reconnect_delay)
            continue

        ctx.start_likes = None
        ctx._last_like_total = None
        ctx.like_triggers = prepare_like_triggers(ctx.like_triggers)
        client = create_client(ctx.tiktok_user)
        ctx.tiktok_client = client

        # Connect exactly the way the proven-working reference does
        # (AI_HANDOVER §2 / §8A option 3): TikTokLive's thread-blocking
        # `client.run()` builds its own event loop inside this worker thread
        # and serves it (`run_until_complete(client.connect())`) until the
        # WebSocket closes — no set_event_loop, no loop.close(), no watchdog,
        # no wrapper around the run call. The loop is captured in on_connect
        # (which runs on that loop) for external disconnect / chatbot sends.
        _chatbot.apply_session_to_client(client)

        try:
            log.info(f"[*] Connecting to @{ctx.tiktok_user}...")
            await asyncio.to_thread(client.run)

        except Exception as e:  # TikTok client connection errors are reported; reconnect loop continues
            log.exception("CRITICAL ERROR IN TIKTOK CLIENT")

            error_str = str(e)
            log.warning(f"[..] Connection lost: {error_str}")

            if "DEVICE_BLOCKED" in error_str or bool(
                _RE_ERR_CODE_200.search(error_str)
            ):
                log.error("[FAIL] TikTok block active (DEVICE_BLOCKED).")
                log.info("[TIP] Wait 15 minutes or restart your router.")
                get_crash_manager().report_exception(
                    TIKTOK_0001, exc=e, context_info={"block_reason": "DEVICE_BLOCKED"}
                )
                await asyncio.sleep(900)
            else:
                log.warning(f"[..] Reconnect in {ctx.reconnect_delay}s...")
                get_crash_manager().report_exception(
                    TIKTOK_0002,
                    exc=e,
                    context_info={"reconnect_delay": ctx.reconnect_delay},
                )
                await asyncio.sleep(ctx.reconnect_delay)

        finally:
            _chatbot.unbind_client()
            ctx.tiktok_client_loop = None
            ctx.tiktok_live = False
            # Persist a stream that was still running when the bridge stopped
            # (no LiveEndEvent will arrive). Sync on purpose — the task must
            # finish before the process exits.
            _flush_active_session()
            _publish_tiktok_status(False)
            await asyncio.sleep(2)


if __name__ == "__main__":
    import signal as _signal_mod

    install_global_exception_hook("main")
    heartbeat = start_heartbeat(log, interval=60.0)
    crash_mgr = get_crash_manager()
    health = get_health_monitor()
    health.register("tiktok_bridge", HealthState.STARTING)

    # Register signal handlers for graceful shutdown (especially SIGTERM on Linux).
    # Without this, SIGTERM kills the process instantly without cleanup.
    def _bridge_signal_handler(sig: int, frame: object) -> None:
        sig_name = (
            _signal_mod.Signals(sig).name
            if hasattr(_signal_mod, "Signals")
            else str(sig)
        )
        log.info("[SIGNAL] Bridge received %s — initiating graceful stop", sig_name)
        # Setting this flag causes the reconnect loop to exit cleanly;
        # the main event loop then runs finally blocks and exits.
        ctx.disable_tiktok_connect = True
        # Also try to stop the event loop via KeyboardInterrupt for immediate exit
        raise KeyboardInterrupt

    _signal_mod.signal(_signal_mod.SIGTERM, _bridge_signal_handler)
    _signal_mod.signal(_signal_mod.SIGINT, _bridge_signal_handler)
    if sys.platform != "win32" and hasattr(_signal_mod, "SIGHUP"):
        _signal_mod.signal(_signal_mod.SIGHUP, _bridge_signal_handler)  # type: ignore[attr-defined]

    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_bot())
        health.set_state("tiktok_bridge", HealthState.STOPPED)
    except KeyboardInterrupt:
        log.info("\n[STOP] Script stopped manually.")
        health.set_state("tiktok_bridge", HealthState.STOPPED)
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
        # Remote host closed the connection abruptly (e.g. overlay/GUI/browser
        # disconnect). This is normal network behavior, not a fatal crash.
        log.warning("[NET] Connection reset by remote host: %s", exc)
        health.set_state("tiktok_bridge", HealthState.STOPPED)
    except Exception:  # top-level boundary: report and exit non-zero
        handle_unhandled_exception("main")
        health.set_state("tiktok_bridge", HealthState.FAILED)
        sys.exit(1)
    finally:
        health.set_state("tiktok_bridge", HealthState.STOPPED)
        heartbeat.stop()
