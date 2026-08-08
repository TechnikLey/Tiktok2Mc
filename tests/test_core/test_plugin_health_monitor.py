import time

import pytest


@pytest.fixture(autouse=True)
def _reset_registry():
    import core.api.registry as reg

    reg._registry = None
    yield
    reg._registry = None


class TestPluginHealthMonitor:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        from core.api.plugin_health import PluginHealthMonitor

        phm = PluginHealthMonitor()
        assert phm._task is None
        await phm.start()
        assert phm._task is not None
        await phm.stop()
        assert phm._task is None

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        from core.api.plugin_health import PluginHealthMonitor

        phm = PluginHealthMonitor()
        await phm.start()
        t = phm._task
        await phm.start()
        assert phm._task is t
        await phm.stop()

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self):
        from core.api.plugin_health import PluginHealthMonitor

        phm = PluginHealthMonitor()
        await phm.stop()
        await phm.stop()

    def test_check_health_marks_unhealthy_plugin(self, monkeypatch):
        from pathlib import Path

        from core.api.models import PluginRegistration
        from core.api.plugin_health import PluginHealthMonitor
        from core.api.registry import PluginRegistry

        reg = PluginRegistry(Path(""))
        reg.register(
            PluginRegistration(
                name="stale_plugin",
                enabled=True,
                last_heartbeat=time.time() - 200,
                health_status="healthy",
            )
        )
        monkeypatch.setattr("core.api.plugin_health.get_registry", lambda: reg)
        phm = PluginHealthMonitor()
        phm._check_health()
        updated = reg.get("stale_plugin")
        assert updated.health_status == "unhealthy"

    def test_check_health_skips_disabled_plugins(self, monkeypatch):
        from pathlib import Path

        from core.api.models import PluginRegistration
        from core.api.plugin_health import PluginHealthMonitor
        from core.api.registry import PluginRegistry

        reg = PluginRegistry(Path(""))
        reg.register(
            PluginRegistration(
                name="disabled_plugin",
                enabled=False,
                last_heartbeat=time.time() - 200,
                health_status="healthy",
            )
        )
        monkeypatch.setattr("core.api.plugin_health.get_registry", lambda: reg)
        phm = PluginHealthMonitor()
        phm._check_health()
        updated = reg.get("disabled_plugin")
        assert updated.health_status == "healthy"

    def test_check_health_skips_no_heartbeat(self, monkeypatch):
        from pathlib import Path

        from core.api.models import PluginRegistration
        from core.api.plugin_health import PluginHealthMonitor
        from core.api.registry import PluginRegistry

        reg = PluginRegistry(Path(""))
        reg.register(
            PluginRegistration(
                name="no_hb",
                enabled=True,
                last_heartbeat=None,
                health_status="healthy",
            )
        )
        monkeypatch.setattr("core.api.plugin_health.get_registry", lambda: reg)
        phm = PluginHealthMonitor()
        phm._check_health()
        updated = reg.get("no_hb")
        assert updated.health_status == "healthy"

    def test_check_health_promotes_to_healthy(self, monkeypatch):
        from pathlib import Path

        from core.api.models import PluginRegistration
        from core.api.plugin_health import PluginHealthMonitor
        from core.api.registry import PluginRegistry

        reg = PluginRegistry(Path(""))
        reg.register(
            PluginRegistration(
                name="fresh_plugin",
                enabled=True,
                last_heartbeat=time.time() - 5,
                health_status="starting",
            )
        )
        monkeypatch.setattr("core.api.plugin_health.get_registry", lambda: reg)
        phm = PluginHealthMonitor()
        phm._check_health()
        updated = reg.get("fresh_plugin")
        assert updated.health_status == "healthy"

    def test_check_health_dead_plugin_not_downgraded(self, monkeypatch):
        from pathlib import Path

        from core.api.models import PluginRegistration
        from core.api.plugin_health import PluginHealthMonitor
        from core.api.registry import PluginRegistry

        reg = PluginRegistry(Path(""))
        reg.register(
            PluginRegistration(
                name="dead",
                enabled=True,
                last_heartbeat=time.time() - 200,
                health_status="dead",
            )
        )
        monkeypatch.setattr("core.api.plugin_health.get_registry", lambda: reg)
        phm = PluginHealthMonitor()
        phm._check_health()
        updated = reg.get("dead")
        assert updated.health_status == "dead"

    def test_check_health_untouched_plugin_within_timeout(self, monkeypatch):
        from pathlib import Path

        from core.api.models import PluginRegistration
        from core.api.plugin_health import PluginHealthMonitor
        from core.api.registry import PluginRegistry

        reg = PluginRegistry(Path(""))
        reg.register(
            PluginRegistration(
                name="recent",
                enabled=True,
                last_heartbeat=time.time() - 10,
                health_status="healthy",
            )
        )
        monkeypatch.setattr("core.api.plugin_health.get_registry", lambda: reg)
        phm = PluginHealthMonitor()
        phm._check_health()
        updated = reg.get("recent")
        assert updated.health_status == "healthy"

    def test_singleton(self):
        from core.api.plugin_health import get_health_monitor

        m1 = get_health_monitor()
        m2 = get_health_monitor()
        assert m1 is m2
