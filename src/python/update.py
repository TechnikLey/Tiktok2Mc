#!/usr/bin/env python3
# ==================================================
# update.py - Auto-updater for the Streaming Tool (P3a)
# ==================================================
# Omaha-style state machine:
#
#   CHECK → FETCH → VERIFY_SIG → VERIFY_SHA → STAGE → FLIP → PRUNE → NOTIFY
#
# - CHECK      local install version vs. latest GitHub release tag
# - FETCH      download the platform archive (+ .sha256 companion)
# - VERIFY_SIG download manifest.json + manifest.json.sig, verify the
#              detached Ed25519 signature (fail closed)
# - VERIFY_SHA archive checksum, then per-file sha256 against the manifest
# - STAGE      extracted ``app-<ver>/`` directory is verified and moved
#              into the install root (atomically via os.replace)
# - FLIP       atomically repoint ``current.json`` at the new version
# - PRUNE      old ``app-<ver>/`` dirs survive one rollback generation,
#              older ones are removed
# - NOTIFY     progress file for the GUI launcher + ``--auto`` relaunch
#
# The updater never touches running processes (no kill choreography);
# a new version becomes active on the next tool restart through the
# ``current.json`` pointer. Launcher binaries (``start``/``update``) are
# swapped by the launcher on the next boot.
# ==================================================

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging import version

from core.checksum import compute_sha256, verify_checksum
from core.crash_manager import get_crash_manager
from core.error_codes import UPDATE_0001
from core.logger import (
    handle_unhandled_exception,
    initialize_logging,
    install_global_exception_hook,
)
from core.paths import get_base_dir, get_runtime_dir
from core.update_engine import manifest as manifest_mod
from core.update_engine import pointer as pointer_mod
from core.update_engine.migration import extract_version, parse_version_txt
from core.update_exit import (
    EXIT_API_ERROR,
    EXIT_CHECKSUM_MISMATCH,
    EXIT_DOWNLOAD_FAILED,
    EXIT_INSTALL_FAILED,
    EXIT_MISSING_CHECKSUM,
    EXIT_NO_ASSET,
    EXIT_NO_UPDATE,
    EXIT_OK,
    EXIT_SIGNATURE_MISMATCH,
    EXIT_UNEXPECTED,
)
from core.utils import load_config

# The updater verifies release manifests against the public key shipped with
# the code; CI replaces the key material at build time (see build.py). Tests
# override it via the T2M_SIGNING_PUBLIC_KEY environment variable.
try:
    from core.release_keys import RELEASE_SIGNING_PUBLIC_KEY
except ImportError:  # pragma: no cover - built binaries always bundle core
    RELEASE_SIGNING_PUBLIC_KEY = ""

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
START_FILE = None
VERSION_FILE = None
UPDATE_STATUS_FILE = None
AUTO_MODE = False
cfg = {}
GITHUB_TOKEN = None
HEADERS_API = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Streaming-Tool-Updater",
}
HEADERS_ASSET = {
    "Accept": "application/octet-stream",
    "User-Agent": "Streaming-Tool-Updater",
}
SIGNING_PUBLIC_KEY = ""


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
        START_FILE, \
        VERSION_FILE, \
        UPDATE_STATUS_FILE, \
        AUTO_MODE, \
        cfg, \
        GITHUB_TOKEN, \
        HEADERS_API, \
        HEADERS_ASSET, \
        SIGNING_PUBLIC_KEY, \
        API_URL
    BASE_DIR = get_base_dir()
    TEMP_DIR = (BASE_DIR / "_update_tmp").resolve()
    VERSION_FILE = (BASE_DIR / "version.txt").resolve()
    START_FILE = (BASE_DIR / f"start{SUFFIX}").resolve()
    UPDATE_STATUS_FILE = (get_runtime_dir() / "update_status.json").resolve()
    AUTO_MODE = "--auto" in sys.argv
    try:
        cfg = load_config((BASE_DIR / "config" / "config.yaml").resolve())
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        log.error("%s", e)
        wait_for_key()
        sys.exit(1)
    if sys.platform != "win32" and cfg.get("show_sudo_warning", True):
        if os.geteuid() != 0:
            if sys.stdin.isatty():
                log.error(
                    "The updater requires root privileges on Linux to replace\n"
                    "application files and set executable permissions.\n"
                    "\n"
                    "Start with: sudo ./update.bin\n"
                    "Or let the GUI handle updates (it elevates automatically)."
                )
                wait_for_key()
                sys.exit(1)
            else:
                log.warning(
                    "Not running as root (no TTY). Continuing anyway — "
                    "updates may fail if file replacement requires elevated "
                    "permissions. Set show_sudo_warning: false in config to "
                    "suppress this warning."
                )
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

    # Test-only hook (mirrors TIKTOK2MC_UPDATE_SOURCE): test key for the
    # manifest signature. Production binaries verify against the public key
    # embedded below; the E2E harness runs the *compiled* updater and needs
    # its own per-test key.
    SIGNING_PUBLIC_KEY = (
        os.environ.get("T2M_SIGNING_PUBLIC_KEY") or RELEASE_SIGNING_PUBLIC_KEY
    )


