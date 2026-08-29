#!/usr/bin/env python3
"""Java runtime detection and installation helpers.

Shared by ``src/python/server.py`` (the Minecraft server launcher) and the
API layer so that:

* missing/old Java is detected *before* a server process is spawned,
* the GUI receives a precise, actionable error message instead of a generic
  "failed to start", and
* automatic installation actually works - especially on Linux, where plain
  ``sudo`` fails when the process has no terminal (the GUI launches
  subprocesses detached).  On Linux we therefore prefer ``pkexec`` (PolicyKit
  shows a graphical authentication prompt that does not need a TTY) and fall
  back to non-interactive ``sudo -n``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml.error import YAMLError

log = logging.getLogger(__name__)

MIN_JAVA_VERSION = 25

# Default download sources (Adoptium Temurin 25 JRE, Windows x64) with real
# SHA256 checksums from the Adoptium API (api.adoptium.net). The newest GA
# release is tried first, older ones are kept as fallback mirrors. If a URL is
# updated, the checksum MUST be refreshed too - a mismatch aborts that mirror.
# Format: {"url": "https://...", "sha256": "..."}
_JDK_SOURCES = [
    {
        "url": (
            "https://github.com/adoptium/temurin25-binaries/releases/download/"
            "jdk-25.0.4%2B7/OpenJDK25U-jre_x64_windows_hotspot_25.0.4_7.zip"
        ),
        "sha256": "5b0d58f043f762fa3ee6cc12b6774b59b245cafdcb357e45ce61f822aa9a56cb",
    },
    {
        "url": (
            "https://github.com/adoptium/temurin25-binaries/releases/download/"
            "jdk-25.0.3%2B9/OpenJDK25U-jre_x64_windows_hotspot_25.0.3_9.zip"
        ),
        "sha256": "a183e7280220ad5f6fe94ecbf025a5f10fc5797a0b18c600ed8f813c8158c530",
    },
    {
        "url": (
            "https://github.com/adoptium/temurin25-binaries/releases/download/"
            "jdk-25.0.2%2B10/OpenJDK25U-jre_x64_windows_hotspot_25.0.2_10.zip"
        ),
        "sha256": "1919e7e1603bc5937187139db2d65824f8d95ef42d0423ae9f9f1d9eb97842f6",
    },
]

# Linux package names and the bare install command per package manager.
_LINUX_PACKAGES = {
    "apt": "openjdk-25-jre-headless",
    "dnf": "java-25-openjdk-headless",
    "pacman": "jre-openjdk",
    "zypper": "java-25-openjdk-headless",
}

_PM_INSTALL = {
    "apt": ["apt-get", "install", "-y"],
    "dnf": ["dnf", "install", "-y"],
    "pacman": ["pacman", "-S", "--noconfirm"],
    "zypper": ["zypper", "install", "-y"],
}

# Human-readable install commands shown to the user in the GUI/logs.
INSTALL_HINTS = {
    "apt": "sudo apt install -y openjdk-25-jre-headless",
    "dnf": "sudo dnf install -y java-25-openjdk-headless",
    "pacman": "sudo pacman -S --noconfirm jre-openjdk",
    "zypper": "sudo zypper install -y java-25-openjdk-headless",
}


@dataclass
class JavaStatus:
    ok: bool
    path: str = ""
    version: str = ""
    source: str = ""  # "config" | "bundled" | "system" | ""
    reason: str = ""
    hints: list[str] = field(default_factory=list)
    auto_installable: bool = False


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------


def java_major_version(java_path: Path) -> int | None:
    """Return the major Java version reported by ``java -version``, or None."""
    try:
        result = subprocess.run(
            [str(java_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = result.stderr or result.stdout
        # Lines look like: openjdk version "17.0.8"  or  java version "1.8.0_xxx"
        match = re.search(r'version "([^"]+)"', output)
        if not match:
            return None
        parts = match.group(1).split(".")
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1])
        return int(parts[0])
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        log.debug("Could not determine Java version for %s: %s", java_path, exc)
        return None


def java_version_string(java_path: Path) -> str:
    """Return the raw version string from ``java -version``, or '' on failure."""
    try:
        result = subprocess.run(
            [str(java_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (result.stderr or result.stdout).strip()
        match = re.search(r'version "([^"]+)"', output)
        return match.group(1) if match else output
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("Could not read Java version for %s: %s", java_path, exc)
        return ""


def java_is_usable(java_path: Path, min_version: int = MIN_JAVA_VERSION) -> bool:
    """Return True if ``java_path`` exists and is new enough for the server."""
    if not java_path.exists():
        return False
    major = java_major_version(java_path)
    return major is not None and major >= min_version


def bundled_java_path(root_dir: Path) -> Path:
    """Path of the bundled runtime (``server/java/bin/java``)."""
    exe = "java.exe" if platform.system() == "Windows" else "java"
    return (root_dir / "server" / "java" / "bin" / exe).resolve()


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _package_manager() -> str | None:
    """Return the detected Linux package manager name, or None."""
    if platform.system() == "Windows" or platform.system() == "Darwin":
        return None
    for name in ("apt", "dnf", "pacman", "zypper"):
        if shutil.which(name) or (name == "apt" and shutil.which("apt-get")):
            return name
    return None


def _system_java_path() -> Path | None:
    found = shutil.which("java")
    if not found:
        return None
    return Path(found).resolve()


def _java_home_path() -> Path | None:
    """Return the java executable from ``JAVA_HOME``/``JDK_HOME``, or None.

    Many installs (Eclipse Temurin, Microsoft OpenJDK) set ``JAVA_HOME`` even
    when ``java`` is not on PATH, and some PATH entries (e.g. the Oracle
    ``javapath`` shim after an uninstall) are broken and produce no output.
    Checking the env vars catches both cases.
    """
    home = os.environ.get("JAVA_HOME") or os.environ.get("JDK_HOME")
    if not home:
        return None
    exe = "java.exe" if platform.system() == "Windows" else "java"
    candidate = Path(home) / "bin" / exe
    return candidate if candidate.is_file() else None


def _linux_auto_installable() -> bool:
    """Whether a privileged install can be attempted on this Linux box."""
    if platform.system() != "Linux":
        return False
    if _package_manager() is None:
        return False
    if getattr(os, "geteuid", lambda: -1)() == 0:
        return True
    if shutil.which("pkexec"):
        return True
    if shutil.which("sudo"):
        return True
    return bool(shutil.which("sudo"))


def install_hints() -> list[str]:
    """Return install command hints for the current platform."""
    if platform.system() == "Windows":
        return ["Java is bundled automatically - use the Install Java button."]
    if platform.system() == "Darwin":
        return ["brew install openjdk@25"]
    pm = _package_manager()
    if pm in INSTALL_HINTS:
        return [INSTALL_HINTS[pm]]
    return [
        "Ubuntu/Debian : sudo apt install openjdk-25-jre-headless",
        "Fedora/RHEL   : sudo dnf install java-25-openjdk-headless",
        "Arch Linux    : sudo pacman -S jre-openjdk",
        "openSUSE      : sudo zypper install java-25-openjdk-headless",
        "macOS         : brew install openjdk@25",
    ]


def detect_java(root_dir: Path, config_path: Path | None = None) -> JavaStatus:
    """Detect a usable Java runtime and return a structured status.

    Detection order mirrors the original launcher:
      1. custom ``java.path`` from the config file
      2. bundled runtime under ``server/java/bin/``
      3. ``JAVA_HOME`` / ``JDK_HOME``
      4. ``java`` on the system PATH

    When a candidate exists but is unusable (broken shim, too old) the scan
    continues to the next source instead of stopping, so the user gets a
    complete picture in the failure reason.
    """
    hints = install_hints()
    auto = platform.system() == "Windows" or _linux_auto_installable()
    notes: list[str] = []

    def _usable(source: str, java_path: Path) -> JavaStatus:
        return JavaStatus(
            ok=True,
            path=str(java_path.resolve()),
            version=java_version_string(java_path),
            source=source,
            hints=hints,
            auto_installable=False,
        )

    # 1. Custom path from config
    if config_path and Path(config_path).exists():
        try:
            from core.yaml_utils import load_yaml

            cfg = load_yaml(config_path) or {}
            custom = cfg.get("java", {}).get("path", "")
            if custom:
                custom_path = Path(custom)
                if java_is_usable(custom_path):
                    return _usable("config", custom_path)
                notes.append(
                    f"Custom Java path from config is not usable: {custom} "
                    f"(needs Java {MIN_JAVA_VERSION}+)."
                )
                log.warning("%s", notes[-1])
        except (OSError, ValueError, YAMLError) as exc:
            log.warning("Failed to read custom Java path from config: %s", exc)

    # 2. Bundled runtime
    bundled = bundled_java_path(root_dir)
    if java_is_usable(bundled):
        return _usable("bundled", bundled)

    # 3. JAVA_HOME / JDK_HOME
    java_home = _java_home_path()
    if java_home is not None:
        if java_is_usable(java_home):
            return _usable("system", java_home)
        major = java_major_version(java_home)
        if major is None:
            notes.append(
                f"JAVA_HOME points to {java_home}, but it does not report a version."
            )
        else:
            notes.append(
                f"Found Java {major} at JAVA_HOME ({java_home}), but it is too old "
                f"(need {MIN_JAVA_VERSION}+)."
            )

    # 4. System PATH
    system_path = _system_java_path()
    if system_path is not None:
        major = java_major_version(system_path)
        if major is not None and major >= MIN_JAVA_VERSION:
            return _usable("system", system_path)
        if major is None:
            notes.append(
                f"The 'java' command on PATH ({system_path}) did not report a version."
            )
        else:
            notes.append(
                f"Found Java {major} on PATH ({system_path}), but it is too old "
                f"(need {MIN_JAVA_VERSION}+)."
            )

    if notes:
        reason = " ".join(notes)
    else:
        reason = (
            "No Java installation was found on this system "
            "(checked the bundled runtime, JAVA_HOME and PATH)."
        )
    return JavaStatus(
        ok=False,
        reason=reason,
        hints=hints,
        auto_installable=auto,
    )


def ensure_java(
    root_dir: Path,
    config_path: Path | None = None,
    install: bool = True,
) -> JavaStatus:
    """Detect Java, attempt an automatic install when missing, re-detect.

    Returns the final ``JavaStatus``.  ``install`` defaults to True to keep the
    CLI launcher self-contained; the API layer uses ``detect_java`` for the
    pre-flight check and triggers installation on demand.
    """
    status = detect_java(root_dir, config_path)
    if status.ok or not install:
        return status

    if platform.system() == "Windows":
        _ok, message = install_java_windows(root_dir)
    elif platform.system() == "Linux":
        _ok, message = install_java_linux()
    else:
        return status

    log.info("Java install result: %s", message)
    final = detect_java(root_dir, config_path)
    if not final.ok:
        final.reason = f"{final.reason} ({message})"
    return final


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def _download_file(url: str, dest: Path, timeout: int = 120) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "TikTok2Mc/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 256)


def _verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    """Verify SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 256), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest().lower() == expected_sha256.lower()
    except OSError as exc:
        log.warning("Failed to verify checksum for %s: %s", file_path, exc)
        return False


