# ==================================================
# update.py - Auto-updater for the Streaming Tool
# ==================================================
# Checks GitHub releases for new versions, downloads
# and extracts the update package, copies whitelisted
# files into the installation directory, and migrates
# the user config to match the latest template.
# ==================================================

import sys
import shutil
import zipfile
import requests
import re
import time
import io
import yaml
from pathlib import Path
from packaging import version
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from core.paths import get_base_dir

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# =========================
# HTTP headers for GitHub API
# =========================
HEADERS_API = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Streaming-Tool-Updater"
}
HEADERS_ASSET = {
    "Accept": "application/octet-stream",
    "User-Agent": "Streaming-Tool-Updater"
}

# =========================
# Base paths & configuration
# =========================
BASE_DIR = get_base_dir()

TEMP_DIR = (BASE_DIR / "_update_tmp").resolve()
VERSION_FILE = (BASE_DIR / "version.txt").resolve()
DEFAULT_CONFIG_FILE = (BASE_DIR / "config" / "config.default.yaml").resolve()
CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()

# Directories and individual files that may be overwritten by an update
WHITELIST_DIRS = {
    "core",
    "scripts",
    "config",
    "plugins/deathcounter",
    "plugins/likegoal",
    "plugins/overlaytxt",
    "plugins/timer",
    "plugins/wincounter",
}

WHITELIST_FILES = {
    "version.txt",
    "README.md",
    "LICENSE",
    "update.exe",
    "server.exe",
    "start.exe",
    "plugins/registry.exe"
}

GITHUB_USER = "TechnikLey"
GITHUB_REPO = "Tiktok2Mc"
API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"

try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    input("Press Enter to exit...")
    sys.exit(1)

CONFIG_UPDATE_ENABLE = cfg.get("auto_update_config", True)

# =========================
# Helper functions
# =========================
def extract_version(text):
    if not text: return "0.0.0"
    m = re.search(r"(\d+\.\d+(\.\d+)?(-beta|-alpha)?)", str(text))
    return m.group(1) if m else "0.0.0"

def get_versions(path):
    v = {"tool": "0.0.0", "updater": "0.0.0"}
    if isinstance(path, str):
        path = Path(path)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    k, val = map(str.strip, line.split(":", 1))
                    if "toolversion" in k.lower(): v["tool"] = extract_version(val)
                    elif "updaterversion" in k.lower(): v["updater"] = extract_version(val)
    return v

def save_versions(tool_v, updater_v):
    with VERSION_FILE.open("w", encoding="utf-8") as f:
        f.write(f"ToolVersion: {tool_v}\n")
        f.write(f"UpdaterVersion: {updater_v}\n")

