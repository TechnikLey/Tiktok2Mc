#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

from core.api.services.datapack import sync_datapack, wait_for_datapack
from core.crash_manager import get_crash_manager
from core.error_codes import MC_0002, MC_0003
from core.health_monitor import HealthState, get_health_monitor
from core.java_utils import MIN_JAVA_VERSION, ensure_java
from core.logger import (
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
    start_heartbeat,
)
from core.paths import get_root_dir
from core.server_jar import ServerJarError, ensure_instance_jar
from core.yaml_utils import load_yaml

log = initialize_logging(__name__)
install_global_exception_hook("server")

# ==================================================
# server.py - Minecraft server launcher
# ==================================================
# Configures and starts a Minecraft server with the
# bundled Java runtime. Manages RCON, server.properties,
# EULA acceptance, and the MinecraftServerAPI plugin.
# ==================================================


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _wait_or_skip(prompt: str = "Press Enter to continue..."):
    if _is_interactive():
        try:
            input(prompt)
        except (EOFError, KeyboardInterrupt):
            pass


# === Parse arguments (instance-based only) ===
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument(
    "--instance-dir",
    type=str,
    default=None,
    help="Path to the server instance directory",
)
_parser.add_argument("--port", type=str, default=None, help="Override the server port")
_args, _ = _parser.parse_known_args()

ROOT_DIR = get_root_dir()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

if _args.instance_dir:
    INSTANCE_DIR = Path(_args.instance_dir).resolve()
else:
    INSTANCE_DIR = (ROOT_DIR / "server" / "default").resolve()
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

SERVER_PROPERTIES = (INSTANCE_DIR / "server.properties").resolve()
IGNORE_RCON_FILE = (ROOT_DIR / "config" / ".ignore_rcon_warning").resolve()
PLUGINS_DIR = (INSTANCE_DIR / "plugins").resolve()
CONFIGSERVERAPI_FILE = (PLUGINS_DIR / "MinecraftServerAPI" / "config.yml").resolve()

# === Determine server.jar path (instance-based ONLY) ===
# NO version-based paths. NO legacy paths. NO fallback paths.
SERVER_JAR = (INSTANCE_DIR / "server.jar").resolve()

# If the jar is missing, try to obtain it automatically: download the version
# configured in config.yaml (default 1.21.11) and place it in the instance
# directory. This covers fresh installs/instances where the user never
# manually dropped a jar into the folder.
if not SERVER_JAR.exists():
    log.warning(
        "server.jar not found at %s — attempting automatic download.", SERVER_JAR
    )
    try:
        cfg_probe = load_yaml(CONFIG_FILE) if CONFIG_FILE.exists() else {}
        want_version = str(cfg_probe.get("mc_version", "1.21.11"))
        from core.server_jar import ServerJarError, ensure_instance_jar

        SERVER_JAR = ensure_instance_jar(INSTANCE_DIR.name, want_version)
        log.info(
            "Automatically downloaded server.jar (%s) into the instance directory.",
            want_version,
        )
    except (ServerJarError, OSError, ValueError) as e:
        log.error("server.jar not found at %s", SERVER_JAR)
        log.error(
            "Place a valid Minecraft server.jar in the instance directory and restart."
        )
        log.error("Automatic download failed: %s", e)
        _wait_or_skip()
        sys.exit(1)

log.info("Using instance jar: %s", SERVER_JAR)

# === Java detection ===
# Try to find a usable runtime and, as a last resort for CLI use, attempt an
# automatic installation. In the GUI flow the API already ran this check
# before spawning this process, so we usually only get here when Java exists.
JAVA_STATUS = ensure_java(ROOT_DIR, CONFIG_FILE)
if JAVA_STATUS.ok:
    JAVA_EXE = Path(JAVA_STATUS.path)
    if JAVA_STATUS.source == "config":
        log.info("Using custom Java path from config: %s", JAVA_STATUS.path)
    elif JAVA_STATUS.source == "bundled":
        log.info("Using bundled Java runtime: %s", JAVA_STATUS.path)
    else:
        log.info("Using system Java: %s", JAVA_STATUS.path)
else:
    log.error("No Java runtime available. Cannot start Minecraft server.")
    log.error("Reason: %s", JAVA_STATUS.reason)
    log.error("server.jar path: %s", SERVER_JAR)
    if not JAVA_STATUS.auto_installable:
        log.info("Please install Java %d or newer manually:", MIN_JAVA_VERSION)
        for hint in JAVA_STATUS.hints:
            log.info("  %s", hint)
    crash_mgr = get_crash_manager()
    crash_mgr.report_error(MC_0002, detail=JAVA_STATUS.reason)
    _wait_or_skip()
    sys.exit(1)

