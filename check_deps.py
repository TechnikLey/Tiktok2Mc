#!/usr/bin/env python3
# ==========================================
# check_deps.py - Dependency checker & installer
#
# Checks Python packages and system tools,
# installs missing packages automatically.
#
# Usage:
#   python check_deps.py              # Check & install all
#   python check_deps.py --requirements  # Also pip install from requirements.txt
#   python check_deps.py --check-only    # Only check, don't install
#   python check_deps.py --system-only   # Only check system tools
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

# System tools: (name, check_func, install_hint, required_for)
def _check_node():
    return shutil.which("node") is not None

def _check_npm():
    return shutil.which("npm") is not None

def _check_binutils():
    return shutil.which("ld") is not None

def _check_git():
    return shutil.which("git") is not None

def _check_java():
    return shutil.which("java") is not None

SYSTEM_TOOLS = [
    ("node",    _check_node,    "https://nodejs.org/",                        "vsix/mca-tests",  False),
    ("npm",     _check_npm,     "https://nodejs.org/",                        "vsix",            False),
    ("binutils",_check_binutils,"sudo apt install binutils",                  "pyinstaller",     False),
    ("git",     _check_git,     "sudo apt install git",                       "general",         False),
    ("java",    _check_java,    "sudo apt install openjdk-21-jre-headless",   "minecraft-server",False),
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
        [sys.executable, "-m", "pip", "install", pip_name, "--quiet"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0:
        cprint(f"  + {pip_name} installed", C.GREEN)
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
        [sys.executable, "-m", "pip", "install", "-r", str(req_path), "--quiet"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode == 0:
        cprint("  + All packages from requirements.txt installed", C.GREEN)
        return True
    else:
        cprint(f"  ! pip install failed:\n{result.stderr.strip()[:500]}", C.RED)
        return False


def check_system_tool(name, check_func, install_hint, category, optional):
    """Check if a system tool is available."""
    available = check_func()
    status = C.GREEN + "OK" + C.RESET if available else (C.GRAY + "skip" + C.RESET if optional else C.RED + "MISSING" + C.RESET)
    cprint(f"  [{status}] {name} ({category})")
    return available, install_hint


def main():
    parser = argparse.ArgumentParser(
        description="Check and install dependencies for TikTok2Mc",
    )
    parser.add_argument("--requirements", action="store_true",
                        help="Also run pip install -r requirements.txt")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check, don't install anything")
    parser.add_argument("--system-only", action="store_true",
                        help="Only check system tools")
    parser.add_argument("--pip-only", action="store_true",
                        help="Only check/install Python packages")
    args = parser.parse_args()

    if sys.platform == "win32":
        os.system("")

    header("TikTok2Mc Dependency Checker")
    SCRIPT_DIR = Path(__file__).resolve().parent
    missing_system = []
    missing_python = []
    installed_count = 0
    skipped_count = 0

    # ── System tools ──
    if not args.pip_only:
        header("System Tools")
        for name, check_func, hint, category, optional in SYSTEM_TOOLS:
            available, _ = check_system_tool(name, check_func, hint, category, optional)
            if not available and not optional:
                missing_system.append((name, hint))
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
            for name, hint in missing_system:
                cprint(f"    - {name}: {hint}", C.RED)
            cprint(f"\n  Run without --check-only to auto-install.", C.YELLOW)
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
            for name, hint in missing_system:
                cprint(f"    - {name}: {hint}", C.YELLOW)

        if not missing_python and not missing_system:
            cprint("  Everything is installed.", C.GREEN)
        elif not missing_python and missing_system:
            cprint("\n  All Python packages OK. Install system tools manually.", C.GREEN)
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
