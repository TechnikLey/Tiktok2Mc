import subprocess
import yaml
import sys
from pathlib import Path
from core.paths import get_base_dir

# ==================================================
# server.py - Minecraft server launcher
# ==================================================
# Configures and starts a Minecraft server with the
# bundled Java runtime. Manages RCON, server.properties,
# EULA acceptance, and the MinecraftServerAPI plugin.
# ==================================================

# === Base paths ===
BASE_DIR = get_base_dir()

SERVER_DIR = (BASE_DIR / "server" / "mc").resolve()
JAVA_EXE = (BASE_DIR / "server" / "java" / "bin" / "java.exe").resolve()
CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()
SERVER_JAR = (SERVER_DIR / "server.jar").resolve()
SERVER_PROPERTIES = (SERVER_DIR / "server.properties").resolve()
IGNORE_RCON_FILE = (BASE_DIR / "config" / ".ignore_rcon_warning").resolve()
PLUGINS_DIR = (SERVER_DIR / "plugins").resolve()
CONFIGSERVERAPI_FILE = (PLUGINS_DIR / "MinecraftServerAPI" / "config.yml").resolve()

if not CONFIGSERVERAPI_FILE.exists():
    print(f"Error: MinecraftServerAPI config file not found at {CONFIGSERVERAPI_FILE}")
    sys.exit(1)

# === Load configuration ===
try:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config missing: {CONFIG_FILE}")

    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    Xms = cfg.get("Java", {}).get("Xms", "1G")
    Xmx = cfg.get("Java", {}).get("Xmx", "1G")
    MC_PORT = cfg.get("Java", {}).get("Port", 25565)
    WEBSERVERPORT = cfg.get("MinecraftServerAPI", {}).get("WebServerPort", 7777)
    APIPORT = cfg.get("MinecraftServerAPI", {}).get("APIPort", 7000)
    MINECRAFTSERVERAPI_ENABLED = cfg.get("MinecraftServerAPI", {}).get("Enable", True)

except Exception as e:
    print(f"Config error: {e}")
    input("Press Enter to continue...")
    sys.exit(1)

with CONFIGSERVERAPI_FILE.open("r", encoding="utf-8") as f:
    cfg_api = yaml.safe_load(f)

    webhook = cfg_api.setdefault("webhooks", {})
    urls = webhook.setdefault("urls", [f"http://localhost:{WEBSERVERPORT}"])
    URL = urls[0]

    if APIPORT != cfg_api.get("port", 7000):
        cfg_api["port"] = int(APIPORT)
    else:
        print("API Port is up to date.")

with CONFIGSERVERAPI_FILE.open("w", encoding="utf-8") as f:
    yaml.safe_dump(cfg_api, f, sort_keys=False)

# === Enable / disable MinecraftServerAPI plugin ===
plugin_name = "MinecraftServerAPI-1.21.x.jar"
plugin_file = PLUGINS_DIR / plugin_name
disabled_file = plugin_file.with_stem(plugin_file.stem + ".disabled")

if not MINECRAFTSERVERAPI_ENABLED:
    # Plugin file exists and is active -> disable it
    if plugin_file.exists():
        plugin_file.rename(disabled_file)
        print(f"{plugin_name} has been disabled.")
    # Plugin is already disabled
    elif disabled_file.exists():
        print(f"{plugin_name} is already disabled.")
    # Plugin file not found at all
    else:
        print(f"{plugin_name} not found.")
else:
    # Re-enable disabled plugin
    if disabled_file.exists():
        disabled_file.rename(plugin_file)
        print(f"{plugin_name} has been re-enabled.")
    elif plugin_file.exists():
        print("No plugin disable requested.")
    else:
        print("Plugin not found, activation failed.")

# === RCON settings ===
RCON = cfg.get("RCON", {})
RCON_ENABLED = RCON.get("Enable", False)
RCON_PASSWORD = RCON.get("Password", "ABC1234")
RCON_PORT = RCON.get("Port", 25575)

# === Pre-flight checks ===
if not JAVA_EXE.exists():
    print("Java not found!")
    sys.exit(1)
if not SERVER_JAR.exists():
    print("server.jar not found!")
    sys.exit(1)

# === Warning if RCON is disabled ===
if not RCON_ENABLED and not IGNORE_RCON_FILE.exists():
    print("\nWARNING: RCON is disabled!")
    print("Some features may not work correctly without RCON.")
    print("It is recommended to enable RCON in the config file unless you know exactly what you are doing.\n")
    print("Type one of the following options and press ENTER:")
    print("  continue  - Start the server anyway")
    print("  ignore    - Do not show this warning again")
    print("  break     - Abort startup\n")

    proceed = False
    while not proceed:
        choice = input("Your choice: ").strip().lower()
        if choice == "continue":
            proceed = True
        elif choice == "ignore":
            with IGNORE_RCON_FILE.open("w", encoding="utf-8") as f:
                f.write("ignore RCON warning")
            print("RCON warning will be ignored in the future.")
            proceed = True
        elif choice == "break":
            print("Startup aborted by user.")
            sys.exit(0)
        else:
            print("Invalid input. Please type: continue, ignore, or break.")

# === Accept EULA ===
EULA_FILE = SERVER_DIR / "eula.txt"
if not EULA_FILE.exists():
    with EULA_FILE.open("w", encoding="utf-8") as f:
        f.write("eula=true\n")

# === Update server.properties ===
def set_server_property(file_path: Path, key, value):
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

set_server_property(SERVER_PROPERTIES, "enable-rcon", str(RCON_ENABLED).lower())
set_server_property(SERVER_PROPERTIES, "rcon.password", RCON_PASSWORD)
set_server_property(SERVER_PROPERTIES, "rcon.port", RCON_PORT)
set_server_property(SERVER_PROPERTIES, "server-port", MC_PORT)

# === Password check ===
if RCON_ENABLED and RCON_PASSWORD == "ABC1234":
    print("\nWARNING: Your RCON password is still 'ABC1234'!")
    print("Please change it in config.yaml before using the server.\n")
    input("Press Enter to continue...")

# === Start Minecraft server ===
print("\n--- Minecraft Server ---")
print(f"RAM:   {Xms} → {Xmx}")
print(f"Java:  {JAVA_EXE}")
print(f"Path:  {SERVER_DIR}")
print(f"Port:  {MC_PORT}")
print("------------------------\n")

try:
    subprocess.run([str(JAVA_EXE), f"-Xms{Xms}", f"-Xmx{Xmx}", "-jar", str(SERVER_JAR), "nogui"], cwd=str(SERVER_DIR))
except KeyboardInterrupt:
    print("\nServer was stopped manually.")

print("\nServer stopped.")
input("Press Enter to exit...")