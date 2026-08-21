"""TikTok chatbot — sends messages to the connected TikTok live room.

The bot is a first-party core module (see docs/CHATBOT.md §6).  It

* reads its own config file (``config/chatbot.yaml``),
* subscribes to ``tiktok.gift`` / ``tiktok.follow`` / ``tiktok.join`` /
  ``tiktok.comment`` events on the in-process :data:`event_bus`,
* applies spam protection (min interval, per-minute window, queue cap,
  duplicate suppression, length cap), and
* sends the rendered template via the bound :class:`TikTokLiveClient`.

The client runs on its own dedicated event loop thread (see
``main.run_bot``); all sends are scheduled onto that loop with
``run_coroutine_threadsafe`` so the httpx session stays loop-consistent.

Config changes are applied at runtime: the API writes the YAML file and
drops a reload signal; the bridge's signal watcher calls
:meth:`TikTokChatbot.reload_config`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import core.paths
from core.api.eventbus import event_bus
from core.crash_manager import get_crash_manager
from core.error_codes import CHATBOT_0001, CHATBOT_0002, CHATBOT_0003, CHATBOT_0004
from core.yaml_utils import load_yaml

# Note: no module-level ``initialize_logging`` here on purpose — this module
# is imported by tests and API tooling where a full logging init (queue
# listener thread + file handler) must not be triggered as an import side
# effect.  The bridge process initializes logging globally before use.
log = logging.getLogger(__name__)

DEFAULT_MIN_INTERVAL_S = 5.0
DEFAULT_MAX_PER_MINUTE = 10
DEFAULT_MAX_QUEUE = 20
DEFAULT_MAX_LEN = 150
AUTH_FAILURE_LIMIT = 3


@dataclass
class ChatbotConfig:
    """Typed view of ``config/chatbot.yaml`` with safe defaults."""

    enabled: bool = False
    min_interval_s: float = DEFAULT_MIN_INTERVAL_S
    max_per_minute: int = DEFAULT_MAX_PER_MINUTE
    max_queue: int = DEFAULT_MAX_QUEUE
    dedupe_identical: bool = True
    max_len: int = DEFAULT_MAX_LEN
    on_gift: bool = True
    on_follow: bool = True
    on_join: bool = False
    gift_thanks: str = "Danke {user} für {gift}! 💖"
    follow_thanks: str = "Danke fürs Folgen, {user}!"
    join_welcome: str = ""
    keyword_replies: dict[str, str] = field(default_factory=dict)
    tt_target_idc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "spam_protection": {
                "min_interval_s": self.min_interval_s,
                "max_per_minute": self.max_per_minute,
                "max_queue": self.max_queue,
                "dedupe_identical": self.dedupe_identical,
                "max_len": self.max_len,
            },
            "triggers": {
                "gift": self.on_gift,
                "follow": self.on_follow,
                "join": self.on_join,
            },
            "templates": {
                "gift_thanks": self.gift_thanks,
                "follow_thanks": self.follow_thanks,
                "join_welcome": self.join_welcome,
            },
            "keyword_replies": dict(self.keyword_replies),
            "session": {"tt_target_idc": self.tt_target_idc},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChatbotConfig:
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        cfg.enabled = bool(data.get("enabled", cfg.enabled))

        spam = data.get("spam_protection")
        if isinstance(spam, dict):
            try:
                cfg.min_interval_s = max(
                    0.0, float(spam.get("min_interval_s", cfg.min_interval_s))
                )
            except (TypeError, ValueError):
                pass
            try:
                cfg.max_per_minute = max(
                    1, int(spam.get("max_per_minute", cfg.max_per_minute))
                )
            except (TypeError, ValueError):
                pass
            try:
                cfg.max_queue = max(1, int(spam.get("max_queue", cfg.max_queue)))
            except (TypeError, ValueError):
                pass
            cfg.dedupe_identical = bool(
                spam.get("dedupe_identical", cfg.dedupe_identical)
            )
            try:
                cfg.max_len = max(1, int(spam.get("max_len", cfg.max_len)))
            except (TypeError, ValueError):
                pass

        triggers = data.get("triggers")
        if isinstance(triggers, dict):
            cfg.on_gift = bool(triggers.get("gift", cfg.on_gift))
            cfg.on_follow = bool(triggers.get("follow", cfg.on_follow))
            cfg.on_join = bool(triggers.get("join", cfg.on_join))

        templates = data.get("templates")
        if isinstance(templates, dict):
            cfg.gift_thanks = str(templates.get("gift_thanks", cfg.gift_thanks))
            cfg.follow_thanks = str(templates.get("follow_thanks", cfg.follow_thanks))
            cfg.join_welcome = str(templates.get("join_welcome", cfg.join_welcome))

        keywords = data.get("keyword_replies")
        if isinstance(keywords, dict):
            cfg.keyword_replies = {
                str(k).strip().lower(): str(v)
                for k, v in keywords.items()
                if str(k).strip() and str(v).strip()
            }

        session = data.get("session")
        if isinstance(session, dict):
            cfg.tt_target_idc = str(session.get("tt_target_idc", cfg.tt_target_idc))
        return cfg


class TikTokChatbot:
    """Event-driven chat sender with spam protection.

    Lifecycle (wired in ``main.run_bot``)::

        bot = get_chatbot()
        await bot.start()               # starts worker + event subscription
        bot.bind_client(client, loop)   # after each successful connect
        ...
        bot.unbind_client()             # when the client loop closes
        await bot.stop()                # shutdown
    """

    def __init__(
        self,
        config_path: Path | None = None,
        status_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._config_path = config_path or core.paths.get_chatbot_config_file()
        self._status_sink = status_sink
        self.config = ChatbotConfig()
        self.load_config()

        self._client: Any = None
        self._client_loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[str] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._sub_queue: asyncio.Queue | None = None

        self._last_sent: float = 0.0
        self._window: deque[float] = deque()
        self._last_text: str = ""
        self._consecutive_failures: int = 0
        self._auto_disabled: bool = False

        self.has_session: bool = False

        self.sent_count: int = 0
        self.dropped_count: int = 0
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_config(self) -> ChatbotConfig:
        """(Re-)read ``config/chatbot.yaml``, falling back to defaults."""
        try:
            data = load_yaml(self._config_path)
            self.config = ChatbotConfig.from_dict(data if data else {})
            log.info("[CHATBOT] Config loaded from %s", self._config_path)
        except FileNotFoundError:
            self.config = ChatbotConfig()
            log.info("[CHATBOT] No config file yet — using defaults")
        except Exception as e:  # invalid YAML must not kill the bridge
            self.config = ChatbotConfig()
            get_crash_manager().report_error(
                CHATBOT_0002, detail=f"{type(e).__name__}: {e}"
            )
        return self.config

    def reload_config(self) -> None:
        """Apply config changes at runtime (called by the signal watcher)."""
        was_enabled = self.config.enabled
        self.load_config()
        if self.config.enabled and self._auto_disabled:
            # A user re-enable clears a previous auto-disable.
            self._auto_disabled = False
            self._consecutive_failures = 0
        if was_enabled != self.config.enabled:
            self.publish_status()

    # ------------------------------------------------------------------
    # Client binding
    # ------------------------------------------------------------------

    def bind_client(self, client: Any, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the live TikTok client and the loop it runs on."""
        self._client = client
        self._client_loop = loop
        self._consecutive_failures = 0
        self.publish_status()

    def unbind_client(self) -> None:
        """Clear the binding when the client loop closes."""
        self._client = None
        self._client_loop = None
        self.publish_status()

    # ------------------------------------------------------------------
    # Session (Phase 4, docs/CHATBOT.md §4)
    # ------------------------------------------------------------------

    def apply_session_to_client(self, client: Any) -> bool:
        """Apply stored TikTok login credentials to *client* (best-effort).

        Reads the encrypted session store and calls
        ``client.web.set_session(session_id, tt_target_idc)`` before the
        client connects.  Returns True when credentials were applied.
        Failures never block the read-only connection path.
        """
        from core.chatbot_session import load_chatbot_session

        creds: tuple[str, str] | None = None
        try:
            creds = load_chatbot_session()
        except Exception as e:  # storage errors must not kill the bridge
            log.warning("[CHATBOT] Session store unreadable: %s", e)
            get_crash_manager().report_error(
                CHATBOT_0004, detail=f"{type(e).__name__}: {e}"
            )

        self.has_session = creds is not None
        if creds is None:
            return False

        session_id, tt_target_idc = creds
        try:
            web = getattr(client, "web", None)
            set_session = getattr(web, "set_session", None)
            if not callable(set_session):
                raise TypeError("client has no web.set_session()")
            set_session(session_id, tt_target_idc)
            log.info(
                "[CHATBOT] TikTok session applied (idc=%s)",
                tt_target_idc or "default",
            )
            return True
        except Exception as e:
            self.last_error = f"session apply failed: {type(e).__name__}: {e}"
            log.warning("[CHATBOT] %s", self.last_error)
            get_crash_manager().report_exception(
                CHATBOT_0004, exc=e, context_info={"stage": "apply"}
            )
            return False
        finally:
            self.publish_status()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Long-lived worker coroutine.

        Intended to be scheduled via ``CrashManager.observe_task`` from the
        bridge's supervised worker list — same pattern as the other bridge
        workers.
        """
        self._queue = asyncio.Queue(maxsize=self.config.max_queue)
        self._sub_queue = event_bus.subscribe(
            "tiktok.gift", "tiktok.follow", "tiktok.join", "tiktok.comment"
        )
        log.info("[CHATBOT] Worker started (enabled=%s)", self.config.enabled)
        consumer = asyncio.create_task(self._consume_events())
        try:
            while True:
                text = await self._queue.get()
                try:
                    await self._send_with_protection(text)
                finally:
                    self._queue.task_done()
        finally:
            consumer.cancel()
            if self._sub_queue is not None:
                event_bus.unsubscribe(self._sub_queue)
                self._sub_queue = None
            log.info("[CHATBOT] Worker stopped")

    async def _consume_events(self) -> None:
        assert self._sub_queue is not None
        while True:
            msg = await self._sub_queue.get()
            try:
                self._handle_event(msg)
            finally:
                self._sub_queue.task_done()

    def _handle_event(self, msg: dict[str, Any]) -> None:
        if not self.config.enabled or self._auto_disabled:
            return
        data = msg.get("data", {})
        ev_type = data.get("type")
        user = str(data.get("user") or "").strip()
        if not user:
            return

        text: str | None = None
        if ev_type == "gift" and self.config.on_gift:
            text = self.config.gift_thanks.format_map(_SafeMap(user=user))
        elif ev_type == "follow" and self.config.on_follow:
            text = self.config.follow_thanks.format_map(_SafeMap(user=user))
        elif ev_type == "join" and self.config.on_join:
            text = self.config.join_welcome.format_map(_SafeMap(user=user))
        elif ev_type == "comment":
            comment = str(data.get("comment") or "").strip().lower()
            if comment:
                for keyword, reply in self.config.keyword_replies.items():
                    if comment == keyword or comment.startswith(keyword + " "):
                        text = reply.format_map(_SafeMap(user=user))
                        break

        if text:
            self.submit(text)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def submit(self, text: str) -> bool:
        """Queue *text* for sending; returns False when dropped.

        Drops are silent by design (flood protection is normal operation);
        only the counter is bumped.
        """
        if self._queue is None or self._auto_disabled:
            self.dropped_count += 1
            return False
        try:
            self._queue.put_nowait(text[: self.config.max_len])
            return True
        except asyncio.QueueFull:
            self.dropped_count += 1
            return False

    async def _send_with_protection(self, text: str) -> None:
        now = time.monotonic()

        # Per-minute window limit.
        while self._window and now - self._window[0] > 60.0:
            self._window.popleft()
        if len(self._window) >= self.config.max_per_minute:
            self.dropped_count += 1
            log.debug("[CHATBOT] Dropped (window limit): %r", text)
            return

        # Duplicate suppression — TikTok rejects identical consecutive texts.
        if self.config.dedupe_identical and text == self._last_text:
            self.dropped_count += 1
            log.debug("[CHATBOT] Dropped (duplicate): %r", text)
            return

        # Minimum interval between sends.
        wait = self.config.min_interval_s - (now - self._last_sent)
        if wait > 0:
            await asyncio.sleep(wait)

        ok = await self._send(text)
        self._last_sent = time.monotonic()
        if ok:
            self._window.append(self._last_sent)
            self._last_text = text
            self._consecutive_failures = 0
            self.sent_count += 1
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= AUTH_FAILURE_LIMIT:
                self._auto_disabled = True
                log.error("[CHATBOT] Auto-disabled after repeated failures")
                get_crash_manager().report_error(
                    CHATBOT_0003,
                    detail=f"{self._consecutive_failures} consecutive failures",
                )
                self.publish_status()

    async def _send(self, text: str) -> bool:
        client = self._client
        loop = self._client_loop
        if client is None or loop is None or loop.is_closed():
            self.last_error = "not connected"
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(client.send_room_chat(text), loop)
            await asyncio.wait_for(asyncio.wrap_future(future), timeout=10)
            self.last_error = ""
            return True
        except Exception as e:  # send errors must never kill the worker
            self.last_error = f"{type(e).__name__}: {e}"
            log.warning("[CHATBOT] Send failed: %s", self.last_error)
            get_crash_manager().report_exception(
                CHATBOT_0001, exc=e, context_info={"text_len": len(text)}
            )
            return False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "active": bool(self.config.enabled and not self._auto_disabled),
            "auto_disabled": self._auto_disabled,
            "connected": self._client is not None,
            "has_session": self.has_session,
            "sent_count": self.sent_count,
            "dropped_count": self.dropped_count,
            "queue_size": self._queue.qsize() if self._queue is not None else 0,
            "last_error": self.last_error,
        }

    def publish_status(self) -> None:
        """Publish status to the local bus and the injected sink (API SSE)."""
        status = self.get_status()
        loop = ctx_main_loop()
        if loop is not None:
            asyncio.run_coroutine_threadsafe(
                event_bus.publish("chatbot.status", status), loop
            )
        if self._status_sink is not None:
            try:
                self._status_sink(status)
            except Exception as e:  # sink failure must never break the bot
                log.debug("[CHATBOT] Status sink failed: %s", e)


def ctx_main_loop() -> asyncio.AbstractEventLoop | None:
    """Return the running main loop, or None outside asyncio context."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class _SafeMap(dict):
    """format_map helper that leaves unknown placeholders untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


# Module-level singleton accessor.
_chatbot: TikTokChatbot | None = None


def get_chatbot(
    status_sink: Callable[[dict[str, Any]], None] | None = None,
) -> TikTokChatbot:
    """Return the process-wide bot instance.

    *status_sink* is only honored on first creation; later calls return the
    existing singleton unchanged.
    """
    global _chatbot
    if _chatbot is None:
        _chatbot = TikTokChatbot(status_sink=status_sink)
    return _chatbot
