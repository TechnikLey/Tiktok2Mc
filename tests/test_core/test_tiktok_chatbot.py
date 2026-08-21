"""Tests for the native TikTok chatbot module (core.tiktok_chatbot)."""

import asyncio
import threading
import time

import pytest

import core.chatbot_session as chatbot_session
import core.paths
from core.tiktok_chatbot import (
    AUTH_FAILURE_LIMIT,
    DEFAULT_MAX_PER_MINUTE,
    DEFAULT_MIN_INTERVAL_S,
    ChatbotConfig,
    ChatbotReply,
    TikTokChatbot,
    _SafeMap,
)


@pytest.fixture
def bot(tmp_path):
    """A chatbot instance with an isolated config path and no client."""
    return TikTokChatbot(config_path=tmp_path / "chatbot.yaml")


# ---------------------------------------------------------------------------
# ChatbotConfig
# ---------------------------------------------------------------------------


class TestChatbotConfig:
    def test_defaults(self):
        cfg = ChatbotConfig()
        assert cfg.enabled is False
        assert cfg.min_interval_s == DEFAULT_MIN_INTERVAL_S == 7.0
        assert cfg.max_per_minute == DEFAULT_MAX_PER_MINUTE == 8
        assert cfg.dedupe_identical is True
        # Sensible out-of-the-box rules: gift + follow thanks.
        assert [r.on for r in cfg.replies] == ["gift", "follow"]
        assert "{user}" in cfg.replies[0].message

    def test_from_dict_none_returns_defaults(self):
        assert ChatbotConfig.from_dict(None) == ChatbotConfig()

    def test_from_dict_full_roundtrip(self):
        original = ChatbotConfig(
            enabled=True,
            min_interval_s=2.5,
            max_per_minute=7,
            max_queue=9,
            dedupe_identical=False,
            max_len=99,
            replies=[
                ChatbotReply(on="gift", match="rose", message="thx {user}"),
                ChatbotReply(on="keyword", match="discord", message="join us"),
            ],
            tt_target_idc="aws",
        )
        restored = ChatbotConfig.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_invalid_values_fall_back_to_defaults(self):
        defaults = ChatbotConfig()
        cfg = ChatbotConfig.from_dict(
            {
                "spam_protection": {
                    "min_interval_s": "not-a-number",
                    "max_per_minute": -5,
                    "max_queue": None,
                    "max_len": 0,
                }
            }
        )
        # Invalid types keep defaults; out-of-range values are clamped.
        assert cfg.min_interval_s == defaults.min_interval_s
        assert cfg.max_per_minute == 1
        assert cfg.max_queue == defaults.max_queue
        assert cfg.max_len == 1

    def test_replies_parsing_normalises_and_skips_invalid(self):
        cfg = ChatbotConfig.from_dict(
            {
                "replies": [
                    {"on": " KEYWORD ", "match": "  discord  ", "message": "hi"},
                    {"on": "bogus", "message": "ignored"},
                    "not-a-dict",
                    {"on": "gift", "match": "", "message": "  "},
                ]
            }
        )
        assert len(cfg.replies) == 1
        assert cfg.replies[0] == ChatbotReply(
            on="keyword", match="discord", message="hi"
        )

    def test_empty_replies_list_is_respected(self):
        cfg = ChatbotConfig.from_dict({"replies": []})
        assert cfg.replies == []

    def test_legacy_keys_are_ignored_no_migration(self):
        """Old triggers/templates/keyword_replies keys must NOT migrate."""
        cfg = ChatbotConfig.from_dict(
            {
                "triggers": {"gift": True, "follow": True, "join": True},
                "templates": {
                    "gift_thanks": "old gift",
                    "follow_thanks": "old follow",
                    "join_welcome": "old join",
                },
                "keyword_replies": {"discord": "old reply"},
            }
        )
        assert cfg.replies == ChatbotConfig().replies

    def test_to_dict_structure(self):
        data = ChatbotConfig(enabled=True).to_dict()
        assert set(data) == {"enabled", "spam_protection", "replies", "session"}


class TestSafeMap:
    def test_known_and_unknown_placeholders(self):
        text = "{user} sent {gift} and {unknown_thing}"
        rendered = text.format_map(_SafeMap(user="u", gift="g"))
        assert rendered == "u sent g and {unknown_thing}"


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------


