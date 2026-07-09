#!/usr/bin/env python3
# ==========================================
# check_deps.py - Dependency checker & installer
#
# Checks Python packages and system tools,
# installs missing packages automatically.
#
# Usage:
#   python check_deps.py              # Check & install missing Python packages
#   python check_deps.py --install    # Install EVERYTHING (Python + system tools)
#   python check_deps.py --check-only # Only check, don't install
#   python check_deps.py --requirements  # Also pip install from requirements.txt
#   python check_deps.py --system-only   # Only check system tools
#   python check_deps.py --pip-only      # Only check/install Python packages
# ==========================================

import sys
import os
import shutil
import subprocess
import argparse
import importlib.util
from pathlib import Path

# ---- Colors ----
class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def cprint(msg, color=C.RESET):
    print(f"{color}{msg}{C.RESET}")

def header(msg):
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 50}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {msg}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 50}{C.RESET}")

# ---- Package manager detection ----
def _detect_package_manager():
    """Detect the system package manager. Returns (name, install_cmd_prefix) or None."""
    if sys.platform == "win32":
        for name in ["winget", "choco", "scoop"]:
            if shutil.which(name):
                if name == "winget":
                    return name, ["winget", "install", "--accept-package-agreements", "--accept-source-agreements"]
                elif name == "choco":
                    return name, ["choco", "install", "-y"]
                elif name == "scoop":
                    return name, ["scoop", "install"]
        return None, None

    # Linux / macOS
    for name in ["apt", "dnf", "pacman", "zypper", "brew"]:
        if shutil.which(name):
            if name == "apt":
                return name, ["sudo", "apt", "install", "-y"]
            elif name == "dnf":
                return name, ["sudo", "dnf", "install", "-y"]
            elif name == "pacman":
                return name, ["sudo", "pacman", "-S", "--noconfirm"]
            elif name == "zypper":
                return name, ["sudo", "zypper", "install", "-y"]
            elif name == "brew":
                return name, ["brew", "install"]
    return None, None

# ---- Python package definitions ----
# (import_name, pip_name, required_for, optional)
PYTHON_PACKAGES = [
    # Core
    ("yaml",             "PyYAML",          "core",        False),
    ("webview",          "pywebview",       "core",        False),
    ("flask",            "Flask",           "core",        False),
    ("fastapi",          "fastapi",         "core",        False),
    ("uvicorn",          "uvicorn",         "core",        False),
    ("pydantic",         "pydantic",        "core",        False),
    ("requests",         "requests",        "core",        False),
    ("multipart",        "python-multipart","core",        False),
    ("psutil",           "psutil",          "core",        False),

    # Streaming
    ("TikTokLive",       "TikTokLive",      "streaming",   False),
    ("mcrcon",           "mcrcon",          "streaming",   False),

    # Build
    ("PyInstaller",      "pyinstaller",     "build",       False),
    ("packaging",        "packaging",       "build",       False),
    ("ruamel.yaml",      "ruamel.yaml",     "build",       False),

    # Security
    ("cryptography",     "cryptography",    "core",        False),

    # Qt backend
    ("PyQt6",            "PyQt6",           "gui",         False),
    ("PyQt6.WebEngine",  "PyQt6-WebEngine", "gui",         False),
    ("qtpy",             "qtpy",            "gui",         False),

    # Testing
    ("pytest",           "pytest",          "testing",     True),
    ("pytest_timeout",   "pytest-timeout",  "testing",     True),
]

# ---- System tools ----
# (name, check_func, pkg_names, required_for, optional, platform, min_version)

def _get_version(cmd, flag="--version"):
    """Get version string from a command. Returns (major, minor) or None."""
    try:
        result = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=5)
        output = (result.stdout + result.stderr).strip()
        # Extract first digits like "20.19.1" or "v20.19.1"
        import re
        m = re.search(r"(\d+)\.(\d+)", output)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None

def _check_node():
    path = shutil.which("node")
    if not path:
        return False, None
    ver = _get_version("node")
    if not ver:
        return True, None
    if ver[0] < 20:
        return False, f"{ver[0]}.{ver[1]} (need >= 20)"
    return True, f"{ver[0]}.{ver[1]}"

def _check_npm():
    path = shutil.which("npm")
    if not path:
        return False, None
    ver = _get_version("npm")
    if not ver:
        return True, None
    if ver[0] < 10:
        return False, f"{ver[0]}.{ver[1]} (need >= 10)"
    return True, f"{ver[0]}.{ver[1]}"

def _check_binutils():
    return shutil.which("ld") is not None, None

def _check_git():
    return shutil.which("git") is not None, None

def _check_java():
    return shutil.which("java") is not None, None

