import pytest


class TestHookRegistration:
    def test_default_construction(self):
        from core.hook_registry import HookRegistration

        r = HookRegistration(name="test_hook")
        assert r.name == "test_hook"
        assert r.version == "1.0.0"
        assert r.enabled is True
        assert r.capabilities == []
        assert r.registered_at is not None
        assert r.updated_at is not None

    def test_to_dict(self):
        from core.hook_registry import HookRegistration

        r = HookRegistration(
            name="test_hook",
            version="2.0.0",
            enabled=True,
            display_name="Test",
            author="dev",
        )
        d = r.to_dict()
        assert d["name"] == "test_hook"
        assert d["version"] == "2.0.0"
        assert d["enabled"] is True

    def test_from_dict(self):
        from core.hook_registry import HookRegistration

        data = {
            "name": "from_dict",
            "version": "1.5.0",
            "enabled": False,
            "display_name": "From Dict",
            "description": "Created from dict",
            "author": "tester",
            "capabilities": [],
            "plugin": "",
            "update_url": "",
            "source": "",
            "error": "",
            "registered_at": 1000.0,
            "updated_at": 2000.0,
        }
        r = HookRegistration.from_dict(data)
        assert r.name == "from_dict"
        assert r.version == "1.5.0"
        assert r.enabled is False

    def test_roundtrip(self):
        from core.hook_registry import HookRegistration

        original = HookRegistration(name="rt", capabilities=["chat"])
        data = original.to_dict()
        restored = HookRegistration.from_dict(data)
        assert restored.name == "rt"
        assert restored.capabilities == ["chat"]

    def test_registered_at_defaults(self):
        import time

        from core.hook_registry import HookRegistration

        before = time.time()
        r = HookRegistration(name="timing")
        after = time.time()
        assert before <= r.registered_at <= after


class TestHookRegistry:
    @pytest.fixture
    def registry(self, tmp_path):
        from core.hook_registry import HookRegistry

        return HookRegistry(tmp_path)

    def test_register_new_hook(self, registry):
        from core.hook_registry import HookRegistration

        r = registry.register(HookRegistration(name="new_hook"))
        assert registry.get("new_hook") is not None
        assert r.name == "new_hook"

    def test_register_duplicate_preserves_enabled(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="dup", enabled=False))
        registry.register(HookRegistration(name="dup", enabled=True))
        found = registry.get("dup")
        assert found.enabled is False

    def test_register_duplicate_preserves_registered_at(self, registry):
        from core.hook_registry import HookRegistration

        r1 = registry.register(HookRegistration(name="dup"))
        orig_time = r1.registered_at
        registry.register(HookRegistration(name="dup"))
        r2 = registry.get("dup")
        assert r2.registered_at == orig_time

    def test_unregister_existing(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="del"))
        assert registry.unregister("del") is True
        assert registry.get("del") is None

    def test_unregister_nonexistent(self, registry):
        assert registry.unregister("nope") is False

    def test_list_empty(self, registry):
        assert registry.list() == []

    def test_list_with_entries(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="a"))
        registry.register(HookRegistration(name="b"))
        assert len(registry.list()) == 2

    def test_update_partial(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="upd", version="1.0"))
        reg = registry.update("upd", version="2.0", display_name="Updated")
        assert reg is not None
        assert reg.version == "2.0"
        assert reg.display_name == "Updated"

    def test_update_nonexistent(self, registry):
        reg = registry.update("nope", version="1.0")
        assert reg is None

    def test_update_does_not_set_none(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="upd"))
        reg = registry.update("upd", version=None)
        assert reg is not None
        assert reg.version == "1.0.0"

    def test_set_enabled(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="tog"))
        assert registry.set_enabled("tog", False) is True
        assert registry.is_enabled("tog") is False

    def test_set_enabled_nonexistent(self, registry):
        assert registry.set_enabled("nope", False) is False

    def test_is_enabled_default_true_for_unknown(self, registry):
        assert registry.is_enabled("unknown") is True

    def test_is_enabled_disabled(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="off", enabled=False))
        assert registry.is_enabled("off") is False

    def test_sync_from_discovery_new_hooks(self, registry):
        discovered = [
            {"name": "new_hook", "version": "1.0", "display_name": "New", "description": "", "author": "", "capabilities": [], "plugin": "", "update_url": "", "source": "/path", "_error": ""}
        ]
        count = registry.sync_from_discovery(discovered)
        assert count == 1
        assert registry.get("new_hook") is not None

    def test_sync_from_discovery_duplicates(self, registry):
        discovered = [
            {"name": "existing", "version": "1.0", "display_name": "E", "description": "", "author": "", "capabilities": [], "plugin": "", "update_url": "", "source": "/p1", "_error": ""},
            {"name": "existing", "version": "1.0", "display_name": "E", "description": "", "author": "", "capabilities": [], "plugin": "", "update_url": "", "source": "/p2", "_error": ""},
        ]
        count = registry.sync_from_discovery(discovered)
        assert count == 1

    def test_get_stale(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="active"))
        registry.register(HookRegistration(name="stale"))
        stale = registry.get_stale({"active"})
        assert stale == ["stale"]

    def test_clean_stale(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="keep"))
        registry.register(HookRegistration(name="remove"))
        count = registry.clean_stale({"keep"})
        assert count == 1
        assert registry.get("keep") is not None
        assert registry.get("remove") is None

    def test_clean_stale_no_stale(self, registry):
        from core.hook_registry import HookRegistration

        registry.register(HookRegistration(name="a"))
        count = registry.clean_stale({"a"})
        assert count == 0


class TestGetHookRegistry:
    def test_singleton(self):
        import core.hook_registry as hr
        from core.hook_registry import get_hook_registry

        hr._registry = None
        r1 = get_hook_registry()
        r2 = get_hook_registry()
        assert r1 is r2

    def test_default_storage_dir(self):
        import core.hook_registry as hr
        from core.hook_registry import get_hook_registry

        hr._registry = None
        r = get_hook_registry()
        assert r._file is not None
