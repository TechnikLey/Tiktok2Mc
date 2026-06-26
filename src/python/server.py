#!/usr/bin/env python3
import subprocess
import sys
import shutil
import platform
import re
import zipfile
import urllib.request
import os
from pathlib import Path
from core.paths import get_root_dir
import logging
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from core.yaml_utils import load_yaml
from core.logger import initialize_logging, install_global_exception_hook, start_heartbeat, handle_unhandled_exception

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


_MIN_JAVA_VERSION = 17


def _java_major_version(java_path: Path) -> int | None:
    """Return the major Java version reported by ``java -version``, or None."""
    try:
        result = subprocess.run(
            [str(java_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stderr or result.stdout
        # Lines look like: openjdk version "17.0.8"  or  java version "1.8.0_xxx"
        match = re.search(r'version "([^"]+)"', output)
        if not match:
            return None
        version_str = match.group(1)
        parts = version_str.split(".")
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1])
        return int(parts[0])
    except Exception as exc:
        log.debug("Could not determine Java version for %s: %s", java_path, exc)
        return None


def _java_is_usable(java_path: Path) -> bool:
    """Return True if ``java_path`` exists and is new enough for the server."""
    if not java_path.exists():
        return False
    major = _java_major_version(java_path)
    return major is not None and major >= _MIN_JAVA_VERSION


def _find_java(root_dir: Path, config_path: Path | None = None) -> Path | None:
    # First, check if config specifies a custom Java path
    if config_path and config_path.exists():
        try:
            cfg = load_yaml(config_path)
            custom_java = cfg.get("java", {}).get("path", "")
            if custom_java:
                custom = Path(custom_java)
                if _java_is_usable(custom):
                    log.info("Using custom Java path from config: %s", custom)
                    return custom.resolve()
                log.warning("Custom Java path from config is not usable: %s", custom)
        except Exception as e:
            log.warning("Failed to read custom Java path from config: %s", e)

    bundled = root_dir / "server" / "java" / "bin" / "java.exe"
    if _java_is_usable(bundled):
        return bundled.resolve()

    system_java = shutil.which("java")
    if system_java:
        system_path = Path(system_java).resolve()
        if _java_is_usable(system_path):
            return system_path
        log.warning(
            "System Java at %s is too old (need %d+). Looking for a suitable runtime...",
            system_path, _MIN_JAVA_VERSION,
        )

    if platform.system() == "Windows":
        java_dir = root_dir / "server" / "java"
        java_bin = java_dir / "bin" / "java.exe"
        if not _java_is_usable(java_bin):
            log.info("No suitable Java found. Downloading OpenJDK 21 for Windows...")
            java_dir.mkdir(parents=True, exist_ok=True)
            jdk_url = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.2%2B13/OpenJDK21U-jre_x64_windows_hotspot_21.0.2_13.zip"
            zip_path = java_dir / "java_download.zip"
            try:
                urllib.request.urlretrieve(jdk_url, zip_path)
                log.info("Download complete. Extracting...")
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(java_dir)
                for sub in java_dir.iterdir():
                    if sub.is_dir() and (sub / "bin" / "java.exe").exists():
                        for item in sub.iterdir():
                            target = java_dir / item.name
                            if not target.exists():
                                item.rename(target)
                        shutil.rmtree(sub)
                        break
                zip_path.unlink()
                log.info("Java extraction complete.")
            except Exception as e:
                log.warning(f"Failed to download/extract Java: {e}")
                if zip_path.exists():
                    zip_path.unlink()
        if _java_is_usable(java_bin):
            return java_bin.resolve()
    else:
        log.info("Java not found. Attempting to install via package manager...")
        install_cmds = {
            "apt": ["sudo", "apt", "install", "-y", "openjdk-21-jre-headless"],
            "dnf": ["sudo", "dnf", "install", "-y", "java-21-openjdk-headless"],
            "pacman": ["sudo", "pacman", "-S", "--noconfirm", "jre-openjdk"],
            "zypper": ["sudo", "zypper", "install", "-y", "java-21-openjdk-headless"],
        }
        for pkg_mgr, cmd in install_cmds.items():
            if shutil.which(pkg_mgr):
                log.info(f"Using {pkg_mgr} to install Java...")
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0 and shutil.which("java"):
                        java_path = Path(shutil.which("java")).resolve()
                        if _java_is_usable(java_path):
                            log.info(f"Java installed successfully: {java_path}")
                            return java_path
                    else:
                        log.warning(f"{pkg_mgr} install failed:\n{result.stderr}")
                except Exception as e:
                    log.warning(f"Package manager {pkg_mgr} failed: {e}")
                break
        log.info("\nJava could not be installed automatically.")
        log.info(f"Please install Java {_MIN_JAVA_VERSION} or newer manually:")
        log.info("  Ubuntu/Debian : sudo apt install openjdk-21-jre-headless")
        log.info("  Fedora/RHEL   : sudo dnf install java-21-openjdk-headless")
        log.info("  Arch Linux    : sudo pacman -S jre-openjdk")
        log.info("  openSUSE      : sudo zypper install java-21-openjdk-headless")
        log.info("  macOS         : brew install openjdk@21")
    return None


ROOT_DIR = get_root_dir()
SERVER_DIR = (ROOT_DIR / "server" / "mc").resolve()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
SERVER_JAR = (SERVER_DIR / "server.jar").resolve()
SERVER_PROPERTIES = (SERVER_DIR / "server.properties").resolve()
IGNORE_RCON_FILE = (ROOT_DIR / "config" / ".ignore_rcon_warning").resolve()
PLUGINS_DIR = (SERVER_DIR / "plugins").resolve()
CONFIGSERVERAPI_FILE = (PLUGINS_DIR / "MinecraftServerAPI" / "config.yml").resolve()

# === Java detection ===
JAVA_EXE = _find_java(ROOT_DIR, CONFIG_FILE)
if JAVA_EXE is None:
    log.error("No Java runtime available. Cannot start Minecraft server.")
    log.error("server.jar path: %s", SERVER_JAR)
    _wait_or_skip()
    sys.exit(1)

# === MinecraftServerAPI config — create default if missing ===
if not CONFIGSERVERAPI_FILE.exists():
    log.info("MinecraftServerAPI config not found at %s — creating default.", CONFIGSERVERAPI_FILE)
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
    except Exception as e:
        log.warning("Failed to write default config: %s", e)

# === Load configuration ===
Xms = "1G"
Xmx = "1G"
MC_PORT = 25565
WEBSERVERPORT = 29188
APIPORT = 29187
MINECRAFTSERVERAPI_ENABLED = True
SERVER_HOST = "127.0.0.1"
MC_VERSION = "1.21.11"

try:
    if CONFIG_FILE.exists():
        cfg = load_yaml(CONFIG_FILE)
        Xms = cfg.get("java", {}).get("xms", "1G")
        Xmx = cfg.get("java", {}).get("xmx", "1G")
        MC_PORT = int(os.environ.get("RESOLVED_PORT_MC_GAME_PORT",
                       cfg.get("java", {}).get("port", 25565)))
        WEBSERVERPORT = int(os.environ.get("RESOLVED_PORT_WEBHOOK_PORT",
                           cfg.get("minecraft_server_api", {}).get("web_server_port", 29188)))
        APIPORT = int(os.environ.get("RESOLVED_PORT_MCSERVER_API_PORT",
                       cfg.get("minecraft_server_api", {}).get("api_port", 29187)))
        MINECRAFTSERVERAPI_ENABLED = cfg.get("minecraft_server_api", {}).get("enabled", True)
        SERVER_HOST = cfg.get("server_host", "127.0.0.1")
        MC_VERSION = cfg.get("mc_version", "1.21.11")
    else:
        log.warning("Config not found at %s — using defaults.", CONFIG_FILE)
except Exception as e:
    log.warning("Failed to load config: %s — using defaults.", e)

# === Ensure MinecraftServerAPI config is in sync ===
if CONFIGSERVERAPI_FILE.exists():
    try:
        yaml_obj = YAML(typ="rt")
        yaml_obj.preserve_quotes = True
        yaml_obj.indent(mapping=2, sequence=4, offset=2)
        yaml_obj.width = 120
        with CONFIGSERVERAPI_FILE.open("r", encoding="utf-8") as f:
            cfg_api = yaml_obj.load(f) or CommentedMap()
    except Exception:
        cfg_api = CommentedMap()

    webhook = cfg_api.setdefault("webhooks", {})
    webhook.setdefault("urls", [f"http://127.0.0.1:{WEBSERVERPORT}"])

    if APIPORT != cfg_api.get("port", 29187):
        cfg_api["port"] = int(APIPORT)

    try:
        with CONFIGSERVERAPI_FILE.open("w", encoding="utf-8") as f:
            yaml_obj.dump(cfg_api, f)
    except Exception as e:
        log.warning("Failed to write MinecraftServerAPI config: %s", e)

# === Enable / disable MinecraftServerAPI plugin ===
plugin_name = "MinecraftServerAPI-1.21.x.jar"
plugin_file = PLUGINS_DIR / plugin_name
disabled_file = plugin_file.with_stem(plugin_file.stem + ".disabled")

if not MINECRAFTSERVERAPI_ENABLED:
    if plugin_file.exists():
        try:
            plugin_file.rename(disabled_file)
            log.info(f"{plugin_name} has been disabled.")
        except Exception as e:
            log.warning(f"Failed to disable {plugin_name}: {e}")
    elif disabled_file.exists():
        log.info(f"{plugin_name} is already disabled.")
    else:
        log.info(f"{plugin_name} not found.")
else:
    if disabled_file.exists():
        try:
            disabled_file.rename(plugin_file)
            log.info(f"{plugin_name} has been re-enabled.")
        except Exception as e:
            log.warning(f"Failed to re-enable {plugin_name}: {e}")
    elif plugin_file.exists():
        log.info("No plugin disable requested.")
    else:
        log.info("Plugin not found, activation failed.")

# === RCON settings ===
RCON = cfg.get("rcon", {}) if 'cfg' in dir() else {}
RCON_ENABLED = RCON.get("enabled", False)
RCON_PASSWORD = RCON.get("password", "")
RCON_PORT = RCON.get("port", 25575)

# === Pre-flight checks ===
if not SERVER_JAR.exists():
    log.warning("server.jar not found at %s", SERVER_JAR)
    log.warning("Place a valid Minecraft server.jar in that directory and restart.")
    _wait_or_skip()
    sys.exit(1)

# === RCON disabled warning (only in interactive mode) ===
if not RCON_ENABLED and not IGNORE_RCON_FILE.exists() and _is_interactive():
    log.info("\nWARNING: RCON is disabled!")
    log.info("Some features may not work correctly without RCON.")
    log.info("It is recommended to enable RCON in the config file unless you know exactly what you are doing.\n")
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
                except Exception as e:
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
EULA_FILE = SERVER_DIR / "eula.txt"
if not EULA_FILE.exists():
    try:
        with EULA_FILE.open("w", encoding="utf-8") as f:
            f.write("eula=true\n")
        log.info("EULA accepted automatically.")
    except Exception as e:
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
    except Exception as e:
        log.warning("Failed to set server property %s: %s", key, e)


set_server_property(SERVER_PROPERTIES, "enable-rcon", str(RCON_ENABLED).lower())
set_server_property(SERVER_PROPERTIES, "rcon.password", RCON_PASSWORD)
set_server_property(SERVER_PROPERTIES, "rcon.port", RCON_PORT)
set_server_property(SERVER_PROPERTIES, "server-port", MC_PORT)

# === Empty RCON password warning ===
if RCON_ENABLED and not RCON_PASSWORD:
    log.warning("RCON password is not set! Set one in config.yaml or use the setup wizard.")
    log.info("Starting Minecraft server with RCON disabled until a password is configured.")
    set_server_property(SERVER_PROPERTIES, "enable-rcon", "false")

# === Start Minecraft server ===
log.info("\n--- Minecraft Server ---")
log.info(f"RAM:     {Xms} -> {Xmx}")
log.info(f"Java:    {JAVA_EXE}")
log.info(f"Version: {MC_VERSION}")
log.info(f"Path:    {SERVER_DIR}")
log.info(f"Port:    {MC_PORT}")
log.info("--------------------------\n")

heartbeat = start_heartbeat(log, interval=60.0)
try:
    proc = subprocess.run(
        [str(JAVA_EXE), f"-Xms{Xms}", f"-Xmx{Xmx}", "-jar", str(SERVER_JAR), "nogui"],
        cwd=str(SERVER_DIR),
    )
    if proc.returncode != 0:
        log.warning("Minecraft server exited with code %s", proc.returncode)
        sys.exit(proc.returncode)
except FileNotFoundError:
    log.error("Java executable not found: %s", JAVA_EXE)
    _wait_or_skip()
    sys.exit(1)
except KeyboardInterrupt:
    log.info("\nServer was stopped manually.")
except Exception as e:
    log.error("Failed to start Minecraft server: %s", e)
    handle_unhandled_exception("server")
    _wait_or_skip()
    sys.exit(1)
finally:
    heartbeat.stop()

log.info("\nServer stopped.")
