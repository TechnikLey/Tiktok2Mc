"""Trigger execution service for the Event Tester GUI.

Encapsulates all trigger-sending logic.  The service can operate in two
modes:

1. **HTTP mode** (preferred) – POSTs directly to the bridge's
   ``/custom_trigger`` and ``/test_comment`` endpoints.  This guarantees
   that test events follow the exact same code path as real events.

2. **Executable mode** (fallback) – discovers ``text_trigger.exe`` (or the
   platform equivalent) and invokes it as a subprocess.  This satisfies the
   requirement to interface with the existing external tool.

In both cases the service maintains an in-memory session history and
enforces a short cooldown to prevent accidental double-clicks.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.paths import get_base_dir, get_root_dir
from core.yaml_utils import load_yaml

log = logging.getLogger(__name__)


@dataclass
class TriggerRecord:
    """A single entry in the trigger session history."""

    timestamp: float
    kind: str  # "trigger" or "comment"
    payload: dict[str, Any]
    status: str  # "running", "success", "error"
    message: str = ""


class TriggerService:
    """Central business logic for the Event Tester."""

    # Cooldown between trigger executions (seconds)
    DEBOUNCE_SECONDS = 1.5

    # Predefined trigger types known to be valid in most configs
    # Note: "tiktok" is intentionally excluded — it is a system control,
    # not an event category, and has its own dedicated API endpoint.
    DEFAULT_EVENT_TYPES = [
        "follow",
        "like",
        "join",
        "share",
        "comment",
        "gift",
    ]

    def __init__(self) -> None:
        self._history: list[TriggerRecord] = []
        self._last_execution: float = 0.0
        self._webhook_port: int | None = None
        self._server_host: str = "127.0.0.1"
        self._executable_path: Path | None = None
        self._discover_executable()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_executable(self) -> None:
        """Locate ``text_trigger.exe`` / ``test_trigger.exe`` / ``send_trigger.py``."""
        root = get_root_dir()
        base = get_base_dir()
        is_windows = sys.platform == "win32"
        suffix = ".exe" if is_windows else ".bin"

        candidates: list[Path] = [
            root / f"text_trigger{suffix}",
            root / f"test_trigger{suffix}",
            base.parent / "test" / f"test_trigger{suffix}",
            root / "tests" / "send_trigger.py",
            root / "test" / f"test_trigger{suffix}",
        ]

        for cand in candidates:
            if cand.exists():
                self._executable_path = cand.resolve()
                log.info("Trigger executable discovered: %s", self._executable_path)
                return

        log.debug("No trigger executable found; falling back to HTTP mode.")

    def _resolve_webhook_port(self) -> int:
        """Read the bridge webhook port from config (cached)."""
        if self._webhook_port is not None:
            return self._webhook_port

        port = 29188  # default
        try:
            cfg_path = get_root_dir() / "config" / "config.yaml"
            if not cfg_path.exists():
                cfg_path = get_root_dir() / "defaults" / "config.yaml"
            if cfg_path.exists():
                cfg = load_yaml(cfg_path)
                port = int(
                    cfg.get("minecraft_server_api", {}).get("web_server_port", 29188)
                )
                self._server_host = cfg.get("server_host", "127.0.0.1")
        except Exception as exc:
            log.warning("Could not read webhook port from config: %s", exc)

        self._webhook_port = port
        return port

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_event_types(self) -> list[str]:
        """Return the list of predefined event types available for testing."""
        return list(self.DEFAULT_EVENT_TYPES)

    def get_history(self) -> list[dict[str, Any]]:
        """Return the session trigger history (newest first)."""
        return [
            {
                "timestamp": r.timestamp,
                "kind": r.kind,
                "payload": r.payload,
                "status": r.status,
                "message": r.message,
            }
            for r in reversed(self._history)
        ]

    def can_execute(self) -> tuple[bool, str]:
        """Check whether execution is allowed (debounce)."""
        now = time.time()
        elapsed = now - self._last_execution
        if elapsed < self.DEBOUNCE_SECONDS:
            remaining = round(self.DEBOUNCE_SECONDS - elapsed, 1)
            return False, f"Please wait {remaining}s before triggering again."
        return True, ""

    def execute_trigger(
        self, trigger: str, user: str = "System", gift_id: str | None = None
    ) -> dict[str, Any]:
        """Send a trigger event.

        When *gift_id* is provided the trigger value is set to the gift ID
        so that the bridge can match it against ``ctx.valid_functions``.
        """
        ok, msg = self.can_execute()
        if not ok:
            return {"status": "error", "message": msg}

        self._last_execution = time.time()
        # If a gift_id is given, use it as the trigger value so the bridge
        # resolves it against valid_functions by ID (and falls back to name).
        trigger_value = gift_id if gift_id is not None else trigger
        payload = {"trigger": trigger_value, "user": user}
        record = TriggerRecord(
            timestamp=self._last_execution,
            kind="trigger",
            payload=payload,
            status="running",
        )
        self._history.append(record)

        result = self._dispatch(payload, mode="trigger")
        record.status = result.get("status", "error")
        record.message = result.get("message", "")
        return result

    def toggle_tiktok_connection(self) -> dict[str, Any]:
        """Toggle the TikTok live-stream connection on/off.

        This is a system control operation, not an event simulation.
        It calls the same bridge endpoint used by the external trigger tool
        but is exposed as a dedicated API so the GUI can separate connection
        state from event testing.
        """
        ok, msg = self.can_execute()
        if not ok:
            return {"status": "error", "message": msg}

        self._last_execution = time.time()
        payload = {"trigger": "tiktok", "user": "System"}
        record = TriggerRecord(
            timestamp=self._last_execution,
            kind="system",
            payload=payload,
            status="running",
        )
        self._history.append(record)

        result = self._dispatch(payload, mode="trigger")
        record.status = result.get("status", "error")
        record.message = result.get("message", "")

        # The bridge returns a message like "TikTok connection toggled. Now DISABLE_TIKTOK_CONNECT=True"
        # Parse the boolean out so the GUI can show an ON/OFF state.
        connected = True
        message = result.get("message", "")
        if "DISABLE_TIKTOK_CONNECT=True" in message:
            connected = False
        elif "DISABLE_TIKTOK_CONNECT=False" in message:
            connected = True
        elif "disabled" in message.lower() or "now true" in message.lower():
            connected = False

        return {
            "status": result.get("status", "error"),
            "message": message,
            "connected": connected,
        }

    def send_comment(
        self,
        user: str,
        text: str,
        moderator: bool = False,
        superfan: bool = False,
        fanclub: bool = False,
    ) -> dict[str, Any]:
        """Send a test comment event."""
        ok, msg = self.can_execute()
        if not ok:
            return {"status": "error", "message": msg}

        self._last_execution = time.time()
        payload = {
            "user": user,
            "text": text,
            "moderator": moderator,
            "superfan": superfan,
            "fanclub": fanclub,
        }
        record = TriggerRecord(
            timestamp=self._last_execution,
            kind="comment",
            payload=payload,
            status="running",
        )
        self._history.append(record)

        result = self._dispatch(payload, mode="comment")
        record.status = result.get("status", "error")
        record.message = result.get("message", "")
        return result

    # ------------------------------------------------------------------
    # Dispatch internals
    # ------------------------------------------------------------------

    def _dispatch(self, payload: dict[str, Any], mode: str) -> dict[str, Any]:
        """Try executable first, then fall back to HTTP."""
        if self._executable_path is not None:
            try:
                return self._dispatch_via_executable(payload, mode)
            except Exception as exc:
                log.warning("Executable dispatch failed (%s), trying HTTP: %s", mode, exc)

        return self._dispatch_via_http(payload, mode)

    def _dispatch_via_http(self, payload: dict[str, Any], mode: str) -> dict[str, Any]:
        """POST directly to the bridge webhook endpoints."""
        host = self._server_host
        port = self._resolve_webhook_port()

        if mode == "trigger":
            url = f"http://{host}:{port}/custom_trigger"
        else:
            url = f"http://{host}:{port}/test_comment"

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                data.setdefault("status", "ok")
                return data
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                return {
                    "status": "error",
                    "message": detail.get("message", f"HTTP {exc.code}"),
                }
            except Exception:
                return {"status": "error", "message": f"HTTP {exc.code}: {exc.reason}"}
        except urllib.error.URLError as exc:
            msg = (
                f"Cannot reach bridge at {url}. "
                f"The TikTok bridge (main.py) may not be running yet. "
                f"Error: {exc.reason}"
            )
            return {"status": "error", "message": msg}
        except ConnectionResetError as exc:
            return {
                "status": "error",
                "message": (
                    f"Bridge at {url} refused the connection. "
                    f"The TikTok bridge may still be starting up or is not running."
                ),
            }
        except Exception as exc:
            log.exception("HTTP dispatch failed")
            return {"status": "error", "message": str(exc)}

    def _dispatch_via_executable(
        self, payload: dict[str, Any], mode: str
    ) -> dict[str, Any]:
        """Run the external trigger tool as a subprocess.

        The executable is invoked with a single JSON argument so that it can
        be replaced by any CLI-compatible binary without changing this code.
        """
        if self._executable_path is None:
            raise RuntimeError("No executable available")

        # Build a CLI-friendly representation of the payload.
        # We pass the mode and every payload key as --key value.
        args = [str(self._executable_path), f"--mode={mode}"]
        for key, value in payload.items():
            if isinstance(value, bool):
                args.append(f"--{key}" if value else f"--no-{key}")
            else:
                args.append(f"--{key}={value}")

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            if proc.returncode != 0:
                stderr = proc.stderr.strip() or "unknown error"
                return {
                    "status": "error",
                    "message": f"Trigger executable exited with code {proc.returncode}: {stderr}",
                }

            # Try to parse JSON stdout; fall back to plain text.
            stdout = proc.stdout.strip()
            if stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    return {"status": "ok", "message": stdout}
            return {"status": "ok", "message": "Triggered via external tool."}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Trigger executable timed out."}
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc


# Singleton instance used by the API route layer.
_trigger_service: TriggerService | None = None


def get_trigger_service() -> TriggerService:
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = TriggerService()
    return _trigger_service