class TestHandleEvent:
    def _bot_with_config(self, tmp_path, **kwargs):
        b = TikTokChatbot(config_path=tmp_path / "chatbot.yaml")
        b.config = ChatbotConfig(**kwargs)
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=b.config.max_queue)
        b._queue = queue
        return b, queue

    def test_gift_event_queues_default_reply(self, tmp_path):
        b, queue = self._bot_with_config(tmp_path, enabled=True)
        b._handle_event(
            {"data": {"type": "gift", "user": "alice", "gift_name": "Rose"}}
        )
        assert queue.qsize() == 1
        assert queue.get_nowait() == "Danke alice für rose! 💖"

    def test_disabled_bot_ignores_events(self, tmp_path):
        b, queue = self._bot_with_config(tmp_path, enabled=False)
        b._handle_event({"data": {"type": "gift", "user": "alice"}})
        assert queue.empty()

    def test_event_without_matching_rule_is_ignored(self, tmp_path):
        b, queue = self._bot_with_config(
            tmp_path, enabled=True, replies=[ChatbotReply(on="follow", message="hi")]
        )
        b._handle_event({"data": {"type": "gift", "user": "alice"}})
        assert queue.empty()

    def test_missing_user_ignored(self, tmp_path):
        b, queue = self._bot_with_config(tmp_path, enabled=True)
        b._handle_event({"data": {"type": "gift", "user": ""}})
        assert queue.empty()

    def test_empty_message_rule_is_skipped(self, tmp_path):
        b, queue = self._bot_with_config(
            tmp_path,
            enabled=True,
            replies=[
                ChatbotReply(on="gift", match="", message="   "),
                ChatbotReply(on="gift", match="", message="real thanks {user}"),
            ],
        )
        b._handle_event({"data": {"type": "gift", "user": "alice"}})
        assert queue.get_nowait() == "real thanks alice"

    def test_comment_keyword_match(self, tmp_path):
        b, queue = self._bot_with_config(
            tmp_path,
            enabled=True,
            replies=[
                ChatbotReply(on="keyword", match="discord", message="join {user}")
            ],
        )
        b._handle_event(
            {"data": {"type": "comment", "user": "carl", "comment": "DISCORD please"}}
        )
        assert queue.qsize() == 1
        assert queue.get_nowait() == "join carl"

    def test_comment_non_matching_keyword_ignored(self, tmp_path):
        b, queue = self._bot_with_config(
            tmp_path,
            enabled=True,
            replies=[ChatbotReply(on="keyword", match="discord", message="join")],
        )
        b._handle_event(
            {"data": {"type": "comment", "user": "carl", "comment": "hello there"}}
        )
        assert queue.empty()

    def test_gift_name_filter_only_fires_for_that_gift(self, tmp_path):
        b, queue = self._bot_with_config(
            tmp_path,
            enabled=True,
            replies=[
                ChatbotReply(on="gift", match="Rose", message="ROSE for {user}!"),
                ChatbotReply(on="gift", match="", message="generic thanks {user}"),
            ],
        )
        b._handle_event(
            {"data": {"type": "gift", "user": "amy", "gift_name": "TikTok"}}
        )
        assert queue.get_nowait() == "generic thanks amy"
        b._handle_event({"data": {"type": "gift", "user": "amy", "gift_name": "rose"}})
        assert queue.get_nowait() == "ROSE for amy!"

    def test_first_matching_rule_wins_no_double_post(self, tmp_path):
        b, queue = self._bot_with_config(
            tmp_path,
            enabled=True,
            replies=[
                ChatbotReply(on="gift", match="rose", message="special!"),
                ChatbotReply(on="gift", match="", message="generic!"),
            ],
        )
        b._handle_event({"data": {"type": "gift", "user": "amy", "gift_name": "Rose"}})
        assert queue.qsize() == 1
        assert queue.get_nowait() == "special!"


# ---------------------------------------------------------------------------
# Queue / submit
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_submit_drops_when_no_worker(self, bot):
        assert bot.submit("hi") is False
        assert bot.dropped_count == 1

    def test_submit_truncates_to_max_len(self, bot):
        bot._queue = asyncio.Queue(maxsize=10)
        bot.config.max_len = 5
        assert bot.submit("abcdefghij") is True
        assert bot._queue.get_nowait() == "abcde"

    def test_submit_drops_when_queue_full(self, bot):
        bot._queue = asyncio.Queue(maxsize=1)
        assert bot.submit("a") is True
        assert bot.submit("b") is False
        assert bot.dropped_count == 1

    def test_submit_drops_when_auto_disabled(self, bot):
        bot._queue = asyncio.Queue(maxsize=10)
        bot._auto_disabled = True
        assert bot.submit("a") is False


# ---------------------------------------------------------------------------
# Send protection
# ---------------------------------------------------------------------------