# === MinecraftServerAPI config — create default if missing ===
if not CONFIGSERVERAPI_FILE.exists():
    log.info(
        "MinecraftServerAPI config not found at %s — creating default.",
        CONFIGSERVERAPI_FILE,
    )
    CONFIGSERVERAPI_FILE.parent.mkdir(parents=True, exist_ok=True)
    yaml_obj = YAML(typ="rt")
    yaml_obj.preserve_quotes = True
    yaml_obj.indent(mapping=2, sequence=4, offset=2)
    yaml_obj.width = 120
    default_cfg = CommentedMap()
    default_cfg["port"] = 29187
    default_cfg["webhooks"] = {"urls": ["http://127.0.0.1:29188"]}
    try:
        with CONFIGSERVERAPI_FILE.open("w", encoding="utf-8") as f:
            yaml_obj.dump(default_cfg, f)
        log.info("Default MinecraftServerAPI config created.")
    except OSError as e:
        log.warning("Failed to write default config: %s", e)

# === Load configuration ===
Xms = "1G"
Xmx = "1G"
MC_PORT = 25565
WEBSERVERPORT = 29188
APIPORT = 29187
SERVER_HOST = "127.0.0.1"
MC_VERSION = "1.21.11"

try:
    if CONFIG_FILE.exists():
        cfg = load_yaml(CONFIG_FILE)
        Xms = cfg.get("java", {}).get("xms", "1G")
        Xmx = cfg.get("java", {}).get("xmx", "1G")
        MC_PORT = int(
            os.environ.get(
                "RESOLVED_PORT_MC_GAME_PORT", cfg.get("java", {}).get("port", 25565)
            )
        )
        WEBSERVERPORT = int(
            os.environ.get(
                "RESOLVED_PORT_WEBHOOK_PORT",
                cfg.get("minecraft_server_api", {}).get("web_server_port", 29188),
            )
        )
        APIPORT = int(
            os.environ.get(
                "RESOLVED_PORT_MCSERVER_API_PORT",
                cfg.get("minecraft_server_api", {}).get("api_port", 29187),
            )
        )
        SERVER_HOST = cfg.get("server_host", "127.0.0.1")
        MC_VERSION = cfg.get("mc_version", "1.21.11")
    else:
        log.warning("Config not found at %s — using defaults.", CONFIG_FILE)
except (OSError, ValueError, YAMLError) as e:
    log.warning("Failed to load config: %s — using defaults.", e)

# === Port override from CLI ===
if _args.port:
    try:
        MC_PORT = int(_args.port)
        log.info("Port overridden by CLI: %d", MC_PORT)
    except ValueError:
        log.warning("Invalid --port value '%s' — using config default.", _args.port)

# === Ensure MinecraftServerAPI config is in sync ===
if CONFIGSERVERAPI_FILE.exists():
    try:
        yaml_obj = YAML(typ="rt")
        yaml_obj.preserve_quotes = True
        yaml_obj.indent(mapping=2, sequence=4, offset=2)
        yaml_obj.width = 120
        with CONFIGSERVERAPI_FILE.open("r", encoding="utf-8") as f:
            cfg_api = yaml_obj.load(f) or CommentedMap()
    except (OSError, ValueError, YAMLError):
        cfg_api = CommentedMap()

    webhook = cfg_api.setdefault("webhooks", {})
    webhook.setdefault("urls", [f"http://127.0.0.1:{WEBSERVERPORT}"])

    if APIPORT != cfg_api.get("port", 29187):
        cfg_api["port"] = int(APIPORT)

    try:
        with CONFIGSERVERAPI_FILE.open("w", encoding="utf-8") as f:
            yaml_obj.dump(cfg_api, f)
    except OSError as e:
        log.warning("Failed to write MinecraftServerAPI config: %s", e)

# === RCON settings ===
RCON = cfg.get("rcon", {}) if "cfg" in dir() else {}
RCON_ENABLED = RCON.get("enabled", False)
RCON_PASSWORD = RCON.get("password", "")
RCON_PORT = RCON.get("port", 25575)

# === RCON disabled warning (only in interactive mode) ===
if not RCON_ENABLED and not IGNORE_RCON_FILE.exists() and _is_interactive():
    log.info("\nWARNING: RCON is disabled!")
    log.info("Some features may not work correctly without RCON.")
    log.info(
        "It is recommended to enable RCON in the config file unless you know exactly what you are doing.\n"
    )
    log.info("Type one of the following options and press ENTER:")
    log.info("  continue  - Start the server anyway")
    log.info("  ignore    - Do not show this warning again")
    log.info("  break     - Abort startup\n")
    while True:
        try:
            choice = input("Your choice: ").strip().lower()
            if choice == "continue":
                break
            elif choice == "ignore":
                try:
                    with IGNORE_RCON_FILE.open("w", encoding="utf-8") as f:
                        f.write("ignore RCON warning")
                    log.info("RCON warning will be ignored in the future.")
                except OSError as e:
                    log.warning("Could not write ignore file: %s", e)
                break
            elif choice == "break":
                log.info("Startup aborted by user.")
                sys.exit(0)
            else:
                log.info("Invalid input. Please type: continue, ignore, or break.")
        except (EOFError, KeyboardInterrupt):
            break
