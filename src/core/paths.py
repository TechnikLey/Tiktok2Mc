#!/usr/bin/env python3
from pathlib import Path
import sys

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def get_root_dir() -> Path:
    base = get_base_dir()
    return (base.parent.parent).resolve()

def get_base_file() -> Path:
    base = get_base_dir()
    return (base / f"main{SUFFIX}").resolve()

def get_config_file() -> Path:
    root = get_root_dir()
    return (root / "config" / "config.yaml").resolve()

def get_plugin_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    import __main__
    return Path(__main__.__file__).resolve().parent

def get_plugin_config_file() -> Path:
    return get_plugin_dir() / "config.yaml"