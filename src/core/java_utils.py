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

MIN_JAVA_VERSION = 17

# Default download source (Adoptium Temurin 21 JRE, Windows x64).
_JDK21_URL = (
    "https://github.com/adoptium/temurin21-binaries/releases/download/"
    "jdk-21.0.2%2B13/OpenJDK21U-jre_x64_windows_hotspot_21.0.2_13.zip"
)

# Linux package names and the bare install command per package manager.
_LINUX_PACKAGES = {
    "apt": "openjdk-21-jre-headless",
    "dnf": "java-21-openjdk-headless",
    "pacman": "jre-openjdk",
    "zypper": "java-21-openjdk-headless",
}

_PM_INSTALL = {
    "apt": ["apt-get", "install", "-y"],
    "dnf": ["dnf", "install", "-y"],
    "pacman": ["pacman", "-S", "--noconfirm"],
    "zypper": ["zypper", "install", "-y"],
}

# Human-readable install commands shown to the user in the GUI/logs.
INSTALL_HINTS = {
    "apt": "sudo apt install -y openjdk-21-jre-headless",
    "dnf": "sudo dnf install -y java-21-openjdk-headless",
    "pacman": "sudo pacman -S --noconfirm jre-openjdk",
    "zypper": "sudo zypper install -y java-21-openjdk-headless",
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


def _linux_auto_installable() -> bool:
    """Whether a privileged install can be attempted on this Linux box."""
    if platform.system() != "Linux":
        return False
    if _package_manager() is None:
        return False
    if os.geteuid() == 0:
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
        return ["brew install openjdk@21"]
    pm = _package_manager()
    if pm in INSTALL_HINTS:
        return [INSTALL_HINTS[pm]]
    return [
        "Ubuntu/Debian : sudo apt install openjdk-21-jre-headless",
        "Fedora/RHEL   : sudo dnf install java-21-openjdk-headless",
        "Arch Linux    : sudo pacman -S jre-openjdk",
        "openSUSE      : sudo zypper install java-21-openjdk-headless",
        "macOS         : brew install openjdk@21",
    ]


def detect_java(root_dir: Path, config_path: Path | None = None) -> JavaStatus:
    """Detect a usable Java runtime and return a structured status.

    Detection order mirrors the original launcher:
      1. custom ``java.path`` from the config file
      2. bundled runtime under ``server/java/bin/``
      3. ``java`` on the system PATH
    """
    hints = install_hints()
    auto = platform.system() == "Windows" or _linux_auto_installable()
    custom_note = ""

    # 1. Custom path from config
    if config_path and Path(config_path).exists():
        try:
            from core.yaml_utils import load_yaml

            cfg = load_yaml(config_path) or {}
            custom = cfg.get("java", {}).get("path", "")
            if custom:
                custom_path = Path(custom)
                if java_is_usable(custom_path):
                    return JavaStatus(
                        ok=True,
                        path=str(custom_path.resolve()),
                        version=java_version_string(custom_path),
                        source="config",
                        hints=hints,
                        auto_installable=False,
                    )
                custom_note = (
                    f"Custom Java path from config is not usable: {custom} "
                    f"(needs Java {MIN_JAVA_VERSION}+)."
                )
                log.warning("%s", custom_note)
        except (OSError, ValueError, YAMLError) as exc:
            log.warning("Failed to read custom Java path from config: %s", exc)

    # 2. Bundled runtime
    bundled = bundled_java_path(root_dir)
    if java_is_usable(bundled):
        return JavaStatus(
            ok=True,
            path=str(bundled),
            version=java_version_string(bundled),
            source="bundled",
            hints=hints,
            auto_installable=False,
        )

    # 3. System PATH
    system_path = _system_java_path()
    if system_path is not None:
        major = java_major_version(system_path)
        if major is not None and major >= MIN_JAVA_VERSION:
            return JavaStatus(
                ok=True,
                path=str(system_path),
                version=java_version_string(system_path),
                source="system",
                hints=hints,
                auto_installable=False,
            )
        if major is None:
            reason = (
                f"Found Java at {system_path} but could not determine its version "
                f"(the 'java' command did not report one). A runtime with Java "
                f"{MIN_JAVA_VERSION}+ is required."
            )
        else:
            reason = (
                f"Found Java at {system_path} but it is too old "
                f"(version {major}, need {MIN_JAVA_VERSION}+)."
            )
        return JavaStatus(
            ok=False,
            reason=reason,
            hints=hints,
            auto_installable=auto,
        )

    if custom_note:
        reason = custom_note + " No other usable Java runtime was found."
    else:
        reason = "No Java installation was found on this system " \
                 "(checked the bundled runtime and PATH)."
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


def install_java_windows(root_dir: Path) -> tuple[bool, str]:
    """Download and extract a bundled Java 21 JRE into ``server/java``.

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
    try:
        log.info("Downloading OpenJDK 21 JRE for Windows...")
        _download_file(_JDK21_URL, zip_path)
    except OSError as exc:
        log.warning("Java download failed: %s", exc)
        zip_path.unlink(missing_ok=True)
        return (
            False,
            (f"Could not download Java automatically (network error): {exc}. "
            "Check your internet connection and try again."),
        )

    try:
        log.info("Extracting Java runtime...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(java_dir)
        # Move contents of the single top-level folder up into java_dir.
        for sub in java_dir.iterdir():
            if sub.is_dir() and (sub / "bin" / "java.exe").exists():
                for item in sub.iterdir():
                    target = java_dir / item.name
                    if not target.exists():
                        item.rename(target)
                shutil.rmtree(sub, ignore_errors=True)
                break
        zip_path.unlink(missing_ok=True)
    except (OSError, zipfile.BadZipFile) as exc:
        log.warning("Java extraction failed: %s", exc)
        zip_path.unlink(missing_ok=True)
        return False, f"Could not extract the downloaded Java runtime: {exc}"

    if java_is_usable(java_bin):
        return True, f"Java 21 downloaded and extracted to {java_dir}"
    return False, "Java download/extract completed but the runtime is not usable."


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

    if os.geteuid() == 0:
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
            (f"Automatic installation is not possible (no pkexec/sudo). "
            f"Run the following in a terminal:\n  {INSTALL_HINTS[pm]}"),
        )

    cmd = prefix + install_args + [pkg]
    log.info("Installing Java via %s: %s", how, " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        return False, f"Java installation timed out. Run manually: {INSTALL_HINTS[pm]}"
    except FileNotFoundError:
        return False, f"Privileged installer not found. Run manually: {INSTALL_HINTS[pm]}"
    except OSError as exc:
        return False, f"Java installation failed ({exc}). Run manually: {INSTALL_HINTS[pm]}"

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()[:400]
        return (
            False,
            (f"Java installation failed ({pm} exit {result.returncode}). "
            f"{stderr}\nRun the following in a terminal:\n  {INSTALL_HINTS[pm]}"),
        )

    java_path = _system_java_path()
    if java_path is not None and java_is_usable(java_path):
        version = java_version_string(java_path)
        return True, f"Java installed successfully {how}: {java_path} (version {version})"

    return (
        False,
        (f"Package manager reported success but Java is still not usable. "
        f"Run manually: {INSTALL_HINTS[pm]}"),
    )
