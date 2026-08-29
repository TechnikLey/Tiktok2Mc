"""Tests for the TikTok-to-Minecraft bridge core (src/python/main.py).

Tests pure functions and simple behaviors that do not require
a live TikTok connection or RCON server.
"""

import asyncio
import datetime
import json
import threading
from pathlib import Path
from types import SimpleNamespace
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
# Safe event.user access (TikTokLive incompatibilities must not kill the loop)
# =========================================================================


class _BreakingUserEvent:
    """Mirrors TikTokLive proto_events where accessing ``event.user`` throws
    (e.g. ``ExtendedUser.from_user`` hitting a ``nickName`` field the installed
    proto model does not know)."""

    @property
    def user(self):
        raise TypeError("User.__init__() got an unexpected keyword argument 'nickName'")


class _GoodUserEvent:
    def __init__(self, unique_id="gooduser", nickname="Good User"):
        self.user = SimpleNamespace(unique_id=unique_id, nickname=nickname)


class TestUserAttrSafe:
    def test_returns_default_when_event_user_raises(self):
        from src.python.main import user_attr_safe

        event = _BreakingUserEvent()
        assert user_attr_safe(event, "unique_id", "fallback") == "fallback"

    def test_returns_attribute_when_user_ok(self):
        from src.python.main import user_attr_safe

        event = _GoodUserEvent(unique_id="gooduser")
        assert user_attr_safe(event, "unique_id", "fallback") == "gooduser"

    def test_returns_default_when_attr_missing(self):
        from src.python.main import user_attr_safe

        event = _GoodUserEvent()
        assert user_attr_safe(event, "is_moderator", False) is False


class TestUsernameFromEventSafe:
    def test_unknown_when_event_user_raises(self):
        from src.python.main import username_from_event_safe

        event = _BreakingUserEvent()
        assert username_from_event_safe(event) == "Unknown"

    def test_custom_default_when_event_user_raises(self):
        from src.python.main import username_from_event_safe

        event = _BreakingUserEvent()
        assert username_from_event_safe(event, default=None) is None

    def test_uses_unique_id_when_user_ok(self):
        from src.python.main import username_from_event_safe

        event = _GoodUserEvent(unique_id="gooduser")
        assert username_from_event_safe(event) == "gooduser"


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


class TestWebhookQueueSemantics:
    """E.7: queue pause/resume is config-gated, not unconditional."""

    def test_death_pauses_when_enabled(self, monkeypatch):
        from src.python import main as main_mod
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "queue_pause_on_death", True)
        monkeypatch.setattr(ctx, "queue_active", True)
        main_mod._apply_mc_queue_semantics("player_death")
        assert ctx.queue_active is False

    def test_respawn_resumes_when_enabled(self, monkeypatch):
        from src.python import main as main_mod
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "queue_pause_on_death", True)
        monkeypatch.setattr(ctx, "queue_active", False)
        main_mod._apply_mc_queue_semantics("player_respawn")
        assert ctx.queue_active is True

    def test_death_ignored_when_disabled(self, monkeypatch):
        from src.python import main as main_mod
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "queue_pause_on_death", False)
        monkeypatch.setattr(ctx, "queue_active", True)
        main_mod._apply_mc_queue_semantics("player_death")
        assert ctx.queue_active is True

    def test_respawn_ignored_when_disabled(self, monkeypatch):
        from src.python import main as main_mod
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "queue_pause_on_death", False)
        monkeypatch.setattr(ctx, "queue_active", False)
        main_mod._apply_mc_queue_semantics("player_respawn")
        assert ctx.queue_active is False

    def test_other_events_do_not_touch_queue(self, monkeypatch):
        from src.python import main as main_mod
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "queue_pause_on_death", True)
        monkeypatch.setattr(ctx, "queue_active", True)
        main_mod._apply_mc_queue_semantics("server_start")
        main_mod._apply_mc_queue_semantics("player_join")
        assert ctx.queue_active is True

    def test_apply_config_reads_gate_default_true(self, monkeypatch):
        from src.python import main as main_mod
        from src.python.main import BotContext, _apply_config

        bc = BotContext()
        monkeypatch.setattr(main_mod, "ctx", bc)
        # _apply_config ends with datapack_root.mkdir — keep it off the real FS
        monkeypatch.setattr(Path, "mkdir", lambda self, *a, **k: None)

        _apply_config({})
        assert bc.queue_pause_on_death is True
        _apply_config({"minecraft_server_api": {"queue_pause_on_death": False}})
        assert bc.queue_pause_on_death is False


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

    def test_keeps_previous_snapshot_when_build_fails(self, tmp_path: Path):
        from src.python.main import ctx, generate_datapack

        actions_file = tmp_path / "actions.mca"
        actions_file.write_text("12345:&echo hi\n", encoding="utf-8")
        dp_root = tmp_path / "datapacks"
        dp_root.mkdir(parents=True, exist_ok=True)
        with (
            patch.object(ctx, "datapack_root", dp_root),
            patch("src.python.main.ACTIONS_FILE", actions_file),
        ):
            generate_datapack()
        assert "12345" in ctx.valid_functions

        # A rebuild whose datapack root cannot be created must leave the
        # previously published snapshot intact.
        blocked_root = tmp_path / "blocked"
        blocked_root.write_text("not a directory", encoding="utf-8")
        with (
            patch.object(ctx, "datapack_root", blocked_root),
            patch("src.python.main.ACTIONS_FILE", actions_file),
        ):
            generate_datapack()
        assert "12345" in ctx.valid_functions
        assert ctx.shell_actions_cache.get("12345") == ["echo hi"]


