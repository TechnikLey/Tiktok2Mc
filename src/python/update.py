#!/usr/bin/env python3
# ==================================================
# update.py - Auto-updater for the Streaming Tool
# ==================================================
# Checks GitHub releases for new versions, downloads
# and extracts the update package, copies whitelisted
# files into the installation directory, and migrates
# the user config to match the latest template.
# ==================================================

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import requests
from packaging import version
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

from core.api.server import DEFAULT_PORT
from core.backup import get_backup_manager
from core.checksum import verify_checksum
from core.crash_manager import get_crash_manager
from core.error_codes import UPDATE_0001
from core.logger import (
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
)
from core.paths import get_base_dir, get_runtime_dir
from core.update_exit import (
    EXIT_API_ERROR,
    EXIT_CHECKSUM_MISMATCH,
    EXIT_DOWNLOAD_FAILED,
    EXIT_INSTALL_FAILED,
    EXIT_MISSING_CHECKSUM,
    EXIT_NO_ASSET,
    EXIT_NO_UPDATE,
    EXIT_OK,
    EXIT_UNEXPECTED,
)
from core.utils import load_config, normalize_config_version

log = initialize_logging(__name__)

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"

# ---------------------------------------------------------------------------
# Exit codes — one code per failure class so ``start.py`` and the dashboard
# can report precisely *why* an update did not happen. ``5`` is deliberately
# kept as the benign "nothing to do" code (start.py treats it as "continue").
# Defined centrally in core.update_exit (shared with start.py).
# ---------------------------------------------------------------------------

# API request hardening: a transient DNS/network/HTTP blip must not abort
# an update run. Retry the version check a few times with backoff before
# giving up (403 rate-limit is handled immediately and never retried).
_MAX_API_ATTEMPTS = 3
_API_RETRY_DELAY_SECONDS = 2

# ---------------------------------------------------------------------------
# Sentinel globals — set by _init() when run as script, or patched by tests.
# ---------------------------------------------------------------------------
BASE_DIR = None
TEMP_DIR = None
VERSION_FILE = None
DEFAULT_CONFIG_FILE = None
CONFIG_FILE = None
START_FILE = None
UPDATE_STATUS_FILE = None
AUTO_MODE = False
cfg = {}
CONFIG_UPDATE_ENABLE = True
GITHUB_TOKEN = None
HEADERS_API = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Streaming-Tool-Updater",
}
HEADERS_ASSET = {
    "Accept": "application/octet-stream",
    "User-Agent": "Streaming-Tool-Updater",
}


# ---------------------------------------------------------------------------
def wait_for_key(msg="Press Enter to exit..."):
    if not AUTO_MODE:
        try:
            input(msg)
        except EOFError:
            log.info("\nNo input available.")


def _init():
    global \
        BASE_DIR, \
        TEMP_DIR, \
        VERSION_FILE, \
        DEFAULT_CONFIG_FILE, \
        CONFIG_FILE, \
        START_FILE
    global \
        UPDATE_STATUS_FILE, \
        AUTO_MODE, \
        cfg, \
        CONFIG_UPDATE_ENABLE, \
        GITHUB_TOKEN, \
        HEADERS_API, \
        HEADERS_ASSET, \
        API_URL
    BASE_DIR = get_base_dir()
    TEMP_DIR = (BASE_DIR / "_update_tmp").resolve()
    VERSION_FILE = (BASE_DIR / "version.txt").resolve()
    DEFAULT_CONFIG_FILE = (BASE_DIR / "config" / "config.default.yaml").resolve()
    CONFIG_FILE = (BASE_DIR / "config" / "config.yaml").resolve()
    START_FILE = (BASE_DIR / f"start{SUFFIX}").resolve()
    UPDATE_STATUS_FILE = (get_runtime_dir() / "update_status.json").resolve()
    AUTO_MODE = "--auto" in sys.argv
    try:
        cfg = load_config(CONFIG_FILE)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        log.error("%s", e)
        wait_for_key()
        sys.exit(1)
    if sys.platform != "win32" and cfg.get("show_sudo_warning", True):
        if os.geteuid() != 0:
            if sys.stdin.isatty():
                log.error(
                    "This script must be run as root on Linux to perform updates."
                )
                wait_for_key()
                sys.exit(1)
            else:
                log.warning(
                    "Not running as root (no TTY). Continuing anyway — updates may fail."
                )
    CONFIG_UPDATE_ENABLE = cfg.get("auto_update_config", True)
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or cfg.get("github_token")
    HEADERS_API = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Streaming-Tool-Updater",
    }
    HEADERS_ASSET = {
        "Accept": "application/octet-stream",
        "User-Agent": "Streaming-Tool-Updater",
    }
    if GITHUB_TOKEN:
        HEADERS_API["Authorization"] = f"token {GITHUB_TOKEN}"
        HEADERS_ASSET["Authorization"] = f"token {GITHUB_TOKEN}"

    # Test-only hook: point the updater at a GitHub-compatible local mock
    # server (see tools/update_test/). Production never sets this variable,
    # so the default hardcoded GitHub URL is used unchanged.
    API_URL = os.environ.get("TIKTOK2MC_UPDATE_SOURCE") or API_URL


