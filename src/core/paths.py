from pathlib import Path
import sys

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def get_root_dir() -> Path:
    base = get_base_dir()
    return (base.parent.parent).resolve()

def get_base_file() -> Path:
    base = get_base_dir()
    return (base / "main.exe").resolve()

def get_config_file() -> Path:
    root = get_root_dir()
    return (root / "config" / "config.yaml").resolve()