def install_java_windows(root_dir: Path) -> tuple[bool, str]:
    """Download and extract a bundled Java 25 JRE into ``server/java``.

    Returns ``(ok, message)``.  Never raises; errors are returned so callers
    (CLI and API) can surface them cleanly.
    """
    java_dir = (root_dir / "server" / "java").resolve()
    java_bin = java_dir / "bin" / "java.exe"
    if java_is_usable(java_bin):
        return True, f"Bundled Java already present at {java_bin}"

    try:
        java_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Cannot create Java directory {java_dir}: {exc}"

    zip_path = java_dir / "java_download.zip"
    last_error = None

    for idx, source in enumerate(_JDK_SOURCES):
        url = source["url"]
        expected_sha256 = source["sha256"]
        try:
            log.info(
                "Downloading OpenJDK 25 JRE for Windows (mirror %d/%d)...",
                idx + 1,
                len(_JDK_SOURCES),
            )
            _download_file(url, zip_path)
        except OSError as exc:
            last_error = exc
            log.warning("Java download failed from mirror %d: %s", idx + 1, exc)
            zip_path.unlink(missing_ok=True)
            continue

        # Verify checksum
        if not _verify_checksum(zip_path, expected_sha256):
            log.warning("Checksum verification failed for mirror %d", idx + 1)
            zip_path.unlink(missing_ok=True)
            last_error = ValueError("Checksum mismatch")
            continue

        try:
            log.info("Extracting Java runtime...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(java_dir)
            # Move contents of the single top-level folder up into java_dir.
            java_found = False
            for sub in java_dir.iterdir():
                if sub.is_dir():
                    # Search recursively for java.exe
                    for bin_path in sub.rglob("bin/java.exe"):
                        if bin_path.exists():
                            # Move the entire JDK/JRE structure up
                            for item in sub.iterdir():
                                target = java_dir / item.name
                                if not target.exists():
                                    item.rename(target)
                            shutil.rmtree(sub, ignore_errors=True)
                            java_found = True
                            break
                if java_found:
                    break
            zip_path.unlink(missing_ok=True)
        except (OSError, zipfile.BadZipFile) as exc:
            log.warning("Java extraction failed: %s", exc)
            zip_path.unlink(missing_ok=True)
            last_error = exc
            continue

        if java_is_usable(java_bin):
            return True, f"Java 25 downloaded and extracted to {java_dir}"
        return False, "Java download/extract completed but the runtime is not usable."

    # All mirrors failed
    error_msg = str(last_error) if last_error else "Unknown error"
    return (
        False,
        (
            f"Could not download Java automatically (tried {len(_JDK_SOURCES)} mirrors): {error_msg}. "
            "Check your internet connection and try again."
        ),
    )


def install_java_linux() -> tuple[bool, str]:
    """Install a Java runtime via the system package manager.

    Prefers ``pkexec`` (graphical PolicyKit prompt, works without a TTY which
    is exactly the situation when the GUI spawns background processes).  Falls
    back to non-interactive ``sudo -n``, which only succeeds when the user has
    passwordless sudo - otherwise we return clear instructions instead of
    hanging or printing a confusing error to a hidden console.
    """
    if platform.system() != "Linux":
        return False, "Not a Linux system."

    pm = _package_manager()
    if pm is None:
        return False, "No supported package manager (apt/dnf/pacman/zypper) found."

    pkg = _LINUX_PACKAGES[pm]
    install_args = _PM_INSTALL[pm]

    if getattr(os, "geteuid", lambda: -1)() == 0:
        prefix: list[str] = []
        how = "as root"
    elif shutil.which("pkexec"):
        prefix = ["pkexec"]
        how = "via pkexec (graphical password prompt)"
    elif shutil.which("sudo"):
        prefix = ["sudo", "-n"]
        how = "via sudo -n (passwordless sudo only)"
    else:
        return (
            False,
            (
                f"Automatic installation is not possible (no pkexec/sudo). "
                f"Run the following in a terminal:\n  {INSTALL_HINTS[pm]}"
            ),
        )

    cmd = prefix + install_args + [pkg]
    log.info("Installing Java via %s: %s", how, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, check=False
        )
    except subprocess.TimeoutExpired:
        return False, f"Java installation timed out. Run manually: {INSTALL_HINTS[pm]}"
    except FileNotFoundError:
        return (
            False,
            f"Privileged installer not found. Run manually: {INSTALL_HINTS[pm]}",
        )
    except OSError as exc:
        return (
            False,
            f"Java installation failed ({exc}). Run manually: {INSTALL_HINTS[pm]}",
        )

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()[:400]
        return (
            False,
            (
                f"Java installation failed ({pm} exit {result.returncode}). "
                f"{stderr}\nRun the following in a terminal:\n  {INSTALL_HINTS[pm]}"
            ),
        )

    java_path = _system_java_path()
    if java_path is not None and java_is_usable(java_path):
        version = java_version_string(java_path)
        return (
            True,
            f"Java installed successfully {how}: {java_path} (version {version})",
        )

    return (
        False,
        (
            f"Package manager reported success but Java is still not usable. "
            f"Run manually: {INSTALL_HINTS[pm]}"
        ),
    )