elif not RCON_ENABLED and not _is_interactive():
    log.info("RCON is disabled — continuing (non-interactive mode).")

# === Accept EULA ===
EULA_FILE = INSTANCE_DIR / "eula.txt"
if not EULA_FILE.exists():
    try:
        with EULA_FILE.open("w", encoding="utf-8") as f:
            f.write("eula=true\n")
        log.info("EULA accepted automatically.")
    except OSError as e:
        log.warning("Could not write eula.txt: %s", e)


# === Update server.properties ===
def set_server_property(file_path: Path, key, value):
    try:
        if not file_path.exists():
            with file_path.open("w", encoding="utf-8") as f:
                f.write("")

        with file_path.open("r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break

        if not found:
            lines.append(f"{key}={value}")

        with file_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError as e:
        log.warning("Failed to set server property %s: %s", key, e)


set_server_property(SERVER_PROPERTIES, "enable-rcon", str(RCON_ENABLED).lower())
set_server_property(SERVER_PROPERTIES, "rcon.password", RCON_PASSWORD)
set_server_property(SERVER_PROPERTIES, "rcon.port", RCON_PORT)
set_server_property(SERVER_PROPERTIES, "server-port", MC_PORT)

# === Empty RCON password warning ===
if RCON_ENABLED and not RCON_PASSWORD:
    log.warning(
        "RCON password is not set! Set one in config.yaml or use the setup wizard."
    )
    log.info(
        "Starting Minecraft server with RCON disabled until a password is configured."
    )
    set_server_property(SERVER_PROPERTIES, "enable-rcon", "false")

# === Sync StreamingTool datapack into the instance world ===
# Vanilla ``/`` actions in actions.mca run as ``function streamingtool:...``,
# so the generated datapack must be present in the world before the server
# boots. The bridge generates it into the staging area concurrently — wait
# briefly for a complete snapshot (see wait_for_datapack).
DP_SOURCE = (ROOT_DIR / "server" / "datapack").resolve()
if not wait_for_datapack(DP_SOURCE):
    log.warning(
        "[DATAPACK] Datapack was not ready within the wait window — "
        "vanilla actions may be unavailable"
    )
sync_datapack(INSTANCE_DIR, DP_SOURCE)

# === Start Minecraft server ===
log.info("\n--- Minecraft Server ---")
log.info("RAM:     %s -> %s", Xms, Xmx)
log.info("Java:    %s", JAVA_EXE)
log.info("Version: %s", MC_VERSION)
log.info("Path:    %s", INSTANCE_DIR)
log.info("Port:    %s", MC_PORT)
log.info("--------------------------\n")

heartbeat = start_heartbeat(log, interval=60.0)
crash_mgr = get_crash_manager()
health = get_health_monitor()
health.register("mc_server", HealthState.STARTING)
try:
    health.set_state("mc_server", HealthState.RUNNING)
    proc = subprocess.run(
        [str(JAVA_EXE), f"-Xms{Xms}", f"-Xmx{Xmx}", "-jar", str(SERVER_JAR), "nogui"],
        cwd=str(INSTANCE_DIR),
        check=False,
    )
    if proc.returncode != 0:
        log.warning("Minecraft server exited with code %s", proc.returncode)
        crash_mgr.report_error(MC_0003, detail=f"Exit code: {proc.returncode}")
        health.set_state("mc_server", HealthState.FAILED)
        sys.exit(proc.returncode)
except FileNotFoundError:
    log.error("Java executable not found: %s", JAVA_EXE)
    crash_mgr.report_error(MC_0002, detail=str(JAVA_EXE))
    health.set_state("mc_server", HealthState.FAILED)
    _wait_or_skip()
    sys.exit(1)
except KeyboardInterrupt:
    log.info("\nServer was stopped manually.")
    health.set_state("mc_server", HealthState.STOPPED)
except Exception as e:  # top-level boundary: report via crash manager and exit
    log.error("Failed to start Minecraft server: %s", e)
    crash_mgr.report_exception(MC_0003, exc=e, context_info={"detail": str(e)})
    handle_unhandled_exception("server")
    health.set_state("mc_server", HealthState.FAILED)
    _wait_or_skip()
    sys.exit(1)
finally:
    health.set_state("mc_server", HealthState.STOPPED)
    heartbeat.stop()

log.info("\nServer stopped.")
