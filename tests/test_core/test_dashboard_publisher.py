import pytest


@pytest.fixture(autouse=True)
def _reset_registry():
    import core.api.registry as reg

    reg._registry = None
    yield
    reg._registry = None


class TestDashboardPublisher:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        from core.api.dashboard_publisher import DashboardPublisher

        pub = DashboardPublisher()
        assert pub._task is None
        assert pub._running is False
        pub.start()
        assert pub._running is True
        assert pub._task is not None
        await pub.stop()
        assert pub._running is False
        assert pub._task is None

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        from core.api.dashboard_publisher import DashboardPublisher

        pub = DashboardPublisher()
        pub.start()
        t = pub._task
        pub.start()
        assert pub._task is t
        await pub.stop()

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self):
        from core.api.dashboard_publisher import DashboardPublisher

        pub = DashboardPublisher()
        await pub.stop()
        await pub.stop()

    @pytest.mark.asyncio
    async def test_stop_before_start(self):
        from core.api.dashboard_publisher import DashboardPublisher

        pub = DashboardPublisher()
        await pub.stop()

    def test_build_plugin_states_empty(self):
        from core.api.dashboard_publisher import DashboardPublisher

        states = DashboardPublisher._build_plugin_states()
        assert isinstance(states, dict)

    def test_build_ecm_diagnostics(self):
        from core.api.dashboard_publisher import DashboardPublisher

        diag = DashboardPublisher._build_ecm_diagnostics()
        assert diag is None or isinstance(diag, dict)

    def test_singleton(self):
        from core.api.dashboard_publisher import get_dashboard_publisher

        p1 = get_dashboard_publisher()
        p2 = get_dashboard_publisher()
        assert p1 is p2