# Directories and individual files that may be overwritten by an update
WHITELIST_DIRS = {
    "core",
    "scripts",
    "config",
    "plugins/deathcounter",
    "plugins/timer",
    "plugins/wincounter",
    "plugins/spotify",
}

# Individual files in subdirectories that may be overwritten.
WHITELIST_DIR_FILES = {
    "hooks/random/main.py",
    "hooks/example_hook/main.py",
}

WHITELIST_FILES = {
    "version.txt",
    "README.md",
    "LICENSE",
    f"start{SUFFIX}",
}

GITHUB_USER = "TechnikLey"
GITHUB_REPO = "Tiktok2Mc"
API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"

CONFIG_UPDATE_ENABLE = cfg.get("auto_update_config", True)


# =========================
# Helper functions
# =========================
def extract_version(text):
    if not text:
        return "0.0.0"
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
                    if "toolversion" in k.lower():
                        v["tool"] = extract_version(val)
                    elif "updaterversion" in k.lower():
                        v["updater"] = extract_version(val)
    else:
        log.error("Version file not found: %s", path)
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
                        percent = done / total * 100
                        sys.stdout.write(f"\r>> Downloading: {percent:5.1f}%")
                        sys.stdout.flush()
                        _write_update_status("downloading", progress=round(percent, 1))
                    else:
                        _write_update_status("downloading", message="Downloading")
    log.info("\nDownload complete.")


# =========================
# Config migration
# =========================
def migrate_config_if_needed() -> bool:
    if not DEFAULT_CONFIG_FILE.exists():
        log.error("Master template missing: %s", DEFAULT_CONFIG_FILE)
        return False

    yaml_obj = YAML(typ="rt")
    yaml_obj.preserve_quotes = True
    yaml_obj.indent(mapping=2, sequence=4, offset=2)
    yaml_obj.width = 120

    # Case 1: No user config exists
    if not CONFIG_FILE.exists():
        try:
            shutil.copy2(DEFAULT_CONFIG_FILE, CONFIG_FILE)
            log.info("No config found. Created new config from template.")
            return True
        except OSError as e:
            log.error("Failed to copy template: %s", e)
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

    # Version Check (supports "1.0", "0.7", legacy int 7, "v1.0.0")
    try:
        raw_default_val = template_data.get("config_version", "0.0")
        raw_user_val = user_data.get("config_version", "0.0")
        raw_default = normalize_config_version(raw_default_val)
        raw_user = normalize_config_version(raw_user_val)
        default_ver = version.parse(raw_default)
        user_ver = version.parse(raw_user)
    except (ValueError, TypeError) as e:
        log.warning("Version keys are invalid (%s). Forcing migration...", e)
        default_ver, user_ver = version.parse("1.0"), version.parse("0.0")
        raw_default = "1.0"
        raw_user = "0.0"

    if user_ver >= default_ver:
        log.info("Config is up to date (%s).", raw_user)
        return False

    log.info("Migrating config: %s -> %s", raw_user, raw_default)

    # Backup (via centralized BackupManager)
    try:
        bm = get_backup_manager()
        bak = bm.create_backup(CONFIG_FILE, category="migration")
        if bak:
            log.info("Backup created at: %s", bak)
        else:
            log.info("Backup skipped (identical content or too recent)")
    except OSError as e:
        log.error("Migration aborted. Could not create backup: %s", e)
        return False

    # Perform strict injection
    _inject_values_strictly(template_data, user_data)

    # Force the new version number
    template_data["config_version"] = raw_default

    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            yaml_obj.dump(template_data, f)
        log.info("[SUCCESS] Config migrated successfully to %s.", raw_default)
        return True
    except (OSError, YAMLError) as e:
        log.error("[FAIL] Error writing migrated config: %s", e)
        return False


