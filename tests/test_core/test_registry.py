import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def registry():
    from core.api.registry import PluginRegistry

    with tempfile.TemporaryDirectory() as tmp:
        yield PluginRegistry(Path(tmp))


class TestPluginRegistry:
    def test_register_plugin(self, registry):
        from core.api.models import PluginRegistration

        p = PluginRegistration(name="test", path="/p.exe", enabled=True)
        result = registry.register(p)
        assert result.name == "test"
        assert result.enabled is True
        assert result.registered_at is not None
        assert result.updated_at is not None

    def test_register_sets_timestamps(self, registry):
        from core.api.models import PluginRegistration

        p = registry.register(PluginRegistration(name="ts-test"))
        assert p.registered_at is not None
        assert p.updated_at is not None
        assert p.registered_at <= p.updated_at

    def test_get_plugin(self, registry):
        from core.api.models import PluginRegistration

        registry.register(PluginRegistration(name="get-test"))
        p = registry.get("get-test")
        assert p is not None
        assert p.name == "get-test"

    def test_get_nonexistent(self, registry):
        p = registry.get("nope")
        assert p is None

    def test_list_plugins(self, registry):
        from core.api.models import PluginRegistration

        for name in ["a", "b", "c"]:
            registry.register(PluginRegistration(name=name))
        plugins = registry.list()
        assert len(plugins) == 3
        names = [p.name for p in plugins]
        assert "a" in names
        assert "c" in names

    def test_list_empty(self, registry):
        assert registry.list() == []

    def test_unregister(self, registry):
        from core.api.models import PluginRegistration

        registry.register(PluginRegistration(name="del-me"))
        assert registry.unregister("del-me") is True
        assert registry.get("del-me") is None

    def test_unregister_nonexistent(self, registry):
        assert registry.unregister("nope") is False

    def test_update_partial(self, registry):
        from core.api.models import PluginRegistration

        registry.register(PluginRegistration(name="upd", enabled=False, level=2))
        updated = registry.update("upd", enabled=True, level=4)
        assert updated is not None
        assert updated.enabled is True
        assert updated.level == 4
        assert updated.port == 0

    def test_update_nonexistent(self, registry):
        updated = registry.update("nope", enabled=True)
        assert updated is None

    def test_register_overwrites(self, registry):
        from core.api.models import PluginRegistration

        registry.register(PluginRegistration(name="ovr", version="1.0"))
        registry.register(PluginRegistration(name="ovr", version="2.0"))
        p = registry.get("ovr")
        assert p.version == "2.0"

    def test_list_returns_copies(self, registry):
        from core.api.models import PluginRegistration

        registry.register(PluginRegistration(name="cpy"))
        plugins = registry.list()
        plugins[0].name = "mutated"
        assert registry.get("cpy") is not None

    def test_persistence_across_reload(self, registry):
        from core.api.models import PluginRegistration

        registry.register(PluginRegistration(name="persist", enabled=True))
        file_path = registry._file
        del registry

        from core.api.registry import PluginRegistry

        registry2 = PluginRegistry(file_path.parent)
        p = registry2.get("persist")
        assert p is not None
        assert p.enabled is True