# ---------------------------------------------------------------------------
# Release source (single source of truth: the GitHub repo coordinates).
# ---------------------------------------------------------------------------
GITHUB_USER = "TechnikLey"
GITHUB_REPO = "Tiktok2Mc"
API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"

MANIFEST_ASSET = "manifest.json"
SIG_ASSET = "manifest.json.sig"


# =========================
# Helper functions
# =========================
def get_local_tool_version(root: Path) -> str:
    """Return the locally installed tool version.

    Resolution: ``current.json`` ``tool_version`` (versioned layout) →
    ``version.txt`` (legacy/migrated layouts) → ``0.0.0``.
    """
    pointer = pointer_mod.read_pointer(root)
    if pointer is not None:
        return pointer.tool_version
    versions = parse_version_txt(root / "version.txt")
    return versions["tool"]


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


def download_bytes(url: str) -> bytes | None:
    """Fetch a small asset into memory; ``None`` on any network/HTTP error."""
    try:
        response = requests.get(url, headers=HEADERS_ASSET, timeout=30)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as exc:
        log.error("Asset download failed (%s): %s", url, exc)
        return None


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
    """Relaunch ``start.exe`` after a successful update.

    With the P3a pointer design the running processes are never touched, so
    a relaunch is purely a convenience for ``--auto`` mode: the launcher
    boots into the version the pointer now names. No-op outside ``--auto``
    mode (manual runs keep the interactive prompt).  Returns ``True`` when
    the relaunch was launched successfully.
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


# =========================
# Persistent status file (kept for legacy readers; the pointer is the
# truth for which version is installed)
# =========================
def save_versions(tool_v, updater_v) -> None:
    """Keep the legacy ``version.txt`` in sync for pre-P3a readers."""
    try:
        VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with VERSION_FILE.open("w", encoding="utf-8") as f:
            f.write(f"ToolVersion: {tool_v}\n")
            f.write(f"UpdaterVersion: {updater_v}\n")
    except OSError as exc:
        log.warning("Could not write version.txt: %s", exc)


# =========================
# Steps
# =========================
def _step_check(root: Path) -> tuple[str, dict]:
    """CHECK: fetch the latest release info and compare versions."""
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
                    log.info("  - Environment variable: set GITHUB_TOKEN=your_token")
                    log.info("  - Or in config.yaml: github_token: your_token")
                    log.info("Create a token at: https://github.com/settings/tokens")
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
    local_tool_v = get_local_tool_version(root)

    if not (version.parse(online_tool_v) > version.parse(local_tool_v)):
        log.info("Tool is up to date (%s).", local_tool_v)
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
    return online_tool_v, release


def _select_asset(release: dict) -> tuple[dict | None, str]:
    """Pick the platform archive asset and its local file name."""
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
    return asset, archive_name


def _step_fetch(release: dict) -> tuple[Path, str, bytes, bytes]:
    """FETCH + VERIFY_SIG: download archive, manifest and detached signature.

    Returns ``(archive_path, archive_asset_name, manifest_raw, sig_raw)``.
    """
    _write_update_status("downloading", progress=0)
    log.info("[>>] Downloading package...")
    asset, archive_name = _select_asset(release)
    if not asset:
        log.error("[FAIL] No matching release asset found for this platform.")
        _write_update_status("error", message="No update file found for this platform.")
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

    # -- Manifest + detached signature (verified against the embedded key) --
    manifest_url = next(
        (a["url"] for a in release.get("assets", []) if a["name"] == MANIFEST_ASSET),
        None,
    )
    sig_url = next(
        (a["url"] for a in release.get("assets", []) if a["name"] == SIG_ASSET),
        None,
    )
    if manifest_url is None:
        log.error("[FAIL] Release does not contain a %s asset.", MANIFEST_ASSET)
        _write_update_status("error", message="Release manifest is missing.")
        sys.exit(EXIT_NO_ASSET)
    manifest_raw = download_bytes(manifest_url)
    if manifest_raw is None:
        wait_for_key()
        _write_update_status("error", message="Release manifest download failed.")
        sys.exit(EXIT_DOWNLOAD_FAILED)
    if sig_url is None:
        log.error("[FAIL] Release does not contain a %s asset.", SIG_ASSET)
        _write_update_status("error", message="Manifest signature is missing.")
        sys.exit(EXIT_SIGNATURE_MISMATCH)
    sig_raw = download_bytes(sig_url)
    if not sig_raw:
        wait_for_key()
        _write_update_status("error", message="Manifest signature is missing.")
        sys.exit(EXIT_SIGNATURE_MISMATCH)

    return archive_path, asset["name"], manifest_raw, sig_raw


def _verify_signature(manifest_raw: bytes, sig_raw: bytes) -> dict:
    """VERIFY_SIG: fail closed unless the manifest is validly signed."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(SIGNING_PUBLIC_KEY)
        )
    except ValueError:
        log.error("[FAIL] No valid signing public key configured; cannot update.")
        wait_for_key()
        _write_update_status("error", message="Updater is missing its signing key.")
        sys.exit(EXIT_SIGNATURE_MISMATCH)

    if not manifest_mod.verify_signature(manifest_raw, sig_raw, public_key):
        log.error("[FAIL] Manifest signature verification failed — rejecting update.")
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        wait_for_key()
        _write_update_status(
            "error",
            message="Manifest signature verification failed — update rejected.",
        )
        sys.exit(EXIT_SIGNATURE_MISMATCH)

    try:
        manifest = manifest_mod.parse_manifest_bytes(manifest_raw)
    except manifest_mod.ManifestError as exc:
        log.error("[FAIL] Manifest payload invalid: %s", exc)
        wait_for_key()
        _write_update_status("error", message="Release manifest is invalid.")
        sys.exit(EXIT_SIGNATURE_MISMATCH)
    log.info(
        "[OK] Manifest signature verified (tool %s, %d files)",
        manifest.tool_version,
        len(manifest.files),
    )
    return manifest.to_dict()