def _inject_values_strictly(template, user_source, path=""):
    # 1. BASE GUARD: If user_source is None or not a dictionary-like object
    if user_source is None:
        if path:
            log.warning(
                f"Configuration path '{path}' is empty in user config. Skipping."
            )
        return
    if not isinstance(user_source, (dict, CommentedMap)):
        if path:
            log.warning(
                f"Expected a section at '{path}', but found {type(user_source).__name__}. Skipping."
            )
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
                    log.warning(
                        f"Section '{current_path}' is empty in user config. Keeping defaults."
                    )
                else:
                    log.warning(
                        f"Type mismatch at '{current_path}': Expected a section, got a value. Skipping."
                    )
            # CASE B: Template expects a simple value (String, Int, Bool, List)
            else:
                if user_value is not None:
                    template[key] = user_value
                    log.debug("Migrated: %s", current_path)
                else:
                    log.debug(
                        f"Value for '{current_path}' is null/empty. Using default."
                    )
        else:
            log.debug("Key '%s' missing in user config. Using default.", current_path)


def load_yaml_with_debug(path, yaml_obj, label):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml_obj.load(f)
            if data is None:
                return CommentedMap()
            return data
    except YAMLError as e:
        log.error("[FAIL] YAML error in %s: %s", label, path)

        # Print line / column if available
        if hasattr(e, "problem_mark") and e.problem_mark is not None:
            mark = e.problem_mark
            log.error("[FAIL] Line: %s, Column: %s", mark.line + 1, mark.column + 1)

        log.error("[FAIL] Details: %s", e)
        return None
    except Exception as e:  # best-effort config load; caller falls back to defaults
        log.error("[FAIL] Unexpected error while loading %s: %s", label, path)
        log.error("[FAIL] Details: %s", e)
        return None


# =========================
# Update progress reporting (GUI launcher feedback)
# =========================
def _write_update_status(phase, progress=None, message=""):
    """Best-effort progress report for the GUI launcher.

    Writes JSON to ``core/runtime/update_status.json`` which ``gui.py``
    exposes to the launcher page via ``LauncherAPI.get_update_status()``.
    All failures are swallowed — progress reporting must never break an
    update in progress.
    """
    if UPDATE_STATUS_FILE is None:
        return
    try:
        UPDATE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"phase": phase, "progress": progress, "message": message}
        UPDATE_STATUS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _clear_update_status():
    """Remove any stale progress file (best-effort)."""
    if UPDATE_STATUS_FILE is None:
        return
    try:
        if UPDATE_STATUS_FILE.exists():
            UPDATE_STATUS_FILE.unlink()
    except OSError:
        pass


def _relaunch_tool_after_update() -> bool:
    """Relaunch ``start.exe`` after a successful auto-install.

    ``start.py`` exits when the updater signals 'kill' so its files can
    be replaced — the updater is the only actor left and must bring the
    application back up.  No-op outside ``--auto`` mode (manual runs keep
    the interactive prompt).  Returns ``True`` when the relaunch was
    launched successfully.
    """
    if not AUTO_MODE:
        return True
    try:
        cmd = [str(START_FILE)]
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
        else:
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        log.info("[OK] Application relaunched.")
        return True
    except OSError as exc:
        log.warning("[WARN] Could not relaunch the application: %s", exc)
        return False


def _install_file_with_retry(src: Path, dst: Path) -> None:
    """Replace ``dst`` with ``src``, retrying briefly on Windows locks.

    Once the updater signals 'kill', ``start.py`` exits and the GUI closes
    its window so its files can be replaced — but on Windows a just-
    terminated process's executable handle is usually released only a moment
    after that process has fully exited (antivirus scanners can add further
    delay).  A short retry window closes that race.  Outside Windows the
    first failure propagates immediately, preserving the original behavior.
    Raises the last ``OSError`` when the file is still locked after the
    retry window.
    """
    tries = (100 if sys.platform == "win32" else 0) + 1
    last_error: OSError | None = None
    for attempt in range(tries):
        try:
            shutil.copy2(src, dst)
            return
        except OSError as exc:
            last_error = exc
            if attempt < tries - 1:
                time.sleep(0.1)
    if last_error is not None:
        raise last_error


