# ==================================================
# registry.py - Plugin discovery & registration
# ==================================================
# Scans the plugins directory for executables, runs
# them with --register-only to collect metadata, and
# maintains a persistent JSON registry of all plugins.
# ==================================================

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import subprocess
import threading
from typing import Any
from core.paths import get_base_dir
from core.models import AppConfig, validate_config_dict

# --- Paths ---
BASE_DIR = get_base_dir()

APP_REGISTRY_FILE = (BASE_DIR / "PLUGIN_REGISTRY.json").resolve()
SCAN_CACHE_FILE = (BASE_DIR / "plugin_registry_scan_cache.json").resolve()

# --- In-memory state ---
PLUGIN_REGISTRY: list[AppConfig] = []
PLUGIN_REGISTRY_BY_NAME: dict[str, AppConfig] = {}
SCAN_CACHE: dict[str, dict[str, Any]] = {}

_REGISTRY_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()


# ==================================================
# File I/O helpers
# ==================================================

def _write_json_atomic(path: Path, data: Any) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.replace(path)


def _read_registry_file() -> list[AppConfig]:
    if not APP_REGISTRY_FILE.exists():
        return []

    with APP_REGISTRY_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Registry JSON must contain a list of app objects.")

    registry: list[AppConfig] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each registry entry must be a JSON object.")
        validate_config_dict(item)
        registry.append(AppConfig.from_dict(item))

    return registry


def _read_scan_cache_file() -> dict[str, dict[str, Any]]:
    if not SCAN_CACHE_FILE.exists():
        return {}

    with SCAN_CACHE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Scan cache JSON must contain an object.")

    cache: dict[str, dict[str, Any]] = {}
    for exe_path, entry in data.items():
        if not isinstance(exe_path, str) or not isinstance(entry, dict):
            continue

        fingerprint = entry.get("fingerprint")
        config = entry.get("config")
        if not isinstance(fingerprint, dict) or not isinstance(config, dict):
            continue

        cache[exe_path] = {
            "fingerprint": fingerprint,
            "config": config,
        }

    return cache


def _save_registry_file() -> None:
    _write_json_atomic(APP_REGISTRY_FILE, [app.to_dict() for app in PLUGIN_REGISTRY])


def _save_scan_cache_file() -> None:
    _write_json_atomic(SCAN_CACHE_FILE, SCAN_CACHE)


# ==================================================
# Registry & cache loading
# ==================================================

def load_app_registry(force_reload: bool = False) -> list[AppConfig]:
    global PLUGIN_REGISTRY, PLUGIN_REGISTRY_BY_NAME

    with _REGISTRY_LOCK:
        if force_reload or not PLUGIN_REGISTRY:
            registry = _read_registry_file()
            PLUGIN_REGISTRY = registry
            PLUGIN_REGISTRY_BY_NAME = {app.name: app for app in registry}

    return PLUGIN_REGISTRY


def load_scan_cache(force_reload: bool = False) -> dict[str, dict[str, Any]]:
    global SCAN_CACHE

    with _CACHE_LOCK:
        if force_reload or not SCAN_CACHE:
            SCAN_CACHE = _read_scan_cache_file()

    return SCAN_CACHE


# ==================================================
# Plugin registration
# ==================================================

def register_plugin(config: dict[str, Any] | AppConfig) -> AppConfig:
    global PLUGIN_REGISTRY, PLUGIN_REGISTRY_BY_NAME

    if isinstance(config, AppConfig):
        app = config
    else:
        validate_config_dict(config)
        app = AppConfig.from_dict(config)

    print("REGISTER_PLUGIN:", json.dumps(app.to_dict(), ensure_ascii=False), flush=True)

    if app.level in (0, 5):
        print(f"[ERROR] Plugin '{app.name}' uses level {app.level}, which is reserved for the system and must not be used by plugins. Registration aborted.")
        raise ValueError(f"Level {app.level} is not allowed for plugins.")
    if app.level not in (1, 2, 3, 4):
        print(f"[ERROR] Plugin '{app.name}' uses unknown level {app.level}. Valid levels are 1-4. Registration aborted.")
        raise ValueError(f"Unknown level: {app.level}")

    load_app_registry()

    with _REGISTRY_LOCK:
        existing = PLUGIN_REGISTRY_BY_NAME.get(app.name)

        if existing is not None and existing.to_dict() == app.to_dict():
            print(f"[SKIP] Already registered: {app.name}")
            return existing

        if existing is not None:
            for idx, item in enumerate(PLUGIN_REGISTRY):
                if item.name == app.name:
                    PLUGIN_REGISTRY[idx] = app
                    break
            print(f"[UPDATE] Re-registered: {app.name}")
        else:
            PLUGIN_REGISTRY.append(app)
            print(f"[OK] Registered: {app.name}")

        PLUGIN_REGISTRY_BY_NAME[app.name] = app
        _save_registry_file()

    return app


# ==================================================
# Executable scanning & fingerprinting
# ==================================================

def find_main_executables(base_dir: Path) -> list[Path]:
    return sorted(base_dir.rglob("main.exe"))


def _fingerprint(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _parse_registration_output(output: str) -> dict[str, Any] | None:
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("REGISTER_PLUGIN:"):
            line = line[len("REGISTER_PLUGIN:") :].strip()

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            return data

    return None


def run_and_capture_registration(exe_path: Path, timeout: float = 5.0) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            [str(exe_path), "--register-only"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(exe_path.parent),
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    output = completed.stdout or ""
    data = _parse_registration_output(output)
    if data is None:
        return None

    try:
        validate_config_dict(data)
    except Exception:
        return None

    return data


def load_or_scan_executable(exe_path: Path, timeout: float = 10.0) -> tuple[Path, dict[str, Any] | None]:
    cache_key = str(exe_path.resolve())
    fingerprint = _fingerprint(exe_path)

    load_scan_cache()

    with _CACHE_LOCK:
        cached = SCAN_CACHE.get(cache_key)
        if cached and cached.get("fingerprint") == fingerprint:
            config = cached.get("config")
            if isinstance(config, dict):
                try:
                    validate_config_dict(config)
                    return exe_path, config
                except Exception:
                    pass

    data = run_and_capture_registration(exe_path, timeout=timeout)
    if data is not None:
        with _CACHE_LOCK:
            SCAN_CACHE[cache_key] = {
                "fingerprint": fingerprint,
                "config": data,
            }

    return exe_path, data


# ==================================================
# Full registry scan (entry point)
# ==================================================

def run_registry_scan() -> None:
    print(f"[INFO] Scanning: {BASE_DIR}")

    executables = find_main_executables(BASE_DIR)
    if not executables:
        print("[INFO] No executables found")
        return

    max_workers = min(4, max(1, (os.cpu_count() or 1)))
    seen_names: set[str] = set()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for exe_path, data in executor.map(load_or_scan_executable, executables):
            print(f"[INFO] Processing: {exe_path}")

            if data is None:
                print(f"[WARN] No valid response from: {exe_path}")
                continue

            app_name = data.get("name")
            if isinstance(app_name, str) and app_name in seen_names:
                print(f"[SKIP] Duplicate app in this run: {app_name}")
                continue

            try:
                register_plugin(data)
                if isinstance(app_name, str):
                    seen_names.add(app_name)
            except Exception as e:
                print(f"[ERROR] {exe_path}: {e}")

    with _CACHE_LOCK:
        _save_scan_cache_file()

    print("[INFO] Done")

if __name__ == "__main__":
    run_registry_scan()