def _verify_archive_checksum(
    archive_path: Path, asset_name: str, release: dict
) -> None:
    """Archive-level integrity: the per-release ``.sha256`` companion."""
    expected_hash = None
    companion_name = asset_name + ".sha256"
    for a in release.get("assets", []):
        if a["name"].lower() == companion_name.lower():
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
            "[FAIL] Could not determine expected checksum (no .sha256 asset). Aborting update."
        )
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        _write_update_status("error", message="Checksum file is missing.")
        sys.exit(EXIT_MISSING_CHECKSUM)

    if not verify_checksum(archive_path, expected_hash):
        log.error("[FAIL] Downloaded archive checksum does not match expected value.")
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        _write_update_status(
            "error", message="Checksum verification failed — file may be corrupted."
        )
        sys.exit(EXIT_CHECKSUM_MISMATCH)


def _extract_archive(archive_path: Path) -> Path:
    """Extract safely and locate the release content root inside ``TEMP_DIR``."""
    log.info("[..] Extracting...")
    _write_update_status("installing", message="Extracting package")
    try:
        if sys.platform == "win32":
            safe_extract_zip(archive_path, TEMP_DIR)
        else:
            safe_extract_tar(archive_path, TEMP_DIR)
    except (ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        log.error("[FAIL] Extraction failed: %s", exc)
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        wait_for_key()
        _write_update_status(
            "error", message="Extraction failed — archive may be corrupted."
        )
        sys.exit(EXIT_INSTALL_FAILED)

    # The release zip may carry its content directly or inside one wrapper
    # directory; the pointer file at the content root identifies it.
    if (TEMP_DIR / "current.json").exists() or (TEMP_DIR / "version.txt").exists():
        return TEMP_DIR
    for child in sorted(TEMP_DIR.iterdir()):
        if child.is_dir() and (
            (child / "current.json").exists() or (child / "version.txt").exists()
        ):
            return child
    return TEMP_DIR  # fallback: behave like the legacy flow


def _verify_files(content_root: Path, manifest: dict) -> None:
    """Per-file sha256 verification against the (signed) manifest."""
    try:
        manifest_obj = manifest_mod.Manifest.from_dict(manifest)
    except (
        manifest_mod.ManifestError
    ) as exc:  # pragma: no cover - _verify_signature parsed it already
        log.error("[FAIL] Manifest payload invalid: %s", exc)
        wait_for_key()
        _write_update_status("error", message="Release manifest is invalid.")
        sys.exit(EXIT_SIGNATURE_MISMATCH)

    failing = manifest_mod.verify_files(content_root, manifest_obj)
    if failing:
        log.error(
            "[FAIL] %d packaged file(s) failed checksum verification: %s",
            len(failing),
            ", ".join(failing[:8]),
        )
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        wait_for_key()
        _write_update_status(
            "error", message="Verification failed — packaged files are corrupted."
        )
        sys.exit(EXIT_CHECKSUM_MISMATCH)


def _step_stage(content_root: Path, manifest: dict) -> tuple[Path, dict | None]:
    """STAGE: move the verified app dir into the install root.

    Returns ``(app_dir, old_pointer)``.
    """
    app_dir_name = f"app-{manifest['tool_version']}"
    staged_app_dir = content_root / app_dir_name
    if not staged_app_dir.is_dir():
        log.error(
            "[FAIL] Staged content is missing its app directory (%s).", app_dir_name
        )
        wait_for_key()
        _write_update_status(
            "error", message="Package layout is unexpected — no app directory."
        )
        sys.exit(EXIT_INSTALL_FAILED)

    old_pointer = pointer_mod.read_pointer(BASE_DIR)
    if old_pointer is not None and old_pointer.active_app_dir == app_dir_name:
        # Guard: never stage the currently active version over itself.
        log.info("[..] Version %s is already active — nothing to do.", app_dir_name)
        _clear_update_status()
        sys.exit(EXIT_OK)

    final_app_dir = BASE_DIR / app_dir_name
    if final_app_dir.exists():
        # Leftover from an interrupted previous run (or a re-download of the
        # same version after a crash) — it is not active, wipe it.
        log.warning("Removing stale app dir before staging: %s", final_app_dir.name)
        shutil.rmtree(final_app_dir, ignore_errors=True)

    log.info("[>>] Staging %s...", app_dir_name)
    try:
        os.replace(staged_app_dir, final_app_dir)
    except OSError as exc:
        log.error("[FAIL] Could not move staged app dir: %s", exc)
        wait_for_key()
        _write_update_status(
            "error",
            message="Could not install the update (files locked or read-only?).",
        )
        sys.exit(EXIT_INSTALL_FAILED)
    return final_app_dir, old_pointer


def _flip_pointer(
    app_dir: Path,
    old_pointer: pointer_mod.AppPointer | None,
    manifest: dict,
    manifest_sha256: str,
) -> None:
    """FLIP: atomically point ``current.json`` at the new version."""
    previous = None
    if old_pointer is not None and old_pointer.active_app_dir != app_dir.name:
        previous = old_pointer.active_app_dir
    pointer_mod.write_pointer(
        BASE_DIR,
        pointer_mod.AppPointer(
            active_app_dir=app_dir.name,
            tool_version=manifest["tool_version"],
            installed_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            manifest_sha256=manifest_sha256,
            previous_app_dir=previous,
        ),
    )
    log.info("[OK] Pointer now active: %s", app_dir.name)


def _swap_launcher_binaries(content_root: Path) -> None:
    """Stage updated root launcher binaries next to their installed ones.

    ``start``/``update`` stay at the install root across version flips and
    are swapped by the launcher at the next boot, so they are written to
    ``<name>_new`` and never override a running binary.
    """
    for name in (f"start{SUFFIX}", f"update{SUFFIX}"):
        source = content_root / name
        if not source.is_file():
            continue
        target = BASE_DIR / name
        pending = BASE_DIR / (name[: -len(SUFFIX)] + f"_new{SUFFIX}")
        if target.is_file() and compute_sha256(source) == compute_sha256(target):
            if pending.is_file():
                try:
                    pending.unlink()
                except OSError:
                    pass  # next run re-checks
            continue
        try:
            shutil.copy2(source, pending)
            if sys.platform != "win32":
                os.chmod(pending, 0o755)
            log.info("[>>] Queued launcher update: %s", pending.name)
        except OSError as exc:
            # A refusal to overwrite the launcher must not abort the app
            # update; the pointer already names the new program version.
            log.warning("Could not queue %s: %s", pending.name, exc)


def _step_prune(app_dir_name: str) -> list[str]:
    """PRUNE: keep the newest rollback generation, drop older dirs."""
    keep_previous = pointer_mod.read_pointer(BASE_DIR)
    previous = keep_previous.previous_app_dir if keep_previous is not None else None
    removed = pointer_mod.prune_versions(BASE_DIR, app_dir_name, previous)
    if removed:
        log.info("[OK] Pruned old version dirs: %s", ", ".join(removed))
    return removed


def _cleanup_temp() -> None:
    if TEMP_DIR and TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


# =========================
# Main update process
# =========================
def run_update():
    # Clear any stale progress report from a previous run, then report a
    # fresh "checking" status so the GUI launcher can show progress.
    _clear_update_status()
    _write_update_status("checking")

    # Legacy argument from the pre-P3a self-update chain — the new flow has
    # no resume; the full state machine is idempotent, just run it.
    if "--resume" in sys.argv:
        log.info("[>] Legacy --resume argument ignored; running full update flow.")

    root = BASE_DIR

    # 1) CHECK
    _online_tool_v, release = _step_check(root)

    _write_update_status("downloading", progress=0)
    # 2) FETCH (+ VERIFY_SIG transport)
    archive_path, asset_name, manifest_raw, sig_raw = _step_fetch(release)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    try:
        (TEMP_DIR / MANIFEST_ASSET).write_bytes(manifest_raw)
        (TEMP_DIR / SIG_ASSET).write_bytes(sig_raw)
    except OSError as exc:  # pragma: no cover - temp writes rarely fail
        log.warning("Could not persist manifest for inspection: %s", exc)

    # 3) VERIFY_SIG
    manifest = _verify_signature(manifest_raw, sig_raw)

    # 4) VERIFY_SHA (transport + content)
    _verify_archive_checksum(archive_path, asset_name, release)
    content_root = _extract_archive(archive_path)
    _verify_files(content_root, manifest)

    # 5) STAGE
    _write_update_status("installing", message="Installing update")
    app_dir, old_pointer = _step_stage(content_root, manifest)

    # 6) FLIP
    _flip_pointer(app_dir, old_pointer, manifest, manifest_sha256)

    # 7) PRUNE
    _step_prune(app_dir.name)

    # Launcher binaries ride along in the same package (swapped next boot).
    _swap_launcher_binaries(content_root)

    # Legacy version file stays in sync for pre-P3a readers.
    updater_version = manifest.get("updater_version") or ""
    if updater_version:
        save_versions(manifest["tool_version"], updater_version)
    else:
        legacy = parse_version_txt(root / "version.txt")
        save_versions(manifest["tool_version"], legacy["updater"])

    # 8) NOTIFY
    _cleanup_temp()
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
