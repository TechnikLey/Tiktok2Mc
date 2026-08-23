"""Notification dispatcher (API process).

Unified fan-out for user-facing notifications to exchangeable channels
(J.3 Nr. 13).  Channels are configured in the global ``config.yaml``::

    notifications:
      enabled: true
      channels:
        log: {}                                  # always available
        overlay: {overlay_name: default, duration: 4}
        sound: {file: data/sounds/alert.wav}     # .wav via winsound (Windows)
        tts: {}                                  # Windows SAPI via PowerShell
        discord: {webhook_url: https://discord.com/api/webhooks/...}

Built-in handlers live in :data:`CHANNEL_HANDLERS`; additional channels
can be registered there at runtime (exchangeable-channel design). TTS as
a full feature (queueing, voices, per-viewer messages) remains plugin
territory — this channel only speaks one-shot texts.

Requests may pass ``channels`` either as a list of names (global config
applies) or as a mapping ``{name: params}`` whose values are merged over
the global channel config — so plugins/hooks can stay fully self-contained
by passing their own settings (e.g. a webhook URL from their own config).

REST surface (``routes/notifications.py``):

* ``POST /api/v1/notifications``          → fan out one notification
* ``GET  /api/v1/notifications/channels`` → configured channels (masked)
* ``POST /api/v1/notifications/reload``   → re-read the config section
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.error_codes import NOTIF_0001, NOTIF_0002

from .outbound_dispatcher import mask_url  # reuse log-safe URL masking

log = logging.getLogger(__name__)

DEFAULT_TTS_TIMEOUT = 15.0
DEFAULT_HTTP_TIMEOUT = 5.0

# Channel handler signature: (title, body, level, config) -> bool
ChannelHandler = Callable[[str, str, str, dict[str, Any]], bool]


# ---------------------------------------------------------------------------
#  Built-in channel handlers (sync; executed in worker threads)
# ---------------------------------------------------------------------------


def _send_log(title: str, body: str, level: str, config: dict[str, Any]) -> bool:
    message = f"[NOTIF] {title}" + (f" — {body}" if body else "")
    log.info(message)
    return True


def _send_overlay(title: str, body: str, level: str, config: dict[str, Any]) -> bool:
    from core.overlay import send_overlay_text

    duration = int(config.get("duration", 4))
    overlay_name = str(config.get("overlay_name", "default"))
    return send_overlay_text(title, body, duration, overlay_name)


def _send_sound(title: str, body: str, level: str, config: dict[str, Any]) -> bool:
    raw = str(config.get("file", ""))
    if not raw:
        log.warning("%s: sound channel has no 'file' configured", NOTIF_0001.code)
        return False
    path = _resolve_path(raw)
    if not path.is_file():
        log.warning("%s: sound file not found: %s", NOTIF_0001.code, path)
        return False
    if platform.system() != "Windows":
        log.warning(
            "%s: sound channel requires Windows (winsound); skipped %s",
            NOTIF_0001.code,
            path.name,
        )
        return False
    try:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception as exc:  # audio device errors must never break fan-out
        log.warning("%s: sound playback failed: %s", NOTIF_0001.code, exc)
        return False


def _send_tts(title: str, body: str, level: str, config: dict[str, Any]) -> bool:
    text = " ".join(part for part in (title, body) if part)
    if platform.system() != "Windows":
        log.warning("%s: tts channel requires Windows (SAPI); skipped", NOTIF_0001.code)
        return False
    timeout = float(config.get("timeout", DEFAULT_TTS_TIMEOUT))
    rate = int(config.get("rate", 0))
    # Inject a rate setting before speaking (SAPI range -10..10).
    rate_line = f"$s.Rate = {rate}; " if rate else ""
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"{rate_line}$s.Speak([Console]::In.ReadToEnd())"
    )
    ps_args = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]
    try:
        result = subprocess.run(
            ps_args,
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            log.warning(
                "%s: tts failed (exit %s): %s",
                NOTIF_0001.code,
                result.returncode,
                result.stderr.decode(errors="replace")[:200],
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        log.warning("%s: tts timed out after %ss", NOTIF_0001.code, timeout)
        return False
    except OSError as exc:
        log.warning("%s: tts could not start: %s", NOTIF_0001.code, exc)
        return False


def _send_discord(title: str, body: str, level: str, config: dict[str, Any]) -> bool:
    url = str(config.get("webhook_url", ""))
    if not url.startswith(("http://", "https://")):
        log.warning("%s: discord channel needs a valid webhook_url", NOTIF_0001.code)
        return False
    content = f"**{title}**" + (f"\n{body}" if body else "")
    payload = {"content": content}
    timeout = float(config.get("timeout", DEFAULT_HTTP_TIMEOUT))
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError as exc:
        log.warning("%s: discord webhook failed: HTTP %s", NOTIF_0001.code, exc.code)
        return False
    except (OSError, ValueError) as exc:
        log.warning(
            "%s: discord webhook failed (%s): %s",
            NOTIF_0001.code,
            mask_url(url),
            exc,
        )
        return False


CHANNEL_HANDLERS: dict[str, ChannelHandler] = {
    "log": _send_log,
    "overlay": _send_overlay,
    "sound": _send_sound,
    "tts": _send_tts,
    "discord": _send_discord,
}


def _resolve_path(raw: str) -> Path:
    from core.paths import get_root_dir

    path = Path(raw)
    if not path.is_absolute():
        path = get_root_dir() / path
    return path


# ---------------------------------------------------------------------------
#  Config loading
# ---------------------------------------------------------------------------


def load_notification_config() -> dict[str, Any]:
    """Load the ``notifications`` section from the global config file."""
    from ruamel.yaml.error import YAMLError

    from core.paths import get_config_file
    from core.yaml_utils import load_yaml

    cfg_path = get_config_file()
    try:
        cfg = load_yaml(cfg_path) if cfg_path.exists() else {}
    except (OSError, ValueError, YAMLError) as exc:
        log.warning("Failed to load global config for notifications: %s", exc)
        return {}
    section = cfg.get("notifications", {})
    return section if isinstance(section, dict) else {}


# ---------------------------------------------------------------------------
#  Dispatcher
# ---------------------------------------------------------------------------


class NotificationDispatcher:
    """Fans out notifications to the configured channels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = True
        self._channels: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        """(Re)read the ``notifications`` config section (thread-safe)."""
        section = load_notification_config()
        raw_channels = section.get("channels", {})
        channels: dict[str, dict[str, Any]] = (
            {str(k): v for k, v in raw_channels.items()}
            if isinstance(raw_channels, dict)
            else {}
        )
        with self._lock:
            self._enabled = bool(section.get("enabled", True))
            self._channels = channels
        log.info(
            "[NOTIF] Loaded %d notification channel(s): %s",
            len(channels),
            ", ".join(sorted(channels)) or "<none>",
        )

    def _snapshot(self) -> tuple[bool, dict[str, dict[str, Any]]]:
        with self._lock:
            return self._enabled, dict(self._channels)

    def status(self) -> dict[str, Any]:
        enabled, channels = self._snapshot()
        return {
            "enabled": enabled,
            "built_in": sorted(CHANNEL_HANDLERS),
            "configured": {name: sorted(cfg.keys()) for name, cfg in channels.items()},
        }

    def resolve_channels(
        self, requested: list[str] | None
    ) -> tuple[list[str], list[str]]:
        """Return ``(deliverable, skipped)`` channel names for a request.

        Unknown names (neither built-in nor configured) are warned as
        NOTIF-0002; configured names without a registered handler are
        skipped with an info log (custom channels may register later).
        """
        enabled, configured = self._snapshot()
        if not enabled:
            return [], list(requested or configured or ["log"])
        names = list(requested) if requested else (list(configured) or ["log"])
        deliverable: list[str] = []
        skipped: list[str] = []
        for name in names:
            if name in CHANNEL_HANDLERS:
                deliverable.append(name)
            elif name not in configured:
                log.warning(
                    "%s: unknown notification channel '%s' (built-in: %s)",
                    NOTIF_0002.code,
                    name,
                    ", ".join(sorted(CHANNEL_HANDLERS)),
                )
                skipped.append(name)
            else:
                log.info("[NOTIF] channel '%s' has no handler registered", name)
                skipped.append(name)
        return deliverable, skipped

    @staticmethod
    def _normalize_channels(
        channels: list[str] | dict[str, dict[str, Any]] | None,
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        """Split a request's ``channels`` value into names + inline params.

        ``["overlay", "discord"]``      → names only, global config applies
        ``{"discord": {...}}``          → names + inline params per channel
        """
        if channels is None:
            return [], {}
        if isinstance(channels, dict):
            return [str(name) for name in channels], {
                str(name): (params if isinstance(params, dict) else {})
                for name, params in channels.items()
            }
        return [str(name) for name in channels], {}

    async def notify(
        self,
        title: str,
        body: str = "",
        level: str = "info",
        channels: list[str] | dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, list[str]]:
        """Fan out one notification. Returns per-outcome channel lists.

        Inline params (``channels`` as mapping) are merged over the global
        channel config — inline wins — so callers can stay self-contained
        without touching the global config.
        """
        _, configured = self._snapshot()
        names, inline = self._normalize_channels(channels)
        targets, skipped = self.resolve_channels(names or None)

        async def _deliver(name: str) -> tuple[str, bool]:
            handler = CHANNEL_HANDLERS[name]
            cfg = {**configured.get(name, {}), **inline.get(name, {})}
            try:
                ok = await asyncio.to_thread(handler, title, body, level, cfg)
            except Exception as exc:  # one broken channel must not kill fan-out
                log.warning("%s: channel '%s' raised: %s", NOTIF_0001.code, name, exc)
                ok = False
            return name, ok

        results = await asyncio.gather(*(_deliver(n) for n in targets))
        sent = [name for name, ok in results if ok]
        failed = [name for name, ok in results if not ok]
        if failed:
            log.warning(
                "[NOTIF] '%s' delivery failed on channel(s): %s",
                title,
                ", ".join(failed),
            )
        return {"sent": sent, "failed": failed, "skipped": skipped}


# Module-level singleton
_dispatcher: NotificationDispatcher | None = None


def get_notification_dispatcher() -> NotificationDispatcher:
    """Return the global ``NotificationDispatcher`` singleton."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = NotificationDispatcher()
    return _dispatcher