SYSTEM_TOOLS = [
    # (name, check_func, pkg_names, required_for, optional, platform)
    # pkg_names: dict {pm_name: pkg} for auto-install
    ("node",    _check_node,    {"apt":"nodejs", "dnf":"nodejs", "pacman":"nodejs", "zypper":"nodejs", "brew":"node",
                                 "winget":"OpenJS.NodeJS.LTS", "choco":"nodejs-lts", "scoop":"nodejs"},
                                 "vsix/mca-tests",  False, None),
    ("npm",     _check_npm,     {"apt":"npm", "dnf":"npm", "pacman":"npm", "zypper":"npm", "brew":"npm",
                                 "winget":"OpenJS.NodeJS.LTS", "choco":"nodejs-lts", "scoop":"nodejs"},
                                 "vsix",            False, None),
    ("binutils",_check_binutils,{"apt":"binutils", "dnf":"binutils", "pacman":"binutils", "zypper":"binutils"},
                                 "pyinstaller",     False, "linux"),
    ("git",     _check_git,     {"apt":"git", "dnf":"git", "pacman":"git", "zypper":"git", "brew":"git",
                                 "winget":"Git.Git", "choco":"git", "scoop":"git"},
                                 "general",         False, None),
    ("java",    _check_java,    {"apt":"openjdk-21-jre-headless", "dnf":"java-21-openjdk", "pacman":"jre21-openjdk",
                                 "zypper":"java-21-openjdk", "brew":"openjdk@21",
                                 "winget":"Microsoft.OpenJDK.21", "choco":"temurin21", "scoop":"openjdk21"},
                                 "minecraft-server",False, None),
]


def check_python_package(import_name, pip_name):
    """Check if a Python package is importable."""
    try:
        importlib.util.find_spec(import_name)
        return True
    except (ModuleNotFoundError, ValueError):
        return False


def install_pip_package(pip_name):
    """Install a pip package. Returns True on success."""
    cprint(f"  Installing {pip_name}...", C.YELLOW)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pip_name],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0:
        last_line = (result.stdout + result.stderr).strip().splitlines()[-1:] or [""]
        cprint(f"  + {pip_name} installed  {C.GRAY}{last_line[0]}{C.RESET}", C.GREEN)
        return True
    else:
        cprint(f"  ! Failed to install {pip_name}: {result.stderr.strip()[:200]}", C.RED)
        return False


def pip_install_requirements(req_path):
    """Install all packages from requirements.txt."""
    if not req_path.exists():
        cprint(f"  requirements.txt not found: {req_path}", C.RED)
        return False

    cprint(f"\n  Installing from {req_path.name}...", C.CYAN)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode == 0:
        last_line = (result.stdout + result.stderr).strip().splitlines()[-1:] or [""]
        cprint(f"  + All packages installed  {C.GRAY}{last_line[0]}{C.RESET}", C.GREEN)
        return True
    else:
        cprint(f"  ! pip install failed:\n{result.stderr.strip()[:500]}", C.RED)
        return False


def install_system_tool(name, pkg_names, pm_name, pm_prefix):
    """Install a system tool via the detected package manager."""
    pkg = pkg_names.get(pm_name)
    if not pkg:
        cprint(f"  ! No package mapping for {pm_name} — install {name} manually", C.YELLOW)
        return False

    cprint(f"  Installing {name} ({pkg}) via {pm_name}...", C.YELLOW)
    cmd = pm_prefix + [pkg]
    result = subprocess.run(cmd, text=True, timeout=120)
    if result.returncode == 0:
        cprint(f"  + {name} installed", C.GREEN)
        return True
    else:
        cprint(f"  ! Failed to install {name} (exit code {result.returncode})", C.RED)
        return False


def check_system_tool(name, check_func, pkg_names, category, optional, platform_filter):
    """Check if a system tool is available. Returns (available, version_info)."""
    if platform_filter and sys.platform != platform_filter:
        return None, None
    result = check_func()
    if isinstance(result, tuple):
        available, version_info = result
    else:
        available, version_info = result, None
    if available:
        status = C.GREEN + "OK" + C.RESET
    elif optional:
        status = C.GRAY + "skip" + C.RESET
    else:
        status = C.RED + "MISSING" + C.RESET
    suffix = f"  {C.YELLOW}({version_info}){C.RESET}" if version_info else ""
    cprint(f"  [{status}] {name} ({category}){suffix}")
    return available, version_info