# =========================================================================
# Runtime reload offloads blocking work to worker threads
# =========================================================================


class TestReloadOffloadsToThread:
    @pytest.mark.asyncio
    async def test_reload_actions_runs_build_in_thread(self, monkeypatch):
        from src.python import main as main_mod

        seen = {}
        main_thread = threading.get_ident()

        def fake_validate_file(*_args, **_kwargs):
            seen["validate"] = threading.get_ident()
            return []

        def fake_generate_datapack():
            seen["build"] = threading.get_ident()
            main_mod.ctx.valid_functions = {"offloaded"}

        def fake_health():
            return MagicMock()

        monkeypatch.setattr(main_mod, "validate_file", fake_validate_file)
        monkeypatch.setattr(main_mod, "generate_datapack", fake_generate_datapack)
        monkeypatch.setattr(main_mod, "get_health_monitor", fake_health)

        await main_mod.reload_actions()

        assert seen.get("validate") != main_thread
        assert seen.get("build") != main_thread

    @pytest.mark.asyncio
    async def test_reload_actions_requests_server_restart_when_opted_in(
        self, monkeypatch, tmp_path
    ):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod, "validate_file", lambda *a, **k: [])
        monkeypatch.setattr(main_mod, "generate_datapack", lambda: None)
        monkeypatch.setattr(main_mod, "get_health_monitor", lambda: MagicMock())
        monkeypatch.setattr(main_mod, "get_runtime_dir", lambda: tmp_path)

        await main_mod.reload_actions(send_minecraft_reload=True)

        assert (tmp_path / "restart_server").exists()

    @pytest.mark.asyncio
    async def test_reload_actions_does_not_restart_without_opt_in(
        self, monkeypatch, tmp_path
    ):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod, "validate_file", lambda *a, **k: [])
        monkeypatch.setattr(main_mod, "generate_datapack", lambda: None)
        monkeypatch.setattr(main_mod, "get_health_monitor", lambda: MagicMock())
        monkeypatch.setattr(main_mod, "get_runtime_dir", lambda: tmp_path)

        await main_mod.reload_actions(send_minecraft_reload=False)

        assert not (tmp_path / "restart_server").exists()


# =========================================================================
# TikTok event publishing
# =========================================================================


class TestPublishTiktokEvent:
    def test_publish_forwards_event_to_api_bus(self, monkeypatch):
        from src.python import main as main_mod

        submitted = {}

        def fake_run_in_background(fn, *args):
            submitted["fn"] = fn
            submitted["args"] = args

        monkeypatch.setattr(main_mod, "_run_in_background", fake_run_in_background)

        main_mod._publish_tiktok_event("gift", "TestUser", gift_id="5299")

        fn = submitted.get("fn")
        args = submitted.get("args")
        assert fn is main_mod._post_tiktok_event_api
        assert isinstance(args, tuple) and args
        body = json.loads(args[0])
        assert body == {
            "type": "tiktok.gift",
            "data": {"user": "TestUser", "gift_id": "5299"},
        }


# =========================================================================
# Comment worker thread
# =========================================================================


class TestCommentWorker:
    @pytest.mark.asyncio
    async def test_comment_processing_runs_on_worker_thread(self, monkeypatch):
        from src.python import main as main_mod

        # Drain any leftovers from earlier tests.
        while not main_mod._comment_queue.empty():
            main_mod._comment_queue.get()

        main_thread = threading.get_ident()
        seen = {}
        enqueued = []
        monkeypatch.setattr(main_mod.ctx, "valid_functions", {"comment"})

        def fake_process_comment_command(*_args, **_kwargs):
            seen["thread"] = threading.get_ident()
            return False

        def fake_enqueue_threadsafe(item, **kwargs):
            enqueued.append(item)

        monkeypatch.setattr(
            main_mod, "_process_comment_command", fake_process_comment_command
        )
        monkeypatch.setattr(main_mod, "enqueue_threadsafe", fake_enqueue_threadsafe)

        main_mod._start_comment_worker()
        main_mod._comment_queue.put(("tester", "!hi", False, False, False))
        main_mod._comment_queue.join()

        assert seen.get("thread") not in (None, main_thread)
        # user is always the plain username string; the comment text lives
        # only in the structured context.
        assert enqueued == [
            (
                "comment",
                "tester",
                0,
                {
                    "event": "comment",
                    "source": "tiktok",
                    "comment": "!hi",
                    "is_moderator": False,
                    "is_super_fan": False,
                    "in_fanclub": False,
                },
            )
        ]


# =========================================================================
# Follow persistence offload
# =========================================================================


