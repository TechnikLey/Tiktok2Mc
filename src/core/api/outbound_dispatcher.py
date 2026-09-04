"""Outbound webhook dispatcher (API process).

Forwards EventBus events to user-configured HTTP endpoints ("outbound
channels", e.g. Discord webhooks).  Channels are declared in the global
``config.yaml`` under ``outbound.channels`` and subscribe via event
patterns (``tiktok.gift``, ``tiktok.*``) using the same matching rules as
the plugin event bridge.

Delivery contracts:

* ``format: raw``     → JSON envelope ``{"type", "data", "timestamp"}``.
* ``format: discord`` → JSON ``{"content": "<filled template>"}`` where
  the template supports ``{user}``, ``{type}`` and any event data key
  (``{comment}``, ``{gift_id}``, ...).  Missing keys become empty strings.
  The payload shape matches the Discord webhook API.

Each channel has its own circuit breaker (shared implementation with the
overlay subsystem): after ``max_fails`` consecutive failed deliveries the
channel enters a cooldown during which events are dropped instead of sent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from core.error_codes import (
    OUTBOUND_0001,
    OUTBOUND_0002,
    OUTBOUND_0003,
    OUTBOUND_0004,
)
from core.event_patterns import match_event
from core.health_monitor import HealthState, get_health_monitor
from core.overlay_base import OverlayClient

log = logging.getLogger(__name__)

RETRY_DELAY = 1.0
DEFAULT_TIMEOUT = 5.0
VALID_FORMATS = ("raw", "discord")
STOP_GRACE = 2.0


class _SafeFormatDict(dict[str, Any]):
    """``str.format_map`` helper: unknown placeholders become ``""``."""

    def __missing__(self, key: str) -> str:
        return ""


def format_discord_message(template: str, event_type: str, data: dict[str, Any]) -> str:
    """Fill *template* with ``user``/``type`` and all event data keys."""
    fields: dict[str, Any] = {"user": "", "type": event_type}
    for key, value in data.items():
        if isinstance(value, str):
            fields[key] = value
        else:
            try:
                fields[key] = json.dumps(value)
            except (TypeError, ValueError):
                fields[key] = ""
    return template.format_map(_SafeFormatDict(fields))


def mask_url(url: str) -> str:
    """Return a log-safe version of *url* (scheme + host only)."""
    try:
        parts = urlsplit(url)
        if not parts.netloc:
            return "<invalid-url>"
        return f"{parts.scheme or 'http'}://{parts.netloc}/<masked>"
    except ValueError:
        return "<invalid-url>"


# ---------------------------------------------------------------------------
#  Channel model + config loading
# ---------------------------------------------------------------------------


@dataclass
class OutboundChannel:
    """One configured outbound endpoint with breaker and counters."""

    name: str
    url: str
    events: list[str]
    fmt: str = "raw"
    template: str = ""
    enabled: bool = True
    retries: int = 1
    timeout: float = DEFAULT_TIMEOUT
    breaker: OverlayClient | None = None
    sent_count: int = 0
    failed_count: int = 0
    dropped_count: int = 0
    last_breaker_remaining: int = 0

    def matches(self, event_type: str) -> bool:
        """Whether *event_type* matches any of this channel's patterns.

        ``*`` matches every event; otherwise the plugin-bridge rules apply
        (exact names and trailing wildcards like ``tiktok.*``).
        """
        return any(p == "*" or match_event(event_type, p) for p in self.events)

    def build_payload(
        self, event_type: str, data: dict[str, Any], timestamp: float
    ) -> bytes:
        """Serialize the event according to this channel's format."""
        if self.fmt == "discord":
            body = {
                "content": format_discord_message(
                    self.template or "{user} {type}", event_type, data
                )
            }
        else:
            body = {
                "type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        return json.dumps(body).encode()

    def status(self) -> dict[str, Any]:
        open_, remaining = (
            self.breaker.get_cooldown_status() if self.breaker else (False, 0)
        )
        return {
            "name": self.name,
            "url": mask_url(self.url),
            "format": self.fmt,
            "events": list(self.events),
            "enabled": self.enabled,
            "breaker_open": open_,
            "cooldown_remaining": remaining,
            "retries": self.retries,
            "sent": self.sent_count,
            "failed": self.failed_count,
            "dropped": self.dropped_count,
        }


def _parse_channel(entry: Any, defaults: dict[str, Any]) -> OutboundChannel | None:
    """Build an :class:`OutboundChannel` from one config entry or ``None``."""
    if not isinstance(entry, dict):
        return None
    name = str(entry.get("name") or "")
    url = str(entry.get("url") or "")
    enabled = bool(entry.get("enabled", True))
    if not name:
        return None
    if enabled and not url.startswith(("http://", "https://")):
        return None
    events_raw = entry.get("events", ["*"])
    if not isinstance(events_raw, list):
        events_raw = ["*"]
    events = [str(p) for p in events_raw if str(p)]
    if not events:
        events = ["*"]
    fmt = str(entry.get("format", "raw")).lower()
    if fmt not in VALID_FORMATS:
        fmt = "raw"
    retries = max(0, int(entry.get("retries", defaults.get("retries", 1))))
    timeout = max(
        1.0, float(entry.get("timeout", defaults.get("timeout", DEFAULT_TIMEOUT)))
    )
    max_fails = int(defaults.get("max_fails", 3))
    cooldown = int(defaults.get("cooldown", 10))
    return OutboundChannel(
        name=name,
        url=url,
        events=events,
        fmt=fmt,
        template=str(entry.get("template", "")),
        enabled=enabled,
        retries=retries,
        timeout=timeout,
        breaker=OverlayClient(name=name, max_fails=max_fails, cooldown=cooldown),
    )


def load_outbound_channels(config: dict[str, Any]) -> dict[str, OutboundChannel]:
    """Parse the ``outbound`` config section into channels by name.

    Invalid entries are skipped with a warning; duplicate names keep the
    first occurrence.
    """
    section = config.get("outbound")
    if not isinstance(section, dict):
        return {}
    if not section.get("enabled", True):
        return {}

    channels: dict[str, OutboundChannel] = {}
    raw_channels = section.get("channels", [])
    if not isinstance(raw_channels, list):
        return {}
    defaults = {
        "retries": section.get("retries", 1),
        "timeout": section.get("timeout", DEFAULT_TIMEOUT),
        "max_fails": section.get("max_fails", 3),
        "cooldown": section.get("cooldown", 10),
    }
    for entry in raw_channels:
        channel = _parse_channel(entry, defaults)
        if channel is None:
            log.warning(
                "%s: skipping invalid outbound channel entry",
                OUTBOUND_0001.code,
            )
            continue
        if channel.name in channels:
            log.warning(
                "%s: duplicate outbound channel name '%s' — keeping first",
                OUTBOUND_0001.code,
                channel.name,
            )
            continue
        channels[channel.name] = channel
    return channels


def load_outbound_config() -> dict[str, Any]:
    """Load the ``outbound`` section from the global config file."""
    from ruamel.yaml.error import YAMLError

    from core.paths import get_config_file
    from core.yaml_utils import load_yaml

    cfg_path = get_config_file()
    try:
        cfg = load_yaml(cfg_path) if cfg_path.exists() else {}
    except (OSError, ValueError, YAMLError) as exc:
        log.warning("Failed to load global config for outbound: %s", exc)
        return {}
    section = cfg.get("outbound", {})
    return section if isinstance(section, dict) else {}


# ---------------------------------------------------------------------------
#  Dispatcher
# ---------------------------------------------------------------------------


class OutboundDispatcher:
    """Background task that forwards bus events to outbound channels."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._lock = threading.Lock()
        self._channels: dict[str, OutboundChannel] = {}
        self._master_enabled = True
        self._inflight: set[asyncio.Task[None]] = set()
        self._health = get_health_monitor()
        # Construction is the "starting" phase; start() flips to RUNNING.
        self._health.register("outbound_dispatcher", HealthState.STARTING)

    # ------------------------------------------------------------------
    #  Channels
    # ------------------------------------------------------------------

    def refresh_channels(self) -> None:
        """(Re)load channel configuration from the global config."""
        section = load_outbound_config()
        channels = load_outbound_channels({"outbound": section})
        with self._lock:
            self._channels = channels
            self._master_enabled = bool(section.get("enabled", True))
        log.info("[OUTBOUND] Loaded %d outbound channel(s)", len(channels))

    def _snapshot(self) -> tuple[bool, dict[str, OutboundChannel]]:
        with self._lock:
            return self._master_enabled, dict(self._channels)

    # ------------------------------------------------------------------
    #  Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """Fan out one bus event to all matching channels (no awaits)."""
        enabled, channels = self._snapshot()
        if not enabled or not channels:
            return
        event_type = str(msg.get("type", ""))
        if not event_type:
            return
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {"value": data}
        timestamp = float(msg.get("timestamp") or time.time())

        for channel in channels.values():
            if not channel.enabled or not channel.matches(event_type):
                continue
            blocked, remaining = (
                channel.breaker.get_cooldown_status() if channel.breaker else (False, 0)
            )
            if blocked:
                channel.dropped_count += 1
                if remaining > channel.last_breaker_remaining:
                    log.warning(
                        "%s: channel '%s' circuit breaker active — "
                        "dropping events for %ss",
                        OUTBOUND_0003.code,
                        channel.name,
                        remaining,
                    )
                channel.last_breaker_remaining = remaining
                log.debug(
                    "[OUTBOUND] %s dropped (%s): circuit breaker open (%ss)",
                    event_type,
                    channel.name,
                    remaining,
                )
                continue
            payload = channel.build_payload(event_type, data, timestamp)
            task = asyncio.create_task(self._deliver(channel, payload))
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)

    async def _deliver(self, channel: OutboundChannel, payload: bytes) -> None:
        """Deliver one payload with retries and breaker bookkeeping."""
        attempts = channel.retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(RETRY_DELAY)
            try:
                await asyncio.to_thread(
                    self._post, channel.url, payload, channel.timeout
                )
                if channel.breaker:
                    channel.breaker.mark_success()
                channel.sent_count += 1
                return
            except Exception as exc:
                last_error = exc
                log.debug(
                    "[OUTBOUND] %s → %s attempt %d/%d failed: %s",
                    channel.name,
                    mask_url(channel.url),
                    attempt + 1,
                    attempts,
                    exc,
                )
        if channel.breaker:
            channel.breaker.mark_failure()
        channel.failed_count += 1
        log.warning(
            "%s: delivery to '%s' (%s) failed after %d attempt(s): %s",
            OUTBOUND_0002.code,
            channel.name,
            mask_url(channel.url),
            attempts,
            last_error,
        )

    @staticmethod
    def _post(url: str, body: bytes, timeout: float) -> int:
        """POST *body* to *url*.  Returns the HTTP status on 2xx, raises otherwise."""
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if not 200 <= status < 300:
                raise RuntimeError(f"unexpected status {status}")
            return int(status)

    # ------------------------------------------------------------------
    #  Background loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        from core.api.eventbus import event_bus

        q = event_bus.subscribe()  # all events; filtered per channel
        log.info("[OUTBOUND] OutboundDispatcher started")
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    self._dispatch(msg)
                except Exception as exc:  # worker must never die
                    log.error("[OUTBOUND] Dispatch failed: %s", exc)
                    try:
                        self._health.record_error(
                            "outbound_dispatcher", f"Dispatch failed: {exc}"
                        )
                        self._health.set_state(
                            "outbound_dispatcher", HealthState.DEGRADED
                        )
                    except Exception:  # best-effort health reporting
                        pass
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(q)
            log.info("[OUTBOUND] OutboundDispatcher stopped")

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    async def send_test(self, name: str) -> tuple[bool, str]:
        """Send a synthetic test message through one channel.

        Bypasses event patterns and does **not** touch the circuit breaker
        or counters — it is a pure connectivity probe.

        Raises ``LookupError`` when the channel is unknown.
        """
        _, channels = self._snapshot()
        channel = channels.get(name)
        if channel is None:
            raise LookupError(name)
        if not channel.enabled:
            return False, f"channel '{name}' is disabled"
        payload = channel.build_payload(
            "outbound.test",
            {"user": "TestUser"},
            time.time(),
        )
        try:
            status = await asyncio.to_thread(
                self._post, channel.url, payload, channel.timeout
            )
            return True, f"delivered (HTTP {status})"
        except Exception as exc:
            log.warning(
                "%s: test dispatch to '%s' failed: %s", OUTBOUND_0004.code, name, exc
            )
            return False, f"delivery failed: {exc}"

    def status(self) -> dict[str, Any]:
        """Return channel states for the GUI/API (URLs masked)."""
        enabled, channels = self._snapshot()
        return {
            "enabled": enabled,
            "channels": [c.status() for c in channels.values()],
        }

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self.refresh_channels()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._health.set_state("outbound_dispatcher", HealthState.RUNNING)

    async def stop(self) -> None:
        was_running = self._running
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # Deliveries already running in worker threads cannot be interrupted;
        # give them a short grace period before cancelling stragglers.
        inflight = list(self._inflight)
        if inflight:
            if was_running:
                self._health.set_state("outbound_dispatcher", HealthState.STOPPING)
            _, pending = await asyncio.wait(inflight, timeout=STOP_GRACE)
            for task in pending:
                task.cancel()
            self._inflight.clear()
        if was_running:
            self._health.set_state("outbound_dispatcher", HealthState.STOPPED)


# Module-level singleton
_dispatcher: OutboundDispatcher | None = None


def get_outbound_dispatcher() -> OutboundDispatcher:
    """Return the global :class:`OutboundDispatcher` singleton."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = OutboundDispatcher()
    return _dispatcher
