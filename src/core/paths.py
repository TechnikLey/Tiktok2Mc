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
    # Walk up the directory tree looking for known project-root markers.
    #   Dev marker:   src/core/paths.py
    #   Rel marker:   config/config.yaml
    # This works regardless of exe nesting depth (start.exe → 1 level,
    # app.exe → 2 levels, plugins → 3 levels).
    for parent in [base] + list(base.parents):
        if (parent / "src" / "core" / "paths.py").exists():
            return parent.resolve()
        if (parent / "config" / "config.yaml").exists():
            return parent.resolve()
    return base.parent.parent.resolve()

def get_base_file() -> Path:
    base = get_base_dir()
    return (base / f"main{SUFFIX}").resolve()

def get_config_file() -> Path:
    root = get_root_dir()
    return (root / "config" / "config.yaml").resolve()

def get_plugin_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        import __main__
        return Path(__main__.__file__).resolve().parent
    except (AttributeError, ImportError):
        return Path(sys.executable).resolve().parent

def get_plugin_config_file() -> Path:
    return get_plugin_dir() / "config.yaml"