def main():
    parser = argparse.ArgumentParser(
        description="Check and install dependencies for TikTok2Mc",
    )
    parser.add_argument("--install", action="store_true",
                        help="Install everything: Python packages + system tools")
    parser.add_argument("--requirements", action="store_true",
                        help="Also run pip install -r requirements.txt")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check, don't install anything")
    parser.add_argument("--system-only", action="store_true",
                        help="Only check system tools")
    parser.add_argument("--pip-only", action="store_true",
                        help="Only check/install Python packages")
    args = parser.parse_args()

    # --install implies everything (overrides check-only)
    auto_install = args.install

    if sys.platform == "win32":
        os.system("")

    header("TikTok2Mc Dependency Checker")
    if auto_install:
        cprint("  Mode: --install (auto-install everything)\n", C.CYAN)

    SCRIPT_DIR = Path(__file__).resolve().parent
    missing_system = []
    missing_python = []
    installed_count = 0
    skipped_count = 0

    # Detect package manager for system tool installation
    pm_name, pm_prefix = _detect_package_manager()
    if auto_install and pm_name:
        cprint(f"  Package manager: {pm_name}\n", C.GRAY)

    # ── System tools ──
    if not args.pip_only:
        header("System Tools")
        for name, check_func, pkg_names, category, optional, platform_filter in SYSTEM_TOOLS:
            available, version_info = check_system_tool(name, check_func, pkg_names, category, optional, platform_filter)
            if available is None:
                continue
            if not available and not optional:
                if auto_install and pm_name:
                    if install_system_tool(name, pkg_names, pm_name, pm_prefix):
                        installed_count += 1
                    else:
                        missing_system.append((name, pkg_names))
                else:
                    missing_system.append((name, pkg_names))
            elif not available:
                skipped_count += 1

    # ── Python packages ──
    if not args.system_only:
        header("Python Packages")
        categories = {}
        for import_name, pip_name, category, optional in PYTHON_PACKAGES:
            categories.setdefault(category, []).append((import_name, pip_name, optional))

        for cat, pkgs in categories.items():
            cprint(f"\n  {cat.upper()}", C.BOLD)
            for import_name, pip_name, optional in pkgs:
                installed = check_python_package(import_name, pip_name)
                if installed:
                    cprint(f"  [{C.GREEN}OK{C.RESET}] {pip_name}")
                    installed_count += 1
                elif args.check_only:
                    label = "optional" if optional else "REQUIRED"
                    color = C.GRAY if optional else C.RED
                    cprint(f"  [{color}{label}{C.RESET}] {pip_name}")
                    if not optional:
                        missing_python.append(pip_name)
                    else:
                        skipped_count += 1
                else:
                    if optional:
                        cprint(f"  [{C.YELLOW}installing (optional){C.RESET}] {pip_name}")
                    if install_pip_package(pip_name):
                        installed_count += 1
                    elif not optional:
                        missing_python.append(pip_name)
                    else:
                        skipped_count += 1

    # ── Also run requirements.txt if requested ──
    if args.requirements and not args.check_only and not args.system_only:
        header("requirements.txt")
        req_path = SCRIPT_DIR / "requirements.txt"
        pip_install_requirements(req_path)

    # ── Summary ──
    header("Summary")

    if args.check_only:
        if missing_python or missing_system:
            cprint(f"  {len(missing_python)} Python packages missing", C.RED)
            for p in missing_python:
                cprint(f"    - {p}", C.RED)
            cprint(f"  {len(missing_system)} system tools missing", C.RED)
            for name, _ in missing_system:
                cprint(f"    - {name}", C.RED)
            cprint(f"\n  Run with --install to auto-install everything.", C.YELLOW)
            sys.exit(1)
        else:
            cprint("  All dependencies satisfied.", C.GREEN)
            sys.exit(0)
    else:
        if missing_python:
            cprint(f"  {C.RED}{len(missing_python)} Python packages could not be installed:{C.RESET}")
            for p in missing_python:
                cprint(f"    - {p}", C.RED)
        if missing_system:
            cprint(f"\n  {C.YELLOW}System tools that need manual installation:{C.RESET}")
            for name, _ in missing_system:
                hint = next((t[2].get(pm_name, "") for t in SYSTEM_TOOLS if t[0] == name), "")
                if hint:
                    cprint(f"    - {name}: {hint}", C.YELLOW)
                else:
                    cprint(f"    - {name}", C.YELLOW)
            if not auto_install and pm_name:
                cprint(f"\n  {C.CYAN}Tipp: Use --install to auto-install system tools via {pm_name}.{C.RESET}")

        if not missing_python and not missing_system:
            cprint("  Everything is installed.", C.GREEN)
        elif not missing_python and missing_system:
            cprint("\n  All Python packages OK. Some system tools need manual installation.", C.YELLOW)
            if not auto_install and pm_name:
                cprint(f"  {C.CYAN}Tipp: Use --install to auto-install system tools via {pm_name}.{C.RESET}")
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
