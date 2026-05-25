#!/usr/bin/env python3
import time
import threading
import requests
import yaml
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

class OverlayClient:
    def __init__(self, name, global_port, max_fails, cooldown):
        self.name = name
        self.url = f"http://127.0.0.1:{global_port}/display/{name}"
        self.max_fails = max_fails
        self.cooldown = cooldown
        self._fail_count = 0
        self._last_fail_time = 0

    def get_cooldown_status(self):
        if self._fail_count >= self.max_fails:
            elapsed = time.time() - self._last_fail_time
            if elapsed < self.cooldown:
                return True, int(self.cooldown - elapsed)
            self._fail_count = 0 
        return False, 0

    def mark_success(self):
        self._fail_count = 0

    def mark_failure(self):
        self._fail_count += 1
        self._last_fail_time = time.time()

class OverlayManager:
    def __init__(self):
        self.clients = {}
        self.config_path = get_base_dir().parent / "config" / "config.yaml"
        self.load_config()

    def load_config(self):
        if not self.config_path.exists():
            log.critical(f"Config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                full_config = yaml.safe_load(f) or {}
                conf = full_config.get("overlay_text", {})
        except Exception as e:
            log.error(f"YAML Error: {e}")
            return

        global_port = conf.get("port", 29186)
        def_fails = conf.get("max_fails", 3)
        def_cooldown = conf.get("cooldown", 10)

        # Overlays aus dem Unterpunkt laden
        for item in conf.get("overlays", []):
            name = item.get("name")
            if not name:
                log.warning(f"Skipping overlay with missing name: {item}")
                continue
            self.clients[name] = OverlayClient(
                name=name,
                global_port=global_port,
                max_fails=def_fails,
                cooldown=def_cooldown
            )

        # Immer ein "default" Overlay bereitstellen, auch wenn es nicht in der Config steht
        if "default" not in self.clients:
            self.clients["default"] = OverlayClient(
                name="default",
                global_port=global_port,
                max_fails=def_fails,
                cooldown=def_cooldown
            )
            log.info(f"Created fallback 'default' overlay (not in config).")

        log.info(f"Loaded {len(self.clients)} overlays from {self.config_path}")

    def dispatch(self, title, subtitle, duration, target_name):
        client = self.clients.get(target_name)
        if not client:
            log.error(f"Overlay '{target_name}' not found.")
            return False

        blocked, remaining = client.get_cooldown_status()
        if blocked:
            log.warning(f"[{client.name}] Circuit breaker active ({remaining}s).")
            return False

        try:
            r = requests.post(client.url, json={"title": title, "subtitle": subtitle, "duration": duration}, timeout=2)
            if r.status_code == 200:
                client.mark_success()
                return True
            client.mark_failure()
        except Exception as e:
            log.error(f"[OVERLAY] POST to {client.url} failed: {e}")
            client.mark_failure()
        return False

_manager = None
_manager_lock = threading.Lock()

def send_overlay_text(title, subtitle, duration=3, overlay_name="default"):
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = OverlayManager()
    return _manager.dispatch(title, subtitle, duration, overlay_name)