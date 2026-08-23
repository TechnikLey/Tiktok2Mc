import asyncio
from unittest.mock import patch

import pytest


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
    loop.call_soon_threadsafe = lambda cb, *args: cb(*args)  # type: ignore[method-assign]
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
        assert result[3] == {"source": "hook"}

    def test_enqueue_trigger_with_context(self, api):
        api.enqueue_trigger(
            "combo_bonus",
            user="viewer",
            context={"event": "gift", "gift_name": "Rose", "streak": 5},
        )
        result = api._trigger_queue.get_nowait()
        assert result[3] == {
            "source": "hook",
            "event": "gift",
            "gift_name": "Rose",
            "streak": 5,
        }

    def test_enqueue_trigger_context_bound_hook_name(self, api):
        clone = api.for_hook("my_hook")
        clone.enqueue_trigger("chained")
        result = api._trigger_queue.get_nowait()
        assert result[3] == {"source": "hook", "hook": "my_hook"}

    def test_enqueue_trigger_context_source_not_overwritten(self, api):
        api.enqueue_trigger("chained", context={"source": "tiktok"})
        result = api._trigger_queue.get_nowait()
        assert result[3] == {"source": "tiktok"}

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
        with patch(
            "core.overlay_utils.send_overlay_text", return_value=True
        ) as mock_send:
            result = api.send_overlay_text("Title", "Sub", 5, "default")
        assert result is True
        mock_send.assert_called_once_with("Title", "Sub", 5, "default")

    def test_send_overlay_text_failure(self, api):
        with patch(
            "core.overlay_utils.send_overlay_text", side_effect=Exception("fail")
        ):
            result = api.send_overlay_text("Title")
        assert result is False

    def test_set_depth(self, api):
        api.set_depth(2)
        assert api._current_depth == 2


class TestHookContext:
    """HookContext: dict subclass with fail-fast attribute access."""

    def test_attribute_access_reads_keys(self):
        from core.hook_api import HookContext

        ctx = HookContext(event="gift", streak=10)
        assert ctx.event == "gift"
        assert ctx.streak == 10

    def test_unknown_attribute_raises(self):
        from core.hook_api import HookContext

        ctx = HookContext(event="gift")
        with pytest.raises(AttributeError):
            _ = ctx.gift_nane  # typo — must fail fast, not return None

    def test_get_still_works_for_optional_keys(self):
        from core.hook_api import HookContext

        ctx = HookContext(event="gift")
        assert ctx.get("combo", False) is False

    def test_dict_compatibility(self):
        import json as _json

        from core.hook_api import HookContext

        ctx = HookContext(event="gift", streak=5)
        # plain-dict interop stays intact
        assert isinstance(ctx, dict)
        assert ctx == {"event": "gift", "streak": 5}
        assert "streak" in ctx
        assert _json.dumps(ctx) == '{"event": "gift", "streak": 5}'

    def test_enqueue_trigger_produces_hook_context(self, api):
        api.enqueue_trigger("chained")
        result = api._trigger_queue.get_nowait()
        from core.hook_api import HookContext

        assert isinstance(result[3], HookContext)
        assert result[3].source == "hook"


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        import json

        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestForHook:
    def test_for_hook_binds_name_and_shares_queues(self, api):
        clone = api.for_hook("my-hook")
        assert isinstance(clone, type(api))
        assert clone.name == "my-hook"
        assert clone._rcon_queue is api._rcon_queue
        assert clone._trigger_queue is api._trigger_queue
        assert clone._config is api._config
        assert clone._valid_functions is api._valid_functions
        assert api.name == ""  # root stays unbound

    def test_unbound_api_store_set_fails(self, api):
        assert api.store_set("k", 1) is False
        assert api.store_get("k", "d") == "d"
        assert api.store_delete("k") is False
        assert api.store_all() == {}


class TestHookStore:
    """Persistent-store helpers (HTTP against the API's plugin data routes)."""

    @pytest.fixture
    def hook_api(self, api):
        return api.for_hook("my-hook")

    def test_store_set_puts_json_value(self, hook_api):
        with patch("core.hook_api.urllib.request.urlopen") as mock_open:
            assert hook_api.store_set("count", {"n": 3}) is True
        req = mock_open.call_args.args[0]
        assert req.get_method() == "PUT"
        assert "/plugins/my-hook/data/count" in req.full_url
        import json

        assert json.loads(req.data.decode()) == {"value": {"n": 3}}

    def test_store_get_returns_value(self, hook_api):
        with patch(
            "core.hook_api.urllib.request.urlopen",
            return_value=_FakeResponse({"name": "my-hook", "key": "count", "value": 7}),
        ):
            assert hook_api.store_get("count") == 7

    def test_store_get_404_returns_default(self, hook_api):
        import urllib.error
        from email.message import Message

        err = urllib.error.HTTPError("url", 404, "Not Found", Message(), None)
        with patch("core.hook_api.urllib.request.urlopen", side_effect=err):
            assert hook_api.store_get("missing", "fallback") == "fallback"

    def test_store_get_network_error_returns_default(self, hook_api):
        with patch("core.hook_api.urllib.request.urlopen", side_effect=OSError("down")):
            assert hook_api.store_get("k", None) is None

    def test_store_delete_true_on_success(self, hook_api):
        with patch(
            "core.hook_api.urllib.request.urlopen",
            return_value=_FakeResponse({}, status=200),
        ) as mock_open:
            assert hook_api.store_delete("k") is True
        assert mock_open.call_args.args[0].get_method() == "DELETE"

    def test_store_delete_false_on_404(self, hook_api):
        import urllib.error
        from email.message import Message

        err = urllib.error.HTTPError("url", 404, "Not Found", Message(), None)
        with patch("core.hook_api.urllib.request.urlopen", side_effect=err):
            assert hook_api.store_delete("gone") is False

    def test_store_all_returns_data_dict(self, hook_api):
        with patch(
            "core.hook_api.urllib.request.urlopen",
            return_value=_FakeResponse({"name": "my-hook", "data": {"a": 1}}),
        ):
            assert hook_api.store_all() == {"a": 1}
