#!/usr/bin/env python3
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
import tarfile
import requests
import re
import time
import io
import os
import yaml
from pathlib import Path
from packaging import version
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.comments import CommentedMap
from core.paths import get_base_dir
from core.utils import load_config

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

log = logging.getLogger(__name__)

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# =========================
# Base paths & configuration
# =========================
BASE_DIR = get_base_dir()

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"

TEMP_DIR = (BASE_DIR / "_update_tmp").resolve()
VERSION_FILE = (BASE_DIR / "version.txt").resolve()
DEFAULT_CONFIG_FILE = (BASE_DIR / "config" / "config.default.yaml").resolve()
CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()
START_FILE = (BASE_DIR / f"start{SUFFIX}").resolve()

def wait_for_key(msg="Press Enter to exit..."):
    if not AUTO_MODE:
        try:
            input(msg)
        except EOFError:
            log.info("\nNo input available.")

try:
    cfg = load_config(CONFIG_FILE)
except (FileNotFoundError, ValueError, RuntimeError) as e:
    log.error(f"{e}")
    wait_for_key()
    sys.exit(1)

if sys.platform != "win32" and cfg.get("show_sudo_warning", True):
    if os.geteuid() != 0:
        log.error("This script must be run as root on Linux to perform updates.")
        wait_for_key()
        sys.exit(1)

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
    "plugins/spotify",
}

WHITELIST_FILES = {
    "version.txt",
    "README.md",
    "LICENSE",
    f"update{SUFFIX}",
    f"server{SUFFIX}",
    f"start{SUFFIX}",
    f"plugins/registry{SUFFIX}",
    f"plugins/plugin_updater{SUFFIX}",
}

GITHUB_USER = "TechnikLey"
GITHUB_REPO = "Tiktok2Mc"
API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"

AUTO_MODE = "--auto" in sys.argv

try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    log.info(f"Error loading config: {e}")
    wait_for_key()
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
    else:
        log.error(f"Version file not found: {path}")
        wait_for_key()

    return v

def save_versions(tool_v, updater_v):
    with VERSION_FILE.open("w", encoding="utf-8") as f:
        f.write(f"ToolVersion: {tool_v}\n")
        f.write(f"UpdaterVersion: {updater_v}\n")