class TestSendProtection:
    def test_window_limit_drops(self, bot):
        bot.config.max_per_minute = 2
        now = time.monotonic()
        bot._window.extend([now, now])
        before = bot.dropped_count
        asyncio.run(bot._send_with_protection("x"))
        assert bot.dropped_count == before + 1
        assert bot.sent_count == 0

    def test_dedupe_drops_identical_consecutive(self, bot):
        bot.config.min_interval_s = 0.0
        # No client bound: the drop happens before any send attempt.
        bot._last_text = "same"
        before = bot.dropped_count
        asyncio.run(bot._send_with_protection("same"))
        assert bot.dropped_count == before + 1

    def test_send_without_client_counts_failure(self, bot):
        bot.config.min_interval_s = 0.0
        asyncio.run(bot._send_with_protection("hello"))
        assert bot.sent_count == 0
        assert bot.last_error == "not connected"
        assert bot._consecutive_failures == 1

    def test_auto_disable_after_repeated_failures(self, bot):
        bot.config.min_interval_s = 0.0
        for _ in range(AUTH_FAILURE_LIMIT):
            asyncio.run(bot._send_with_protection("hello"))
        assert bot._auto_disabled is True

    def test_successful_send_updates_state(self, bot):
        bot.config.min_interval_s = 0.0

        class FakeClient:
            async def send_room_chat(self, text):
                return None

        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        try:
            bot._client = FakeClient()
            bot._client_loop = loop
            asyncio.run(bot._send_with_protection("hello"))
            assert bot.sent_count == 1
            assert len(bot._window) == 1
            assert bot._last_text == "hello"
            assert bot.last_error == ""
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
            loop.close()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_get_status_shape(self, bot):
        status = bot.get_status()
        assert set(status) == {
            "enabled",
            "active",
            "auto_disabled",
            "connected",
            "has_session",
            "sent_count",
            "dropped_count",
            "queue_size",
            "last_error",
        }
        assert status["has_session"] is False

    def test_status_sink_receives_publishes(self, bot):
        seen = []
        bot._status_sink = seen.append
        bot.publish_status()
        assert len(seen) == 1
        assert seen[0]["enabled"] is False

    def test_status_sink_errors_are_swallowed(self, bot):
        def boom(_):
            raise RuntimeError("sink down")

        bot._status_sink = boom
        bot.publish_status()  # must not raise

    def test_bind_unbind_roundtrip(self, bot):
        loop = asyncio.new_event_loop()
        try:
            bot.bind_client(object(), loop)
            assert bot.get_status()["connected"] is True
            bot.unbind_client()
            assert bot.get_status()["connected"] is False
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Session application (Phase 4, docs/CHATBOT.md §4)
# ---------------------------------------------------------------------------


class _FakeWeb:
    def __init__(self):
        self.calls = []

    def set_session(self, session_id, tt_target_idc):
        self.calls.append((session_id, tt_target_idc))


class TestApplySession:
    def test_applies_stored_credentials(self, bot, tmp_path, monkeypatch):
        monkeypatch.setattr(
            core.paths, "get_chatbot_session_file", lambda: tmp_path / "session.json"
        )
        monkeypatch.setattr(
            chatbot_session.core.paths,
            "get_chatbot_session_file",
            lambda: tmp_path / "session.json",
        )
        chatbot_session.save_chatbot_session("s3cr3tvalue123", "va")

        web = _FakeWeb()
        client = type("C", (), {"web": web})()
        assert bot.apply_session_to_client(client) is True
        assert web.calls == [("s3cr3tvalue123", "va")]
        assert bot.has_session is True
        assert bot.get_status()["has_session"] is True

    def test_no_credentials_is_a_noop(self, bot, tmp_path, monkeypatch):
        monkeypatch.setattr(
            core.paths, "get_chatbot_session_file", lambda: tmp_path / "missing.json"
        )
        monkeypatch.setattr(
            chatbot_session.core.paths,
            "get_chatbot_session_file",
            lambda: tmp_path / "missing.json",
        )

        client = object()
        assert bot.apply_session_to_client(client) is False
        assert bot.has_session is False

    def test_client_without_web_api_reports_failure(self, bot, tmp_path, monkeypatch):
        monkeypatch.setattr(
            core.paths, "get_chatbot_session_file", lambda: tmp_path / "session.json"
        )
        monkeypatch.setattr(
            chatbot_session.core.paths,
            "get_chatbot_session_file",
            lambda: tmp_path / "session.json",
        )
        chatbot_session.save_chatbot_session("s3cr3tvalue123", "")

        assert bot.apply_session_to_client(object()) is False
        assert bot.last_error.startswith("session apply failed")


# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_missing_file_uses_defaults(self, tmp_path):
        bot = TikTokChatbot(config_path=tmp_path / "missing.yaml")
        assert bot.config == ChatbotConfig()

    def test_existing_file_is_loaded(self, tmp_path):
        from core.yaml_utils import save_yaml

        path = tmp_path / "chatbot.yaml"
        save_yaml(
            path,
            {
                "enabled": True,
                "replies": [{"on": "gift", "match": "", "message": "yo {user}"}],
            },
        )
        bot = TikTokChatbot(config_path=path)
        assert bot.config.enabled is True
        assert bot.config.replies[0].message == "yo {user}"

    def test_invalid_yaml_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "chatbot.yaml"
        path.write_text("enabled: [unclosed", encoding="utf-8")
        bot = TikTokChatbot(config_path=path)
        assert bot.config == ChatbotConfig()
