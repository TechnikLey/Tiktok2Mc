import asyncio
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _clean_hook_actions():
    from core.hook_api import HOOK_ACTIONS

    saved = dict(HOOK_ACTIONS)
    HOOK_ACTIONS.clear()
    yield
    HOOK_ACTIONS.clear()
    HOOK_ACTIONS.update(saved)


@pytest.fixture
def api():
    from core.hook_api import HookAPI

    loop = asyncio.new_event_loop()
    rcon_q = asyncio.Queue()
    trigger_q = asyncio.Queue()
    # Make call_soon_threadsafe invoke the callback synchronously
    loop.call_soon_threadsafe = lambda cb, *args: cb(*args)
    return HookAPI(rcon_q, trigger_q, loop, {"key": "val"}, {"valid_fn"}, {})


class TestHookAPI:
    def test_config_property_returns_deepcopy(self, api):
        cfg = api.config
        cfg["key"] = "modified"
        cfg2 = api.config
        assert cfg2["key"] == "val"

    def test_get_hook_config_found(self, api):
        api._hook_configs = {"my_hook": {"setting": 1}}
        assert api.get_hook_config("my_hook") == {"setting": 1}

    def test_get_hook_config_not_found(self, api):
        assert api.get_hook_config("unknown") == {}

    def test_register_action_valid(self, api):
        def handler():
            pass

        api.register_action("my_action", handler)
        from core.hook_api import HOOK_ACTIONS

        assert "my_action" in HOOK_ACTIONS
        assert HOOK_ACTIONS["my_action"] is handler

    def test_register_action_invalid_name_empty(self, api, caplog):
        api.register_action("", lambda: None)
        from core.hook_api import HOOK_ACTIONS

        assert "" not in HOOK_ACTIONS

    def test_register_action_invalid_name_whitespace(self, api, caplog):
        api.register_action("   ", lambda: None)
        from core.hook_api import HOOK_ACTIONS

        assert "   " not in HOOK_ACTIONS

    def test_register_action_non_string_name(self, api, caplog):
        api.register_action(123, lambda: None)  # type: ignore
        from core.hook_api import HOOK_ACTIONS

        assert 123 not in HOOK_ACTIONS

    def test_register_duplicate_action_warns(self, api, caplog):
        def handler1():
            pass

        def handler2():
            pass

        api.register_action("dup", handler1)
        api.register_action("dup", handler2)
        from core.hook_api import HOOK_ACTIONS

        assert HOOK_ACTIONS["dup"] is handler1

    def test_rcon_enqueue(self, api):
        api.rcon_enqueue(["say hello", "give @a diamond"])
        result = api._rcon_queue.get_nowait()
        assert result == (["say hello", "give @a diamond"], "hook")

    def test_rcon_enqueue_empty(self, api):
        api.rcon_enqueue([])
        assert api._rcon_queue.empty()

    def test_rcon_enqueue_queue_full(self, api):
        small_q = asyncio.Queue(maxsize=1)
        loop = asyncio.new_event_loop()
        from core.hook_api import HookAPI

        api2 = HookAPI(small_q, asyncio.Queue(), loop, {}, set(), {})
        small_q.put_nowait((["existing"], "hook"))
        api2.rcon_enqueue(["dropped"])
        assert small_q.qsize() == 1

    def test_enqueue_trigger(self, api):
        api.enqueue_trigger("some_action", user="test_user")
        result = api._trigger_queue.get_nowait()
        assert result[0] == "some_action"
        assert result[1] == "test_user"
        assert result[2] == 1

    def test_enqueue_trigger_depth_check(self, api):
        api.set_depth(3)
        api.enqueue_trigger("deep_action")
        assert api._trigger_queue.empty()
        assert "deep_action" in api._banned_triggers

    def test_enqueue_trigger_banned(self, api):
        api._banned_triggers.add("banned_action")
        api.enqueue_trigger("banned_action")
        assert api._trigger_queue.empty()

    def test_enqueue_trigger_exceeds_max_depth(self, api):
        api._current_depth = 3
        api.enqueue_trigger("too_deep")
        assert api._trigger_queue.empty()
        assert "too_deep" in api._banned_triggers

    def test_log(self, api, caplog):
        import logging
        caplog.set_level(logging.INFO, logger="core.hook_api")
        api.log("test message")
        assert "test message" in caplog.text

    def test_get_valid_functions(self, api):
        funcs = api.get_valid_functions()
        assert "valid_fn" in funcs

    def test_update_runtime_state_config(self, api):
        api.update_runtime_state(config={"new": "config"})
        assert api._config == {"new": "config"}

    def test_update_runtime_state_functions(self, api):
        api.update_runtime_state(valid_functions={"new_fn"})
        assert api._valid_functions == {"new_fn"}

    def test_update_runtime_state_partial(self, api):
        api.update_runtime_state(config={"only": "config"})
        assert api._valid_functions == {"valid_fn"}

    def test_send_overlay_text_success(self, api):
        with patch("core.overlay_utils.send_overlay_text", return_value=True) as mock_send:
            result = api.send_overlay_text("Title", "Sub", 5, "default")
        assert result is True
        mock_send.assert_called_once_with("Title", "Sub", 5, "default")

    def test_send_overlay_text_failure(self, api):
        with patch("core.overlay_utils.send_overlay_text", side_effect=Exception("fail")):
            result = api.send_overlay_text("Title")
        assert result is False

    def test_set_depth(self, api):
        api.set_depth(2)
        assert api._current_depth == 2