def download_with_progress(url, target):
    target = Path(target) if isinstance(target, str) else target
    with requests.get(url, headers=HEADERS_ASSET, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0) or 0)
        done = 0
        with target.open("wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        sys.stdout.write(f"\r>> Downloading: {done / total * 100:5.1f}%")
                        sys.stdout.flush()
    log.info("\nDownload complete.")

# =========================
# Config migration
# =========================
def migrate_config_if_needed() -> bool:
    if not DEFAULT_CONFIG_FILE.exists():
        log.error(f"Master template missing: {DEFAULT_CONFIG_FILE}")
        return False

    yaml_obj = YAML(typ="rt")
    yaml_obj.preserve_quotes = True
    yaml_obj.indent(mapping=2, sequence=4, offset=2)
    yaml_obj.width = 120

    # Case 1: No user config exists
    if not CONFIG_FILE.exists():
        try:
            shutil.copy2(DEFAULT_CONFIG_FILE, CONFIG_FILE)
            log.info(f"No config found. Created new config from template.")
            return True
        except Exception as e:
            log.error(f"Failed to copy template: {e}")
            return False

    # Load Template
    template_data = load_yaml_with_debug(DEFAULT_CONFIG_FILE, yaml_obj, "Template")
    if template_data is None:
        return False

    # Clean up template start comments
    template_data.yaml_set_start_comment("DO NOT EDIT the config_version")

    # Load User Config
    user_data = load_yaml_with_debug(CONFIG_FILE, yaml_obj, "User Config")
    if user_data is None:
        return False

    # Version Check
    try:
        default_version = int(template_data.get("config_version", 0))
        user_version = int(user_data.get("config_version", 0))
    except (ValueError, TypeError):
        log.warning("Version keys are invalid. Forcing migration...")
        default_version, user_version = 1, 0

    if user_version >= default_version:
        log.info(f"Config is up to date (v{user_version}).")
        return False

    log.info(f"Migrating config: v{user_version} -> v{default_version}")

    # Backup
    backup_path = CONFIG_FILE.with_suffix(".yaml.bak")
    try:
        shutil.copy2(CONFIG_FILE, backup_path)
        log.info(f"Backup created at: {backup_path}")
    except Exception as e:
        log.error(f"Migration aborted. Could not create backup: {e}")
        return False

    # Perform strict injection
    _inject_values_strictly(template_data, user_data)

    # Force the new version number
    template_data["config_version"] = default_version

    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            yaml_obj.dump(template_data, f)
        log.info(f"[SUCCESS] Config migrated successfully to v{default_version}.")
        return True
    except Exception as e:
        log.error(f"[FAIL] Error writing migrated config: {e}")
        return False

def _inject_values_strictly(template, user_source, path=""):
    # 1. BASE GUARD: If user_source is None or not a dictionary-like object
    if user_source is None:
        if path:
            log.warning(f"Configuration path '{path}' is empty in user config. Skipping.")
        return
    if not isinstance(user_source, (dict, CommentedMap)):
        if path:
            log.warning(f"Expected a section at '{path}', but found {type(user_source).__name__}. Skipping.")
        return
    # 2. ITERATE: Only if user_source is guaranteed to be a dict
    for key in template:
        current_path = f"{path}.{key}" if path else key 
        # Check if user actually has this key
        if key in user_source:
            user_value = user_source[key]
            template_value = template[key]
            # CASE A: Both are nested structures -> Recurse
            if isinstance(template_value, (dict, CommentedMap)):
                if isinstance(user_value, (dict, CommentedMap)):
                    _inject_values_strictly(template_value, user_value, current_path)
                elif user_value is None:
                    # User left a whole category empty (e.g., 'Java: ')
                    log.warning(f"Section '{current_path}' is empty in user config. Keeping defaults.")
                else:
                    log.warning(f"Type mismatch at '{current_path}': Expected a section, got a value. Skipping.")
            # CASE B: Template expects a simple value (String, Int, Bool, List)
            else:
                if user_value is not None:
                    template[key] = user_value
                    log.debug(f"Migrated: {current_path}")
                else:
                    log.debug(f"Value for '{current_path}' is null/empty. Using default.")
        else:
            log.debug(f"Key '{current_path}' missing in user config. Using default.")

def load_yaml_with_debug(path, yaml_obj, label):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml_obj.load(f)
            if data is None:
                return CommentedMap()
            return data
    except YAMLError as e:
        log.error(f"[FAIL] YAML error in {label}: {path}")

        # Print line / column if available
        if hasattr(e, "problem_mark") and e.problem_mark is not None:
            mark = e.problem_mark
            log.error(f"[FAIL] Line: {mark.line + 1}, Column: {mark.column + 1}")

        log.error(f"[FAIL] Details: {e}")
        return None
    except Exception as e:
        log.error(f"[FAIL] Unexpected error while loading {label}: {path}")
        log.error(f"[FAIL] Details: {e}")
        return None

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
            log.info(f"[>] Resume: Using extracted files from {extracted_root}")
        except (ValueError, IndexError) as e:
            log.error(f"Failed to parse --resume argument: {e}\n sys.argv: {sys.argv}")

    local = get_versions(VERSION_FILE)

    # If no resume, then normal API check and download
    if not extracted_root:
        log.info("[..] Checking for new version via GitHub...")
        try:
            response = requests.get(API_URL, headers=HEADERS_API, timeout=10)
            response.raise_for_status()
            release = response.json()
        except Exception as e:
            log.error(f"[FAIL] API error: {e}")
            wait_for_key()
            sys.exit(5)

        online_tag = release["tag_name"]
        online_tool_v = extract_version(online_tag)

        if not (version.parse(online_tool_v) > version.parse(local["tool"])):
            log.info(f"Tool is up to date ({local['tool']}).")
            wait_for_key()
            sys.exit(5)

        if "beta" in online_tag.lower():
            if AUTO_MODE:
                sys.exit(5)  # skip beta in auto mode
            choice = input(f"[!] Beta version {online_tag} available. Install? (y/N): ").lower()
            if choice != 'y': sys.exit(5)

        # Download & extract
        log.info("[>>] Downloading package...")
        if sys.platform == "win32":
            asset = next((a for a in release.get("assets", []) if "Windows" in a["name"] and a["name"].endswith(".zip")), None)
            archive_name = "release.zip"
        else:
            asset = next((a for a in release.get("assets", []) if "Linux" in a["name"] and a["name"].endswith(".tar.gz")), None)
            archive_name = "release.tar.gz"

        if not asset:
            log.error("[FAIL] No matching release asset found for this platform.")
            sys.exit(5)

        if TEMP_DIR.exists(): shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir(parents=True)
        archive_path = TEMP_DIR / archive_name
        download_with_progress(asset["url"], archive_path)

        if sys.platform == "win32":
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(TEMP_DIR)
        else:
            with tarfile.open(archive_path, "r:gz") as t:
                t.extractall(TEMP_DIR)

        if (TEMP_DIR / "version.txt").exists():
            extracted_root = TEMP_DIR
        else:
            found = False
            for x in TEMP_DIR.iterdir():
                if x.is_dir() and (x / "version.txt").exists():
                    extracted_root = x
                    found = True
                    break
            if not found:
                extracted_root = TEMP_DIR  # Fallback

    # Read versions from the downloaded package
    extracted_root_path = Path(extracted_root) if isinstance(extracted_root, str) else extracted_root
    zip_v = get_versions(extracted_root_path / "version.txt")

    # ==========================================
    # 1. UPDATER SELF-UPDATE (via execv)
    # ==========================================
    if version.parse(zip_v["updater"]) > version.parse(local["updater"]):
        log.info(f"[UPDATE] New updater found ({zip_v['updater']}).")
        new_up_src = extracted_root_path / f"update{SUFFIX}"
        
        if new_up_src.exists():
            new_up_dest = BASE_DIR / f"update_new{SUFFIX}"
            shutil.copy2(new_up_src, new_up_dest)
            # Save only updater version
            save_versions(local["tool"], zip_v["updater"])
            # Set executable permissions on Linux/Mac
            if sys.platform != "win32":
                os.chmod(new_up_dest, 0o755)
            log.info("Starting new updater and resuming tool update...")
            # execv replaces the current process with the new updater
            # Pass --resume so it continues directly at step 2
            os.execv(str(new_up_dest), [str(new_up_dest), "--resume", str(extracted_root_path)])
            sys.exit(0)  # Safety fallback

    log.info(f"[UPDATE] Updater is up to date ({local['updater']}). Proceeding with tool update...")

    # ==========================================
    # 2. TOOL UPDATE (copy files)
    # ==========================================
    # Signal the start script to shut down so files are unlocked
    with (BASE_DIR / "update_signal.tmp").open("w") as f: f.write("kill")
    time.sleep(5)  # pause to let the start script exit

    log.info("[..] Installing files...")
    walk_method = getattr(extracted_root_path, "walk", None)
    if walk_method is not None:
        walk_iter = walk_method()
    else:
        import os as _os
        def _fallback_walk():
            for root, dirs, files in _os.walk(extracted_root_path):
                yield Path(root), dirs, files
        walk_iter = _fallback_walk()
    for root, dirs, files in walk_iter:
        rel_path = root.relative_to(extracted_root_path)
        rel_path_str = str(rel_path).replace("\\", "/")
        if rel_path_str != "." and not any(
            rel_path_str == d or rel_path_str.startswith(d + "/") for d in WHITELIST_DIRS
        ): continue

        for file in files:
            if rel_path_str == "." and file not in WHITELIST_FILES: continue
            if file.lower() == f"update{SUFFIX}".lower(): continue
            if file.lower() == "config.yaml": continue
            
            src = root / file
            dst = BASE_DIR / rel_path / file
            if rel_path_str.split("/")[0] == "server" and dst.exists(): continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Set executable permissions for all files without extension and with .bin extension (Linux/Mac only)
    if sys.platform != "win32":
        for dirpath, dirnames, filenames in os.walk(BASE_DIR):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                # Check if file has no extension or .bin extension
                if not os.path.splitext(fname)[1] or fname.endswith('.bin'):
                    try:
                        os.chmod(fpath, 0o755)
                        log.info(f"[PERM] Set executable: {fpath}")
                    except Exception as e:
                        log.info(f"[PERM] Failed to set executable for {fpath}: {e}")

    save_versions(zip_v["tool"], zip_v["updater"])
    if TEMP_DIR.exists(): shutil.rmtree(TEMP_DIR, ignore_errors=True)

    if CONFIG_UPDATE_ENABLE: 
        migrate_config_if_needed()

    if (BASE_DIR / "update_signal.tmp").exists():
        (BASE_DIR / "update_signal.tmp").unlink()

    log.info("\nUpdate complete.")
    wait_for_key()

    sys.exit(0)

if __name__ == "__main__":
    run_update()