# =========================
# Main update process
# =========================
def run_update():
    # Clear any stale progress report from a previous run, then report a
    # fresh "checking" status so the GUI launcher can show progress.
    _clear_update_status()
    _write_update_status("checking")

    # ==========================================
    # 0. RESUME CHECK
    # ==========================================
    extracted_root = None
    # Check if a path was passed as argument (resuming after updater self-update)
    if "--resume" in sys.argv:
        try:
            idx = sys.argv.index("--resume")
            extracted_root = sys.argv[idx + 1]
            log.info("[>] Resume: Using extracted files from %s", extracted_root)
        except (ValueError, IndexError) as e:
            log.error(
                "Failed to parse --resume argument: %s\n sys.argv: %s", e, sys.argv
            )

    local = get_versions(VERSION_FILE)

    # If no resume, then normal API check and download
    if not extracted_root:
        log.info("[..] Checking for new version via GitHub...")
        release = None
        api_error: requests.exceptions.RequestException | None = None
        for attempt in range(1, _MAX_API_ATTEMPTS + 1):
            try:
                response = requests.get(API_URL, headers=HEADERS_API, timeout=10)
                if response.status_code == 403:
                    if "rate limit" in response.text.lower():
                        log.error("[FAIL] GitHub API rate limit exceeded.")
                        log.info("To increase the limit, set a GitHub token:")
                        log.info(
                            "  - Environment variable: set GITHUB_TOKEN=your_token"
                        )
                        log.info("  - Or in config.yaml: github_token: your_token")
                        log.info(
                            "Create a token at: https://github.com/settings/tokens"
                        )
                    else:
                        log.error("[FAIL] API error: 403 Forbidden")
                    wait_for_key()
                    _write_update_status(
                        "error",
                        message="Update server rejected the request (HTTP 403).",
                    )
                    sys.exit(EXIT_API_ERROR)
                response.raise_for_status()
                release = response.json()
                break
            except requests.exceptions.RequestException as e:
                api_error = e
                if attempt < _MAX_API_ATTEMPTS:
                    log.warning(
                        "[..] Update server unreachable (attempt %d/%d): %s — retrying...",
                        attempt,
                        _MAX_API_ATTEMPTS,
                        e,
                    )
                    time.sleep(_API_RETRY_DELAY_SECONDS * attempt)
        if release is None:
            log.error("[FAIL] API error: %s", api_error)
            wait_for_key()
            _write_update_status("error", message="Could not reach the update server.")
            sys.exit(EXIT_API_ERROR)

        online_tag = release["tag_name"]
        online_tool_v = extract_version(online_tag)

        if not (version.parse(online_tool_v) > version.parse(local["tool"])):
            log.info("Tool is up to date (%s).", local["tool"])
            wait_for_key()
            _clear_update_status()
            sys.exit(EXIT_NO_UPDATE)

        if "beta" in online_tag.lower():
            if AUTO_MODE:
                _clear_update_status()
                sys.exit(EXIT_NO_UPDATE)  # skip beta in auto mode
            try:
                choice = input(
                    f"[!] Beta version {online_tag} available. Install? (y/N): "
                ).lower()
            except EOFError:
                choice = "n"
            if choice != "y":
                _clear_update_status()
                sys.exit(EXIT_NO_UPDATE)

        # Download & extract
        _write_update_status("downloading", progress=0)
        log.info("[>>] Downloading package...")
        if sys.platform == "win32":
            asset = next(
                (
                    a
                    for a in release.get("assets", [])
                    if "Windows" in a["name"] and a["name"].endswith(".zip")
                ),
                None,
            )
            archive_name = "release.zip"
        else:
            asset = next(
                (
                    a
                    for a in release.get("assets", [])
                    if "Linux" in a["name"] and a["name"].endswith(".tar.gz")
                ),
                None,
            )
            archive_name = "release.tar.gz"

        if not asset:
            log.error("[FAIL] No matching release asset found for this platform.")
            _write_update_status(
                "error", message="No update file found for this platform."
            )
            sys.exit(EXIT_NO_ASSET)

        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = TEMP_DIR / archive_name
        try:
            download_with_progress(asset["url"], archive_path)
        except requests.exceptions.RequestException as e:
            log.error("[FAIL] Download failed: %s", e)
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR, ignore_errors=True)
            wait_for_key()
            _write_update_status("error", message="Download failed.")
            sys.exit(EXIT_DOWNLOAD_FAILED)

        # ── Integrity verification ──────────────────────────────────
        expected_hash = None
        # Look for a companion .sha256 asset in the same release
        for a in release.get("assets", []):
            if a["name"].lower() == asset["name"].lower() + ".sha256":
                try:
                    r = requests.get(
                        a["url"],
                        headers=HEADERS_ASSET,
                        timeout=10,
                    )
                    r.raise_for_status()
                    for line in r.text.strip().splitlines():
                        parts = line.strip().split()
                        if parts:
                            candidate = parts[0].lower()
                            if len(candidate) == 64 and all(
                                c in "0123456789abcdef" for c in candidate
                            ):
                                expected_hash = candidate
                                break
                except requests.exceptions.RequestException as exc:
                    log.debug("Could not fetch checksum asset: %s", exc)
                break
        if not expected_hash:
            log.error(
                "[FAIL] Could not determine expected checksum (no .sha256 asset, no fallback). Aborting update."
            )
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR, ignore_errors=True)
            _write_update_status("error", message="Checksum file is missing.")
            sys.exit(EXIT_MISSING_CHECKSUM)

        if not verify_checksum(archive_path, expected_hash):
            log.error(
                "[FAIL] Downloaded archive checksum does not match expected value."
            )
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR, ignore_errors=True)
            _write_update_status(
                "error", message="Checksum verification failed — file may be corrupted."
            )
            sys.exit(EXIT_CHECKSUM_MISMATCH)
        # ─────────────────────────────────────────────────────────────

        def safe_extract_zip(zip_path: Path, dest: Path) -> None:
            with zipfile.ZipFile(zip_path, "r") as z:
                # Validate all member paths first (zip slip protection)
                resolved_dest = dest.resolve()
                for member in z.infolist():
                    target = (dest / member.filename).resolve()
                    if not target.is_relative_to(resolved_dest):
                        raise ValueError(f"Zip slip attempt: {member.filename}")
                z.extractall(dest)

        def safe_extract_tar(tar_path: Path, dest: Path) -> None:
            with tarfile.open(tar_path, "r:gz") as t:
                resolved_dest = dest.resolve()
                for member in t.getmembers():
                    target = (dest / member.name).resolve()
                    if not target.is_relative_to(resolved_dest):
                        raise ValueError(f"Path traversal attempt: {member.name}")
                t.extractall(dest)

        if sys.platform == "win32":
            safe_extract_zip(archive_path, TEMP_DIR)
        else:
            safe_extract_tar(archive_path, TEMP_DIR)

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
    extracted_root_path = (
        Path(extracted_root) if isinstance(extracted_root, str) else extracted_root
    )
    zip_v = get_versions(extracted_root_path / "version.txt")

    # ==========================================
    # 1. UPDATER SELF-UPDATE (via execv)
    # ==========================================
    if version.parse(zip_v["updater"]) > version.parse(local["updater"]):
        log.info("[UPDATE] New updater found (%s).", zip_v["updater"])
        new_up_src = extracted_root_path / "core" / f"update{SUFFIX}"

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
            # Pass --resume so it continues directly at step 2. Forward --auto
            # so the resume child can relaunch start.exe (start.py no longer
            # restarts itself on EXIT_OK; see _relaunch_tool_after_update).
            resume_args = ["--resume", str(extracted_root_path)]
            if AUTO_MODE:
                resume_args = ["--auto", *resume_args]
            if sys.platform == "win32":
                subprocess.Popen([str(new_up_dest), *resume_args])
            else:
                os.execv(str(new_up_dest), [str(new_up_dest), *resume_args])
            sys.exit(EXIT_OK)

    log.info(
        f"[UPDATE] Updater is up to date ({local['updater']}). Proceeding with tool update..."
    )

    # ==========================================
    # 2. TOOL UPDATE (copy files)
    # ==========================================
    # Signal the start script to shut down so files are unlocked
    signal_file = BASE_DIR / "update_signal.tmp"
    try:
        signal_file.write_text("kill")
    except OSError as e:
        log.warning("Could not write signal file: %s", e)

    # Also set API-based kill signal
    try:
        requests.put(
            f"http://127.0.0.1:{DEFAULT_PORT}/api/v1/updater/signal",
            json={"signal": "kill"},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        pass  # fallback to file-based signaling

    # Wait for start script to consume the signal (file deleted) or timeout
    for _ in range(30):
        if not signal_file.exists():
            break
        # Also check API signal acknowledgment
        try:
            resp = requests.get(
                f"http://127.0.0.1:{DEFAULT_PORT}/api/v1/updater/signal",
                timeout=2,
            )
            if resp.status_code == 200 and resp.json().get("signal") is None:
                break  # acknowledged via API
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)

    log.info("[..] Installing files...")
    _write_update_status("installing", message="Installing update")
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
        if (
            rel_path_str != "."
            and not any(
                rel_path_str == d or rel_path_str.startswith(d + "/")
                for d in WHITELIST_DIRS
            )
            and not any(f.startswith(rel_path_str + "/") for f in WHITELIST_DIR_FILES)
        ):
            continue

        for file in files:
            if rel_path_str == "." and file not in WHITELIST_FILES:
                continue
            # For subdirectories not covered by WHITELIST_DIRS, only copy whitelisted files
            if rel_path_str != ".":
                dir_whitelisted = any(
                    rel_path_str == d or rel_path_str.startswith(d + "/")
                    for d in WHITELIST_DIRS
                )
                if (
                    not dir_whitelisted
                    and f"{rel_path_str}/{file}" not in WHITELIST_DIR_FILES
                ):
                    continue
            if file.lower() == f"update{SUFFIX}".lower():
                continue
            if file.lower() == "config.yaml":
                continue

            src = root / file
            dst = BASE_DIR / rel_path / file
            if rel_path_str.split("/")[0] == "server" and dst.exists():
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                _install_file_with_retry(src, dst)
            except OSError as exc:
                log.error("[FAIL] Could not install file %s: %s", dst, exc)
                wait_for_key()
                _write_update_status(
                    "error",
                    message="Could not install the update (files locked or read-only?).",
                )
                sys.exit(EXIT_INSTALL_FAILED)

    # Set executable permissions for all files without extension and with .bin extension (Linux/Mac only)
    if sys.platform != "win32":
        for dirpath, dirnames, filenames in os.walk(BASE_DIR):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                # Check if file has no extension or .bin extension
                if not os.path.splitext(fname)[1] or fname.endswith(".bin"):
                    try:
                        os.chmod(fpath, 0o755)
                        log.info("[PERM] Set executable: %s", fpath)
                    except OSError as e:
                        log.info("[PERM] Failed to set executable for %s: %s", fpath, e)

    try:
        save_versions(zip_v["tool"], zip_v["updater"])
    except OSError as exc:
        log.error("[FAIL] Could not write version.txt: %s", exc)
        wait_for_key()
        _write_update_status(
            "error",
            message="Could not install the update (files locked or read-only?).",
        )
        sys.exit(EXIT_INSTALL_FAILED)
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    if CONFIG_UPDATE_ENABLE:
        migrate_config_if_needed()

    try:
        if (BASE_DIR / "update_signal.tmp").exists():
            (BASE_DIR / "update_signal.tmp").unlink()
    except OSError as e:
        log.warning("Could not remove signal file: %s", e)

    # Also clear API signal
    try:
        requests.delete(
            f"http://127.0.0.1:{DEFAULT_PORT}/api/v1/updater/signal",
            timeout=5,
        )
    except requests.exceptions.RequestException:
        pass  # API server may already be gone

    # Bring the application back up: start.py exited on the kill signal,
    # so the updater must relaunch it after the files are replaced.
    relaunched = _relaunch_tool_after_update()
    if relaunched:
        _write_update_status("done")
    else:
        _write_update_status(
            "error",
            message="Update installed, but the system could not be restarted automatically.",
        )

    log.info("\nUpdate complete.")
    wait_for_key()

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    install_global_exception_hook("update")
    crash_mgr = get_crash_manager()
    try:
        _init()
        run_update()
    except KeyboardInterrupt:
        log.info("Update interrupted by user.")
    except Exception as exc:  # top-level boundary: report via crash manager and exit
        _write_update_status("error", message="Unexpected error while updating.")
        crash_mgr.report_exception(
            UPDATE_0001, exc=exc, context_info={"detail": "Update process failed"}
        )
        handle_unhandled_exception("update")
        sys.exit(EXIT_UNEXPECTED)
