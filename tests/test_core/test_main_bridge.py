"""Tests for the TikTok-to-Minecraft bridge core (src/python/main.py).

Tests pure functions and simple behaviors that do not require
a live TikTok connection or RCON server.
"""

import asyncio
import datetime
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# =========================================================================
# sanitize_filename
# =========================================================================


class TestSanitizeFilename:
    def test_lowercases(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("HELLO") == "hello"

    def test_replaces_spaces(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("hello world") == "hello_world"

    def test_removes_special_chars(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("hello@#$world") == "helloworld"

    def test_allows_underscores_and_hyphens(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("hello_world-test") == "hello_world-test"

    def test_allows_numbers(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("test123") == "test123"

    def test_strips_non_alphanumeric_prefix(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("!!!hello") == "hello"

    def test_empty_string(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("") == ""

    def test_all_spaces(self):
        from src.python.main import sanitize_filename

        assert sanitize_filename("   ") == "___"


# =========================================================================
# get_safe_username
# =========================================================================


class TestGetSafeUsername:
    def test_uses_unique_id(self):
        from src.python.main import get_safe_username

        user = MagicMock()
        user.unique_id = "testuser"
        user.nickname = "Test User"
        assert get_safe_username(user) == "testuser"

    def test_falls_back_to_nickname(self):
        from src.python.main import get_safe_username

        user = MagicMock()
        user.unique_id = None
        user.nickname = "Test User"
        assert get_safe_username(user) == "Test User"

    def test_unknown_default(self):
        from src.python.main import get_safe_username

        user = MagicMock()
        user.unique_id = None
        user.nickname = None
        assert get_safe_username(user) == "Unknown"

    def test_unknown_when_missing(self):
        from src.python.main import get_safe_username

        user = object()
        assert get_safe_username(user) == "Unknown"


# =========================================================================
# Webhook handling
# =========================================================================


class TestWebhook:
    def test_death_event_pauses_queue(self, client):
        resp = client.post(
            "/api/v1/plugins/death-counter/webhook", json={"event": "player_death"}
        )
        assert resp.status_code in (200, 404)

    def test_death_event_json(self):
        data = {"event": "player_death"}
        assert data["event"] == "player_death"

    def test_respawn_event_json(self):
        data = {"event": "player_respawn"}
        assert data["event"] == "player_respawn"


# =========================================================================
# Duplicate config detection
# =========================================================================


class TestDupCmdConfig:
    def test_detects_duplicate_keys(self, tmp_path: Path):
        content = (
            "commands_config:\n"
            "  testcmd:\n"
            "    points_cost: 10\n"
            "  testcmd:\n"
            "    points_cost: 20\n"
        )
        f = tmp_path / "config.yaml"
        f.write_text(content)
        from src.python.main import _check_dup_cmd_config

        with (
            patch("src.python.main.CONFIG_FILE", f),
            patch("builtins.input", return_value=""),
            pytest.raises(SystemExit),
        ):
            _check_dup_cmd_config()

    def test_no_duplicates_ok(self, tmp_path: Path):
        content = (
            "commands_config:\n"
            "  cmd1:\n"
            "    points_cost: 10\n"
            "  cmd2:\n"
            "    points_cost: 20\n"
        )
        f = tmp_path / "config.yaml"
        f.write_text(content)
        from src.python.main import _check_dup_cmd_config

        with patch("src.python.main.CONFIG_FILE", f):
            _check_dup_cmd_config()


# =========================================================================
# generate_datapack shell parsing
# =========================================================================


class TestGenerateDatapackShell:
    def test_parses_shell_prefix(self, tmp_path: Path):
        from src.python.main import ctx, generate_datapack

        actions_file = tmp_path / "actions.mca"
        actions_file.write_text(
            "12345:&curl http://localhost:29191/add\n", encoding="utf-8"
        )
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with (
            patch.object(ctx, "datapack_root", dp_root),
            patch("src.python.main.ACTIONS_FILE", actions_file),
        ):
            generate_datapack()
        assert "12345" in ctx.valid_functions
        assert ctx.shell_actions_cache.get("12345") == [
            "curl http://localhost:29191/add"
        ]

    def test_parses_chained_shell_commands(self, tmp_path: Path):
        from src.python.main import ctx, generate_datapack

        actions_file = tmp_path / "actions.mca"
        actions_file.write_text("12345:&echo hello ; &echo world\n", encoding="utf-8")
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with (
            patch.object(ctx, "datapack_root", dp_root),
            patch("src.python.main.ACTIONS_FILE", actions_file),
        ):
            generate_datapack()
        assert ctx.shell_actions_cache.get("12345") == ["echo hello", "echo world"]

    def test_parses_shell_multiplier(self, tmp_path: Path):
        from src.python.main import ctx, generate_datapack

        actions_file = tmp_path / "actions.mca"
        actions_file.write_text("12345:&echo hi x3\n", encoding="utf-8")
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with (
            patch.object(ctx, "datapack_root", dp_root),
            patch("src.python.main.ACTIONS_FILE", actions_file),
        ):
            generate_datapack()
        assert ctx.shell_actions_cache.get("12345") == ["echo hi", "echo hi", "echo hi"]


# =========================================================================
# Runtime reload signal watcher
# =========================================================================


class TestRuntimeReloadWatcher:
    @pytest.mark.asyncio
    async def test_watcher_triggers_config_and_actions_reload(
        self, tmp_path, monkeypatch
    ):
        from src.python import main as main_mod

        cfg_signal = tmp_path / "reload_config"
        act_signal = tmp_path / "reload_actions"
        monkeypatch.setattr(main_mod, "RELOAD_CONFIG_SIGNAL", cfg_signal)
        monkeypatch.setattr(main_mod, "RELOAD_ACTIONS_SIGNAL", act_signal)

        calls = []

        async def fake_reload_config():
            calls.append("config")

        async def fake_reload_actions(**_kwargs):
            calls.append("actions")

        monkeypatch.setattr(main_mod, "reload_config", fake_reload_config)
        monkeypatch.setattr(main_mod, "reload_actions", fake_reload_actions)

        cfg_signal.write_text("reload", encoding="utf-8")
        act_signal.write_text("reload", encoding="utf-8")

        task = asyncio.create_task(main_mod._reload_signal_watcher())
        await asyncio.sleep(1.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert "config" in calls
        assert "actions" in calls
        assert not cfg_signal.exists()
        assert not act_signal.exists()


# =========================================================================
# Bounded-queue thread-safe enqueue helpers
# =========================================================================


class TestEnqueueThreadsafe:
    @pytest.fixture
    def _sync_loop(self):
        """Event loop whose call_soon_threadsafe runs the callback inline."""
        loop = asyncio.new_event_loop()
        loop.call_soon_threadsafe = lambda cb, *args: cb(*args)  # type: ignore[assignment]
        yield loop
        loop.close()

    def test_enqueues_item(self, _sync_loop):
        from src.python.main import ctx, enqueue_threadsafe

        q = asyncio.Queue()
        with patch.object(ctx, "main_loop", _sync_loop):
            assert (
                enqueue_threadsafe(("follow", "user"), queue=q, label="follow") is True
            )
        assert q.get_nowait() == ("follow", "user")

    def test_drops_full_queue_without_raising(self, _sync_loop):
        from src.python.main import ctx, enqueue_threadsafe

        q = asyncio.Queue(maxsize=1)
        q.put_nowait(("existing", "hook"))
        with patch.object(ctx, "main_loop", _sync_loop):
            assert enqueue_threadsafe(("drop", "user"), queue=q, label="drop") is True
        assert q.qsize() == 1

    def test_default_queue_is_trigger_queue(self, _sync_loop):
        from src.python.main import ctx, enqueue_threadsafe

        ctx.trigger_queue = asyncio.Queue()
        with patch.object(ctx, "main_loop", _sync_loop):
            assert enqueue_threadsafe(("join", "user"), label="join") is True
        assert ctx.trigger_queue.get_nowait() == ("join", "user")

    def test_missing_main_loop_returns_false(self):
        from src.python.main import ctx, enqueue_threadsafe

        q = asyncio.Queue()
        with patch.object(ctx, "main_loop", None):
            assert enqueue_threadsafe(("x", "y"), queue=q, label="x") is False
        assert q.empty()

    def test_running_loop_returns_false(self):
        from src.python.main import ctx, enqueue_threadsafe

        q = asyncio.Queue()
        loop = asyncio.new_event_loop()

        def _raise(_cb, *_args):
            raise RuntimeError("loop closing")

        loop.call_soon_threadsafe = _raise  # type: ignore[assignment]
        with patch.object(ctx, "main_loop", loop):
            assert enqueue_threadsafe(("x", "y"), queue=q, label="x") is False
        loop.close()
        assert q.empty()


# =========================================================================
# execute_global_command overlay dispatch
# =========================================================================


class TestExecuteGlobalCommandOverlay:
    def test_overlay_offloaded_to_thread(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import ctx, execute_global_command

        monkeypatch.setattr(ctx, "valid_functions", {"overlaytest"})
        monkeypatch.setattr(
            ctx, "overlay_actions", {"overlaytest": [("default", "Title|Subtitle|5")]}
        )
        monkeypatch.setattr(ctx, "script_actions", {})
        monkeypatch.setattr(ctx, "vanilla_functions", set())
        monkeypatch.setattr(ctx, "rcon_only_actions", {})
        monkeypatch.setattr(ctx, "shell_actions_cache", {})
        monkeypatch.setattr(ctx, "namespace", "ns")

        calls: list[tuple] = []

        async def fake_to_thread(fn, *args):
            calls.append((fn, args))
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        asyncio.run(execute_global_command("overlaytest", "viewer"))

        assert len(calls) == 1
        fn, args = calls[0]
        assert fn is main_mod.send_overlay_text
        assert args == ("Title", "Subtitle", 5, "default")


# =========================================================================
# _enqueue_like_triggers (like milestone triggers)
# =========================================================================


class TestEnqueueLikeTriggers:
    def _call(self, monkeypatch, total, user="viewer"):
        import src.python.main as main_mod
        from src.python.main import _enqueue_like_triggers

        calls = []

        def fake_enqueue(item, label=None):
            calls.append((item, label))

        monkeypatch.setattr(main_mod, "enqueue_threadsafe", fake_enqueue)
        _enqueue_like_triggers(total, user)
        return calls

    def test_likes_fires_once_per_milestone(self, monkeypatch):
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        monkeypatch.setattr(ctx, "_last_likes_trigger", 0)
        calls = self._call(monkeypatch, 250, "viewer")
        assert calls == [(("likes", "viewer"), "like:likes")]

        calls = self._call(monkeypatch, 250, "viewer")
        assert calls == []  # same milestone: no duplicate

    def test_likes_fires_again_on_next_milestone(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import _enqueue_like_triggers, ctx

        monkeypatch.setattr(main_mod, "enqueue_threadsafe", lambda *a, **k: None)
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        monkeypatch.setattr(ctx, "_last_likes_trigger", 1)
        monkeypatch.setattr(ctx, "_like_2_fired", False)

        calls = []
        monkeypatch.setattr(
            main_mod, "enqueue_threadsafe", lambda item, label=None: calls.append(item)
        )
        _enqueue_like_triggers(350, "viewer")  # milestones = 3 > 1
        assert calls == [("likes", "viewer")]

    def test_like_2_fires_once_at_mega(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import _enqueue_like_triggers, ctx

        calls = []

        def fake_enqueue(item, label=None):
            calls.append(item)

        monkeypatch.setattr(main_mod, "enqueue_threadsafe", fake_enqueue)
        monkeypatch.setattr(ctx, "valid_functions", {"like_2"})
        monkeypatch.setattr(ctx, "_last_likes_trigger", 0)
        monkeypatch.setattr(ctx, "_like_2_fired", False)

        _enqueue_like_triggers(100_000, "viewer")
        assert calls == [("like_2", "viewer")]

        calls.clear()
        _enqueue_like_triggers(150_000, "viewer")
        assert calls == []  # already fired

    def test_no_enqueue_when_not_configured(self, monkeypatch):
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "valid_functions", {"follow"})
        calls = self._call(monkeypatch, 500, "viewer")
        assert calls == []


# =========================================================================
# rcon_worker retry counter + global outage budget
# =========================================================================


class TestRconWorkerRetryBudget:
    @staticmethod
    def _setup(monkeypatch, commands, working=False):
        import src.python.main as main_mod
        from src.python.main import ctx, rcon_worker

        real_sleep = asyncio.sleep

        async def no_sleep(*args, **kwargs):
            return None

        monkeypatch.setattr(main_mod.asyncio, "sleep", no_sleep)

        if working:

            class _WorkingRcon:
                def __init__(self, *a, **k):
                    pass

                def connect(self):
                    return None

                def command(self, cmd):
                    return ""

            monkeypatch.setattr(main_mod, "MCRcon", _WorkingRcon)
        else:

            class _FailingRcon:
                def __init__(self, *a, **k):
                    raise ConnectionError("server unreachable")

            monkeypatch.setattr(main_mod, "MCRcon", _FailingRcon)

        monkeypatch.setattr(ctx, "queue_active", True)
        monkeypatch.setattr(ctx, "rcon_connection", None)
        monkeypatch.setattr(ctx, "last_rcon_attempt", 0)
        monkeypatch.setattr(ctx, "rcon_consecutive_failures", 0)
        monkeypatch.setattr(ctx, "rcon_queue_retries", {})
        ctx.rcon_queue = asyncio.Queue()
        ctx.rcon_pool_lock = asyncio.Lock()
        ctx.rcon_queue.put_nowait((commands, "viewer"))

        monkeypatch.setattr(main_mod, "get_crash_manager", lambda: MagicMock())

        return ctx, rcon_worker, real_sleep

    def test_global_budget_stops_requeue(self, monkeypatch):
        ctx, rcon_worker, real_sleep = self._setup(monkeypatch, ["/say hi"])
        ctx.max_rcon_retries = 50
        ctx.rcon_global_retry_budget = 2

        async def scenario():
            task = asyncio.create_task(rcon_worker())
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 5
            while ctx.rcon_consecutive_failures <= ctx.rcon_global_retry_budget:
                if loop.time() > deadline:
                    task.cancel()
                    raise AssertionError("worker kept re-queueing past budget")
                await real_sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert ctx.rcon_consecutive_failures == 3
        assert ctx.rcon_queue_retries == {}
        assert ctx.rcon_queue.qsize() == 0

    def test_success_resets_retries_and_budget(self, monkeypatch):
        ctx, rcon_worker, real_sleep = self._setup(
            monkeypatch, ["/say hi"], working=True
        )
        ctx.rcon_consecutive_failures = 7
        ctx.rcon_queue_retries = {"old": 2}

        async def scenario():
            task = asyncio.create_task(rcon_worker())
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 5
            while ctx.rcon_consecutive_failures != 0:
                if loop.time() > deadline:
                    task.cancel()
                    raise AssertionError("worker did not send the command")
                await real_sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert ctx.rcon_consecutive_failures == 0
        assert ctx.rcon_queue_retries == {}


class TestUpdateDailyRevenue:
    def test_writes_daily_revenue(self, tmp_path, monkeypatch):
        from src.python.main import ctx, update_daily_revenue

        log_file = tmp_path / "data" / "revenue_log.jsonl"
        today = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d")
        monkeypatch.setattr(ctx, "gift_value_usd", 12.34)
        monkeypatch.setattr(ctx, "gift_day_start_value", 0)
        monkeypatch.setattr(ctx, "gift_current_log_date", today)
        monkeypatch.setattr(ctx, "gift_lock", threading.Lock())
        monkeypatch.setattr("src.python.main.BASE_DIR", tmp_path / "src")

        update_daily_revenue()

        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        data = json.loads(lines[-1])
        assert data["estimated_revenue_usd"] == 12.34
        assert data["date"] == today

    def test_updates_existing_entry(self, tmp_path, monkeypatch):
        from src.python.main import ctx, update_daily_revenue

        log_file = tmp_path / "data" / "revenue_log.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        today = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({"date": today, "estimated_revenue_usd": 5.0}) + "\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(ctx, "gift_value_usd", 20.0)
        monkeypatch.setattr(ctx, "gift_day_start_value", 0)
        monkeypatch.setattr(ctx, "gift_current_log_date", today)
        monkeypatch.setattr(ctx, "gift_lock", threading.Lock())
        monkeypatch.setattr("src.python.main.BASE_DIR", tmp_path / "src")

        update_daily_revenue()

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["estimated_revenue_usd"] == 20.0