class TestProcessFollowOffload:
    def test_follow_persistence_offloaded_to_background(self, tmp_path, monkeypatch):
        from src.python import main as main_mod

        tracking_file = tmp_path / "follows.txt"
        monkeypatch.setattr(main_mod.ctx, "follow_tracking_file", tracking_file)
        monkeypatch.setattr(main_mod.ctx, "follow_lock", threading.Lock())
        monkeypatch.setattr(main_mod.ctx, "_followed_cache", set())
        monkeypatch.setattr(main_mod.ctx, "valid_functions", set())

        submitted = {}

        def fake_run_in_background(fn, *args):
            submitted["fn"] = fn
            submitted["args"] = args

        monkeypatch.setattr(main_mod, "_run_in_background", fake_run_in_background)

        main_mod._process_follow("TestUser")

        assert submitted.get("fn") is main_mod._append_follow_tracking
        assert submitted.get("args") == ("testuser",)
        submitted["fn"](*submitted["args"])
        assert "testuser" in tracking_file.read_text(encoding="utf-8")


class TestHookActionOffload:
    def test_hook_action_runs_in_thread(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import ctx, execute_global_command

        def fake_action(source_user, action, extra):
            pass

        monkeypatch.setattr(ctx, "valid_functions", {"myhook"})
        monkeypatch.setattr(ctx, "script_actions", {"myhook": ["myaction"]})
        monkeypatch.setattr(ctx, "overlay_actions", {})
        monkeypatch.setattr(ctx, "vanilla_functions", set())
        monkeypatch.setattr(ctx, "rcon_only_actions", {})
        monkeypatch.setattr(ctx, "shell_actions_cache", {})
        monkeypatch.setattr(ctx, "hook_api", MagicMock())
        monkeypatch.setattr(main_mod, "HOOK_ACTIONS", {"myaction": fake_action})

        calls = []

        async def fake_to_thread(fn, *args):
            calls.append((fn, args))
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        asyncio.run(execute_global_command("myhook", "viewer"))

        assert len(calls) == 1
        assert calls[0][0] is fake_action
        # Context stays empty when no source context was provided — no
        # internal machinery (chain depth) leaks into the hook contract.
        assert calls[0][1] == ("viewer", "myaction", {})


class TestHookVeto:
    """Veto contract: a hook action returning False aborts the trigger chain."""

    def _setup_trigger(self, monkeypatch, main_mod, actions):
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "valid_functions", {"mytrigger"})
        monkeypatch.setattr(ctx, "script_actions", {"mytrigger": list(actions)})
        monkeypatch.setattr(ctx, "overlay_actions", {})
        monkeypatch.setattr(ctx, "vanilla_functions", set())
        monkeypatch.setattr(ctx, "rcon_only_actions", {})
        monkeypatch.setattr(ctx, "shell_actions_cache", {})
        monkeypatch.setattr(ctx, "hook_api", MagicMock())

        main_loop = MagicMock()
        monkeypatch.setattr(ctx, "main_loop", main_loop)
        return main_loop

    def test_veto_false_aborts_chain_and_enqueue(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import execute_global_command

        calls = []
        monkeypatch.setattr(
            main_mod,
            "HOOK_ACTIONS",
            {
                "gate": lambda *a: False,
                "after": lambda *a: calls.append("after"),
            },
        )

        async def fake_to_thread(fn, *args):
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        main_loop = self._setup_trigger(monkeypatch, main_mod, ["gate", "after"])

        asyncio.run(execute_global_command("mytrigger", "viewer"))

        # Later hook never ran, nothing enqueued to RCON.
        assert calls == []
        main_loop.call_soon_threadsafe.assert_not_called()

    def test_none_return_continues(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import ctx, execute_global_command

        monkeypatch.setattr(
            main_mod,
            "HOOK_ACTIONS",
            {"gate": lambda *a: None},
        )

        async def fake_to_thread(fn, *args):
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        rcon_queue = asyncio.Queue(maxsize=100)
        monkeypatch.setattr(ctx, "rcon_queue", rcon_queue)
        main_loop = self._setup_trigger(monkeypatch, main_mod, ["gate"])
        # vanilla command so commands_to_send is non-empty → enqueue path runs
        monkeypatch.setattr(ctx, "vanilla_functions", {"mytrigger"})
        monkeypatch.setattr(ctx, "namespace", "tiktok")

        assert rcon_queue.empty()
        asyncio.run(execute_global_command("mytrigger", "viewer"))

        main_loop.call_soon_threadsafe.assert_called_once()
        # the enqueued closure puts the command tuple on the queue
        enqueue_fn = main_loop.call_soon_threadsafe.call_args[0][0]
        enqueue_fn()
        cmds, user = rcon_queue.get_nowait()
        assert cmds == ["execute as @a run function tiktok:mytrigger"]
        assert user == "viewer"

    def test_exception_does_not_veto(self, monkeypatch):
        """An erroring hook is reported but must not veto the chain."""
        import src.python.main as main_mod
        from src.python.main import execute_global_command

        calls = []

        def broken(*_a):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            main_mod,
            "HOOK_ACTIONS",
            {
                "broken": broken,
                "after": lambda *a: calls.append("after"),
            },
        )
        monkeypatch.setattr(
            main_mod,
            "get_crash_manager",
            MagicMock(),
        )

        async def fake_to_thread(fn, *args):
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        self._setup_trigger(monkeypatch, main_mod, ["broken", "after"])

        asyncio.run(execute_global_command("mytrigger", "viewer"))

        assert calls == ["after"]


# =========================================================================
# Structured hook context (E.5)
# =========================================================================


class TestHookContext:
    """Structured context flows from the event source to hook actions."""

    def _setup_trigger(self, monkeypatch, main_mod, actions):
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "valid_functions", {"mytrigger"})
        monkeypatch.setattr(ctx, "script_actions", {"mytrigger": list(actions)})
        monkeypatch.setattr(ctx, "overlay_actions", {})
        monkeypatch.setattr(ctx, "vanilla_functions", set())
        monkeypatch.setattr(ctx, "rcon_only_actions", {})
        monkeypatch.setattr(ctx, "shell_actions_cache", {})
        monkeypatch.setattr(ctx, "hook_api", MagicMock())

    def test_context_passed_to_hook_action(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import execute_global_command

        received = {}

        def capture(user, trigger, context):
            received.update(context)

        monkeypatch.setattr(main_mod, "HOOK_ACTIONS", {"act": capture})

        async def fake_to_thread(fn, *args):
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        self._setup_trigger(monkeypatch, main_mod, ["act"])

        context = main_mod._make_hook_context(
            "gift", gift_name="Rose", gift_id="5", streak=10, combo=True
        )
        asyncio.run(execute_global_command("mytrigger", "viewer", 2, context))

        # The context reaches hooks unchanged — no internal machinery
        # (chain_depth) leaks into the event contract.
        assert received == {
            "event": "gift",
            "source": "tiktok",
            "gift_name": "Rose",
            "gift_id": "5",
            "streak": 10,
            "combo": True,
        }

    def test_context_is_hook_context_type(self, monkeypatch):
        """Hooks always receive a HookContext (dict subclass)."""
        import src.python.main as main_mod
        from core.hook_api import HookContext
        from src.python.main import execute_global_command

        seen = {}

        def capture(user, trigger, context):
            seen["user"] = user
            seen["context"] = context

        monkeypatch.setattr(main_mod, "HOOK_ACTIONS", {"act": capture})

        async def fake_to_thread(fn, *args):
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        self._setup_trigger(monkeypatch, main_mod, ["act"])

        asyncio.run(execute_global_command("mytrigger", "viewer", 0, None))

        assert isinstance(seen["context"], HookContext)
        assert isinstance(seen["context"], dict)
        assert seen["user"] == "viewer"

    def test_caller_context_not_mutated(self, monkeypatch):
        """The shared context object must stay untouched across dispatches."""
        import src.python.main as main_mod
        from src.python.main import execute_global_command

        monkeypatch.setattr(main_mod, "HOOK_ACTIONS", {"act": lambda *a: None})
        self._setup_trigger(monkeypatch, main_mod, ["act"])

        async def fake_to_thread(fn, *args):
            return fn(*args)

        monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)

        context = main_mod._make_hook_context("join")
        asyncio.run(execute_global_command("mytrigger", "viewer", 2, context))

        assert context == {"event": "join", "source": "tiktok"}

    def test_unpack_trigger_item_shapes(self):
        import src.python.main as main_mod

        assert main_mod._unpack_trigger_item(("t", "u")) == ("t", "u", 0, {})
        assert main_mod._unpack_trigger_item(("t", "u", 1)) == ("t", "u", 1, {})
        item4 = ("t", "u", 2, {"event": "gift"})
        assert main_mod._unpack_trigger_item(item4) == item4
        # non-dict context degrades to empty dict
        assert main_mod._unpack_trigger_item(("t", "u", 2, None)) == ("t", "u", 2, {})

    def test_make_hook_context_drops_none_values(self):
        import src.python.main as main_mod

        ctx_data = main_mod._make_hook_context("comment", comment=None, count=0)
        assert ctx_data == {"event": "comment", "source": "tiktok", "count": 0}

    @pytest.mark.asyncio
    async def test_worker_delivers_4_tuple_context(self, monkeypatch):
        import src.python.main as main_mod
        from src.python.main import ctx

        received = {}

        async def fake_execute(trigger, user, depth, context):
            received.update(trigger=trigger, user=user, depth=depth, context=context)

        monkeypatch.setattr(main_mod, "execute_global_command", fake_execute)
        monkeypatch.setattr(main_mod, "get_crash_manager", lambda: MagicMock())
        queue = asyncio.Queue()
        await queue.put(("gift", "viewer", 0, {"event": "gift", "streak": 5}))
        monkeypatch.setattr(ctx, "trigger_queue", queue)

        worker = asyncio.create_task(main_mod.trigger_worker())
        try:
            await asyncio.wait_for(queue.join(), timeout=2)
        finally:
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker

        assert received == {
            "trigger": "gift",
            "user": "viewer",
            "depth": 0,
            "context": {"event": "gift", "streak": 5},
        }


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

    def test_overlay_comment_placeholder_from_context(self, monkeypatch):
        """{comment} comes from the structured context, not the user param."""
        import src.python.main as main_mod
        from src.python.main import ctx, execute_global_command

        monkeypatch.setattr(ctx, "valid_functions", {"overlaytest"})
        monkeypatch.setattr(
            ctx,
            "overlay_actions",
            {"overlaytest": [("default", "{user}|{comment}|5")]},
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

        context = main_mod._make_hook_context("comment", comment="hello world")
        # user is always the plain username string now
        asyncio.run(execute_global_command("overlaytest", "tester", 0, context))

        assert len(calls) == 1
        _, args = calls[0]
        assert args == ("tester", "hello world", 5, "default")


# =========================================================================
# _enqueue_like_triggers (configurable like milestone triggers)
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

    def _expected_like_item(self, function, payload, total, every, rule_id):
        """Queue item expected for a like milestone trigger."""
        context = {
            "event": "like",
            "source": "tiktok",
            "total_since_start": total,
            "milestone_every": every,
            "milestone_rule": rule_id,
        }
        return (function, payload, 0, context)

    def test_likes_fires_once_per_milestone(self, monkeypatch):
        from src.python.main import ctx, prepare_like_triggers

        rule = {
            "id": "likes_standard",
            "every": 100,
            "function": "likes",
            "payload": "Community",
            "enabled": True,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        monkeypatch.setattr(ctx, "like_triggers", prepare_like_triggers([rule]))
        calls = self._call(monkeypatch, 150, "viewer")  # 1 milestone crossed
        assert calls == [
            (
                self._expected_like_item(
                    "likes", "Community", 150, 100, "likes_standard"
                ),
                "like:likes_standard",
            )
        ]

        calls = self._call(monkeypatch, 150, "viewer")
        assert calls == []  # same milestone: no duplicate

    def test_likes_fires_again_on_next_milestone(self, monkeypatch):
        from src.python.main import ctx, prepare_like_triggers

        rule = {
            "id": "likes_standard",
            "every": 100,
            "function": "likes",
            "payload": "Community",
            "enabled": True,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        prepared = prepare_like_triggers([rule])
        prepared[0]["last_blocks"] = 1
        monkeypatch.setattr(ctx, "like_triggers", prepared)
        calls = self._call(monkeypatch, 250, "viewer")  # milestone 2 > 1
        assert calls == [
            (
                self._expected_like_item(
                    "likes", "Community", 250, 100, "likes_standard"
                ),
                "like:likes_standard",
            )
        ]

    def test_catches_up_when_multiple_milestones_crossed(self, monkeypatch):
        from src.python.main import ctx, prepare_like_triggers

        rule = {
            "id": "likes_standard",
            "every": 100,
            "function": "likes",
            "payload": "Community",
            "enabled": True,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        monkeypatch.setattr(ctx, "like_triggers", prepare_like_triggers([rule]))
        calls = self._call(monkeypatch, 350, "viewer")  # milestones 1,2,3
        item = (
            self._expected_like_item("likes", "Community", 350, 100, "likes_standard"),
            "like:likes_standard",
        )
        assert calls == [item, item, item]

    def test_like_2_fires_once_at_mega(self, monkeypatch):
        from src.python.main import ctx, prepare_like_triggers

        rule = {
            "id": "likes_100k",
            "every": 100_000,
            "function": "like_2",
            "payload": "Community",
            "enabled": True,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"like_2"})
        monkeypatch.setattr(ctx, "like_triggers", prepare_like_triggers([rule]))
        calls = self._call(monkeypatch, 100_000, "viewer")
        assert calls == [
            (
                self._expected_like_item(
                    "like_2", "Community", 100_000, 100_000, "likes_100k"
                ),
                "like:likes_100k",
            )
        ]

        calls = self._call(monkeypatch, 150_000, "viewer")
        assert calls == []  # already fired

    def test_no_enqueue_when_not_configured(self, monkeypatch):
        from src.python.main import ctx

        monkeypatch.setattr(ctx, "valid_functions", {"follow"})
        monkeypatch.setattr(ctx, "like_triggers", [])
        calls = self._call(monkeypatch, 500, "viewer")
        assert calls == []

    def test_skips_rules_without_action(self, monkeypatch):
        from src.python.main import ctx, prepare_like_triggers

        rule = {
            "id": "no_action",
            "every": 50,
            "function": "missing_trigger",
            "payload": "Community",
            "enabled": True,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        prepared = prepare_like_triggers([rule])
        assert prepared == []  # function has no action in actions.mca

    def test_disabled_rules_are_skipped(self, monkeypatch):
        from src.python.main import ctx, prepare_like_triggers

        rule = {
            "id": "off",
            "every": 50,
            "function": "likes",
            "payload": "Community",
            "enabled": False,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        assert prepare_like_triggers([rule]) == []

    def test_locks_not_nested_when_called_under_like_lock(self, monkeypatch):
        """Regression: on_like calls _enqueue_like_triggers WHILE holding
        ctx.like_lock. The helper re-acquiring the (non-reentrant) lock used to
        deadlock the TikTok reader thread after the second like event (burst
        then silence). The helper must not nest the lock."""
        import threading

        import src.python.main as main_mod
        from src.python.main import _enqueue_like_triggers, ctx, prepare_like_triggers

        rule = {
            "id": "likes_standard",
            "every": 100,
            "function": "likes",
            "payload": "Community",
            "enabled": True,
        }
        monkeypatch.setattr(ctx, "valid_functions", {"likes"})
        monkeypatch.setattr(ctx, "like_triggers", prepare_like_triggers([rule]))

        calls = []
        monkeypatch.setattr(
            main_mod,
            "enqueue_threadsafe",
            lambda item, label=None: calls.append((item, label)),
        )
        result = {}

        def worker():
            # Mirrors on_like (main.py: on_like after fix): caller holds the lock.
            with ctx.like_lock:
                _enqueue_like_triggers(150, "viewer")
            result["done"] = True

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "deadlock: helper re-acquired lock held by caller"
        assert result.get("done")
        assert calls and calls[0][1] == "like:likes_standard"


class TestUpdateLikeTotals:
    """_update_like_totals — robust accumulation of TikTok's oscillating count."""

    def _call(self, previous, new, session):
        from src.python.main import _update_like_totals

        return _update_like_totals(previous, new, session)

    def test_first_reading_sets_floor(self):
        # previous=None: just record the new total, session unchanged.
        assert self._call(None, 58157, 0) == (0, 58157)

    def test_positive_delta_accumulates(self):
        assert self._call(58157, 58200, 0) == (43, 58200)  # +43 new likes

    def test_rewind_adds_nothing_and_moves_floor(self):
        # total drops (mid-stream baseline reload): no new likes, floor moves.
        assert self._call(58157, 58117, 0) == (0, 58117)

    def test_rewind_then_growth_counts_only_new(self):
        session, floor = self._call(58157, 58117, 0)
        assert (session, floor) == (0, 58117)
        session, floor = self._call(floor, 58217, session)  # +100 real
        assert (session, floor) == (100, 58217)

    def test_never_negative(self):
        session, floor = 0, 58157
        for total in (58117, 58000, 57999):
            session, floor = self._call(floor, total, session)
        assert session >= 0
        assert floor == 57999

    def test_equal_total_is_noop(self):
        assert self._call(500, 500, 10) == (10, 500)


class TestValidateLikeTriggers:
    def test_defaults_payload_and_enabled(self):
        from src.python.main import validate_like_triggers

        rules = validate_like_triggers([{"id": "a", "every": 100, "function": "likes"}])
        assert rules == [
            {
                "id": "a",
                "every": 100,
                "function": "likes",
                "payload": "Community",
                "enabled": True,
            }
        ]

    def test_accepts_underscore_every_and_string_enabled(self):
        from src.python.main import validate_like_triggers

        rules = validate_like_triggers(
            [
                {
                    "id": "d",
                    "every": "1_000",
                    "function": "like_2",
                    "payload": "Mega",
                    "enabled": "false",
                }
            ]
        )
        assert rules == [
            {
                "id": "d",
                "every": 1000,
                "function": "like_2",
                "payload": "Mega",
                "enabled": False,
            }
        ]

    def test_rejects_invalid_entries(self):
        from src.python.main import validate_like_triggers

        rules = validate_like_triggers(
            [
                {"id": "", "every": 100, "function": "likes"},
                {"id": "b", "every": 0, "function": "likes"},
                {"id": "c", "every": 100, "function": ""},
                {"id": "d", "every": 100, "function": "likes", "payload": 42},
                "not-a-dict",
            ]
        )
        assert rules == []

    def test_duplicate_ids_skipped(self):
        from src.python.main import validate_like_triggers

        rules = validate_like_triggers(
            [
                {"id": "a", "every": 100, "function": "likes"},
                {"id": "a", "every": 200, "function": "likes"},
            ]
        )
        assert [r["id"] for r in rules] == ["a"]

    def test_non_list_returns_empty(self):
        from src.python.main import validate_like_triggers

        assert validate_like_triggers(None) == []
        assert validate_like_triggers("nope") == []


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


class TestRequeueRcon:
    def test_requeues_when_queue_has_space(self, monkeypatch):
        from src.python.main import _requeue_rcon, ctx

        q = asyncio.Queue(maxsize=2)
        q.put_nowait(("a", "u"))
        monkeypatch.setattr(ctx, "rcon_queue", q)

        _requeue_rcon(["b"], "u")

        assert q.qsize() == 2

    def test_drops_without_blocking_when_queue_full(self, monkeypatch):
        from src.python.main import _requeue_rcon, ctx

        q = asyncio.Queue(maxsize=1)
        q.put_nowait(("a", "u"))
        monkeypatch.setattr(ctx, "rcon_queue", q)

        # The worker is the only consumer of the bounded queue: a blocking
        # put here would deadlock it permanently. put_nowait must return
        # immediately and simply drop the item.
        _requeue_rcon(["b"], "u")

        assert q.qsize() == 1


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


class TestSessionSummary:
    def test_reset_session_resets_counters(self, monkeypatch):
        from src.python.main import _reset_session, ctx

        monkeypatch.setattr(ctx, "session_gifts", 99)
        monkeypatch.setattr(ctx, "session_gift_value_usd", 99.0)
        monkeypatch.setattr(ctx, "session_likes", 99)
        monkeypatch.setattr(ctx, "session_follows", 99)
        monkeypatch.setattr(ctx, "session_comments", 99)
        monkeypatch.setattr(ctx, "session_shares", 99)
        monkeypatch.setattr(ctx, "session_joins", 99)
        monkeypatch.setattr(ctx, "session_end_ts", 1.0)

        _reset_session()

        assert ctx.session_gifts == 0
        assert ctx.session_gift_value_usd == 0.0
        assert ctx.session_likes == 0
        assert ctx.session_follows == 0
        assert ctx.session_comments == 0
        assert ctx.session_shares == 0
        assert ctx.session_joins == 0
        assert ctx.session_end_ts is None
        assert ctx.session_start_ts is not None

    def test_session_summary_entry_snapshot(self, monkeypatch):
        from src.python.main import _session_summary_entry, ctx

        monkeypatch.setattr(ctx, "session_start_ts", 1000.0)
        monkeypatch.setattr(ctx, "session_end_ts", 4600.0)
        monkeypatch.setattr(ctx, "session_gifts", 12)
        monkeypatch.setattr(ctx, "session_gift_value_usd", 4.5)
        monkeypatch.setattr(ctx, "session_likes", 340)
        monkeypatch.setattr(ctx, "session_follows", 5)
        monkeypatch.setattr(ctx, "session_comments", 78)
        monkeypatch.setattr(ctx, "session_shares", 2)
        monkeypatch.setattr(ctx, "session_joins", 41)

        entry = _session_summary_entry()

        assert entry["duration_seconds"] == 3600.0
        assert entry["gifts"] == 12
        assert entry["gift_value_usd"] == 4.5
        assert entry["likes"] == 340
        assert entry["follows"] == 5
        assert entry["comments"] == 78
        assert entry["shares"] == 2
        assert entry["joins"] == 41
        assert entry["start"].startswith("1970-01-01T00:16:40")

    def test_session_summary_entry_empty_without_start(self, monkeypatch):
        from src.python.main import _session_summary_entry, ctx

        monkeypatch.setattr(ctx, "session_start_ts", None)
        assert _session_summary_entry() == {}

    def test_save_session_summary_appends(self, tmp_path, monkeypatch):
        from src.python.main import _save_session_summary

        monkeypatch.setattr("src.python.main.BASE_DIR", tmp_path / "src")
        log_file = tmp_path / "data" / "sessions.jsonl"

        _save_session_summary({"start": "2026-08-16T20:00:00+00:00", "gifts": 3})
        _save_session_summary({"start": "2026-08-17T20:00:00+00:00", "gifts": 7})

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["gifts"] == 3
        assert json.loads(lines[1])["gifts"] == 7

    def test_save_session_summary_ignores_empty(self, tmp_path, monkeypatch):
        from src.python.main import _save_session_summary

        monkeypatch.setattr("src.python.main.BASE_DIR", tmp_path / "src")
        _save_session_summary({})
        assert not (tmp_path / "data" / "sessions.jsonl").exists()


# =========================================================================
# Webhook endpoint auth (X-API-Key on non-localhost requests)
# =========================================================================


class TestWebhookAuth:
    def _make_request(self, remote_addr, api_key_header=None):
        class _Headers:
            def get(self, name, default=""):
                if name == "X-API-Key":
                    return api_key_header if api_key_header is not None else ""
                return default

        req = SimpleNamespace(remote_addr=remote_addr, headers=_Headers())
        return req

    def test_localhost_bypasses_auth(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": "secret"})
        monkeypatch.setattr(main_mod, "request", self._make_request("127.0.0.1"))

        assert main_mod._webhook_request_authorized() is True

    def test_non_localhost_accepts_matching_key(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": "secret"})
        monkeypatch.setattr(
            main_mod, "request", self._make_request("192.168.1.50", "secret")
        )

        assert main_mod._webhook_request_authorized() is True

    def test_non_localhost_rejects_wrong_key(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": "secret"})
        monkeypatch.setattr(
            main_mod, "request", self._make_request("192.168.1.50", "wrong")
        )

        assert main_mod._webhook_request_authorized() is False

    def test_non_localhost_rejects_missing_key(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": "secret"})
        monkeypatch.setattr(main_mod, "request", self._make_request("192.168.1.50"))

        assert main_mod._webhook_request_authorized() is False

    def test_no_key_configured_allows_non_localhost(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": ""})
        monkeypatch.setattr(main_mod, "request", self._make_request("192.168.1.50"))

        assert main_mod._webhook_request_authorized() is True

    def test_before_request_guard_returns_401_when_unauthorized(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": "secret"})
        monkeypatch.setattr(main_mod, "request", self._make_request("10.0.0.9"))

        resp = main_mod._bridge_auth_check()
        assert resp is not None
        body, code = resp
        assert code == 401
        assert "X-API-Key" in body["message"]

    def test_before_request_guard_allows_localhost(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod.ctx, "config", {"api_key": "secret"})
        monkeypatch.setattr(main_mod, "request", self._make_request("127.0.0.1"))

        assert main_mod._bridge_auth_check() is None


# =========================================================================
# Comment command namespace normalization
# =========================================================================


class TestCommentCommandNamespace:
    """minecraft:<cmd> must hit the same allow/deny entry as <cmd>."""

    def _setup_ctx(self, monkeypatch, group):
        import src.python.main as main_mod
        from src.python.main import BotContext

        bc = BotContext()
        rcon_queue = asyncio.Queue()
        bc.rcon_queue = rcon_queue

        def fake_enqueue(item, *, queue=None, label="event"):
            (queue or bc.trigger_queue).put_nowait(item)
            return True

        monkeypatch.setattr(main_mod, "enqueue_threadsafe", fake_enqueue)
        for name, obj in vars(main_mod.ctx).items():
            if name.startswith("comment_cmd"):
                setattr(bc, name, obj)
        bc.comment_cmd_enable = True
        bc.comment_cmd_groups = [group]
        monkeypatch.setattr(main_mod, "ctx", bc)
        return bc

    def _group(self, mode, commands):
        return {
            "prefix": "!",
            "roles": ["all"],
            "mode": mode,
            "commands": list(commands),
            "cooldown": 0,
            "user_cooldown": 0,
            "handler": "rcon",
            "trigger_comment_event": False,
        }

    def test_allow_all_blocklist_catches_namespace(self, monkeypatch):
        from src.python.main import _process_comment_command

        group = self._group("allow-all", ["op"])
        bc = self._setup_ctx(monkeypatch, group)

        suppressed = _process_comment_command(
            "viewer", "!minecraft:op herobrine", False, False, False
        )

        assert bc.rcon_queue.empty()
        assert suppressed is True

    def test_deny_all_allowlist_accepts_namespace(self, monkeypatch):
        from src.python.main import _process_comment_command

        group = self._group("deny-all", ["tp"])
        bc = self._setup_ctx(monkeypatch, group)

        suppressed = _process_comment_command(
            "viewer", "!minecraft:tp 0 64 0", False, False, False
        )

        assert not bc.rcon_queue.empty()
        assert suppressed is True

    def test_deny_all_still_blocks_unlisted_namespace(self, monkeypatch):
        from src.python.main import _process_comment_command

        group = self._group("deny-all", ["tp"])
        bc = self._setup_ctx(monkeypatch, group)

        _process_comment_command(
            "viewer", "!minecraft:op herobrine", False, False, False
        )

        assert bc.rcon_queue.empty()

    def test_plain_command_still_works(self, monkeypatch):
        from src.python.main import _process_comment_command

        group = self._group("deny-all", ["tp"])
        bc = self._setup_ctx(monkeypatch, group)

        _process_comment_command("viewer", "!tp 100 64 100", False, False, False)

        assert not bc.rcon_queue.empty()
        cmds, user = bc.rcon_queue.get_nowait()
        assert cmds == ["tp 100 64 100"]
        assert user == "viewer"


class TestBridgeOriginGuard:
    """Cross-site browser requests against the bridge port must be rejected."""

    def _make_request(
        self, remote_addr="127.0.0.1", host="127.0.0.1:29188", headers=None
    ):
        hdrs = {"host": host}
        hdrs.update(headers or {})
        return SimpleNamespace(remote_addr=remote_addr, host=host, headers=hdrs)

    def test_cross_origin_from_localhost_rejected(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "request",
            self._make_request(headers={"origin": "https://evil.example"}),
        )
        resp = main_mod._bridge_origin_check()
        assert resp is not None and resp[1] == 403

    def test_same_host_origin_allowed(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "request",
            self._make_request(headers={"origin": "http://127.0.0.1:29188"}),
        )
        assert main_mod._bridge_origin_check() is None

    def test_cross_site_fetch_without_origin_rejected(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "request",
            self._make_request(headers={"sec-fetch-site": "cross-site"}),
        )
        resp = main_mod._bridge_origin_check()
        assert resp is not None and resp[1] == 403

    def test_non_browser_client_unaffected(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(main_mod, "request", self._make_request())
        assert main_mod._bridge_origin_check() is None

    def test_dns_rebinding_host_rejected(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(
            main_mod, "request", self._make_request(host="attacker.example")
        )
        resp = main_mod._bridge_origin_check()
        assert resp is not None and resp[1] == 403

    def test_own_hostname_allowed(self, monkeypatch):
        import socket as socket_mod

        from src.python import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "request",
            self._make_request(host=f"{socket_mod.gethostname()}:29188"),
        )
        assert main_mod._bridge_origin_check() is None

    def test_non_localhost_remote_skips_host_check(self, monkeypatch):
        from src.python import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "request",
            self._make_request(remote_addr="192.168.1.50", host="192.168.1.50:29188"),
        )
        assert main_mod._bridge_origin_check() is None