def download_with_progress(url, target):
    target = Path(target) if isinstance(target, str) else target
    with requests.get(url, headers=HEADERS_ASSET, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with target.open("wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r>> Downloading: {done / total * 100:5.1f}%", end="")
    print("\n[OK] Download complete.")

# =========================
# Config migration
# =========================
def migrate_config_if_needed() -> bool:
    if not DEFAULT_CONFIG_FILE.exists():
        print(f"[!] Error: {DEFAULT_CONFIG_FILE} is missing.")
        return False

    yaml_obj = YAML(typ="rt")
    yaml_obj.preserve_quotes = True
    yaml_obj.indent(mapping=2, sequence=4, offset=2)
    yaml_obj.width = 120

    # If no user config exists yet, copy the default template
    if not CONFIG_FILE.exists():
        shutil.copy2(DEFAULT_CONFIG_FILE, CONFIG_FILE)
        print("[INFO] config.yaml created from template.")
        return True

    try:
        # Load the master template (preserving comments and structure)
        with DEFAULT_CONFIG_FILE.open("r", encoding="utf-8") as f:
            new_template = yaml_obj.load(f) or CommentedMap()
        
        new_template.yaml_set_start_comment(None)

        new_template.yaml_set_start_comment("DO NOT EDIT the config_version")

        # Load current user values
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            user_data = yaml_obj.load(f) or CommentedMap()
    except Exception as e:
        print(f"[FAIL] Error loading config files: {e}")
        return False

    default_version = int(new_template.get("config_version", 0))
    user_version = int(user_data.get("config_version", 0))

    if user_version >= default_version:
        print("i Config is already up to date.")
        return False

    # Backup the old config file
    backup_path = CONFIG_FILE.with_stem(CONFIG_FILE.stem + ".bak")
    shutil.copy2(CONFIG_FILE, backup_path)
    print(f"[INFO] Backup created: {backup_path}")

    # STRICT INJECTION:
    # Only iterate over keys defined in the template.
    _inject_values_strictly(new_template, user_data)

    # Set version to the template's version
    new_template["config_version"] = default_version

    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        yaml_obj.dump(new_template, f)

    print(f"[OK] Config migrated. Structure & comments match the template 100%.")
    return True

def _inject_values_strictly(template, user_source):
    """
    Walks the template and fills it with user values.
    Keys that only exist in the user file are ignored (dropped).
    """
    for key in template:
        if key in user_source:
            if isinstance(template[key], dict) and isinstance(user_source[key], dict):
                # Recurse into nested structures
                _inject_values_strictly(template[key], user_source[key])
            else:
                # Adopt the user's value, keeping the template's position
                template[key] = user_source[key]

# =========================
# Main update process
# =========================
def run_update():
    # ==========================================
    # 0. RESUME CHECK
    # ==========================================
    extracted_root = None
    # Check if a path was passed as argument (resuming after updater self-update)
    if "--resume" in sys.argv:
        try:
            idx = sys.argv.index("--resume")
            extracted_root = sys.argv[idx + 1]
            print(f"[>] Resume: Using extracted files from {extracted_root}")
        except (ValueError, IndexError):
            pass

    local = get_versions(VERSION_FILE)

    # If no resume, then normal API check and download
    if not extracted_root:
        print("[..] Checking for new version via GitHub...")
        try:
            response = requests.get(API_URL, headers=HEADERS_API, timeout=10)
            response.raise_for_status()
            release = response.json()
        except Exception as e:
            print(f"[FAIL] API error: {e}")
            input("Press Enter to exit...")
            sys.exit(5)

        online_tag = release["tag_name"]
        online_tool_v = extract_version(online_tag)

        if not (version.parse(online_tool_v) > version.parse(local["tool"])):
            print(f"[OK] Tool is up to date ({local['tool']}).")
            input("Press Enter to exit...")
            sys.exit(5)

        if "beta" in online_tag.lower():
            choice = input(f"[!] Beta version {online_tag} available. Install? (y/N): ").lower()
            if choice != 'y': sys.exit(5)

        # Download & extract
        print(f"[>>] Downloading package...")
        asset = next((a for a in release.get("assets", []) if a["name"].endswith(".zip")), None)
        if not asset: sys.exit(5)

        if TEMP_DIR.exists(): shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir(parents=True)
        zip_path = TEMP_DIR / "release.zip"
        download_with_progress(asset["url"], zip_path)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(TEMP_DIR)

        subs = [d for d in {x.name for x in TEMP_DIR.iterdir()} if d != "release.zip"]
        temp_items = [TEMP_DIR / s for s in subs]
        extracted_root = str(next((p for p in temp_items if p.is_dir()), TEMP_DIR))

    # Read versions from the downloaded package
    extracted_root_path = Path(extracted_root) if isinstance(extracted_root, str) else extracted_root
    zip_v = get_versions(extracted_root_path / "version.txt")

    # ==========================================
    # 1. UPDATER SELF-UPDATE (via execv)
    # ==========================================
    if version.parse(zip_v["updater"]) > version.parse(local["updater"]):
        print(f"\ud83d\udd04 New updater found ({zip_v['updater']}).")
        new_up_src = extracted_root_path / "update.exe"
        
        if new_up_src.exists():
            new_up_dest = BASE_DIR / "update_new.exe"
            shutil.copy2(new_up_src, new_up_dest)
            # Save only updater version
            save_versions(local["tool"], zip_v["updater"])
            
            print("\ud83d\ude80 Starting new updater and resuming tool update...")
            # execv replaces the current process with update_new.exe
            # Pass --resume so it continues directly at step 2
            import os
            os.execv(str(new_up_dest), [str(new_up_dest), "--resume", str(extracted_root_path)])
            sys.exit(0)  # Safety fallback

    # ==========================================
    # 2. TOOL UPDATE (copy files)
    # ==========================================
    # Signal the start script to shut down so files are unlocked
    with (BASE_DIR / "update_signal.tmp").open("w") as f: f.write("kill")
    time.sleep(1)  # pause to let the start script exit

    print(f"[..] Installing files...")
    for root, dirs, files in (extracted_root_path).walk():
        rel_path = root.relative_to(extracted_root_path)
        rel_path_str = str(rel_path).replace("\\", "/")
        if rel_path_str != "." and not any(
            rel_path_str == d or rel_path_str.startswith(d + "/") for d in WHITELIST_DIRS
        ): continue

        for file in files:
            if rel_path_str == "." and file not in WHITELIST_FILES: continue
            if file.lower() == "update.exe": continue
            if file.lower() == "config.yaml": continue
            
            src = root / file
            dst = BASE_DIR / rel_path / file
            if rel_path_str.split("/")[0] == "server" and dst.exists(): continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    save_versions(zip_v["tool"], zip_v["updater"])
    if TEMP_DIR.exists(): shutil.rmtree(TEMP_DIR, ignore_errors=True)
    
    if CONFIG_UPDATE_ENABLE: 
        migrate_config_if_needed()

    print("\n[OK] Update complete.")
    input("Press Enter to exit...")

    sys.exit(0)

if __name__ == "__main__":
    run_update()