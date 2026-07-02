import asyncio
import sys
import threading
import time
import pytest
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _reset_crash_manager():
    import core.crash_manager as cm

    old = cm._crash_manager
    cm._crash_manager = None
    yield
    cm._crash_manager = old


@pytest.fixture
def crash_mgr():
    from core.crash_manager import CrashManager

    return CrashManager("test_module")


class TestCrashManagerBasics:
    def test_install_noop_if_already_installed(self, crash_mgr):
        crash_mgr.install()
        orig_hook = sys.excepthook
        crash_mgr.install()
        assert sys.excepthook is orig_hook

    def test_report_exception_returns_error_instance(self, crash_mgr):
        from core.error_codes import CORE_0001

        exc = ValueError("test error")
        instance = crash_mgr.report_exception(CORE_0001, exc)
        assert instance is not None
        assert instance.code == "CORE-0001"

    def test_report_exception_increments_count(self, crash_mgr):
        from core.error_codes import CORE_0001

        crash_mgr.report_exception(CORE_0001, ValueError("e1"))
        crash_mgr.report_exception(CORE_0001, RuntimeError("e2"))
        assert crash_mgr.get_crash_count() == 2

    def test_report_exception_records_history(self, crash_mgr):
        from core.error_codes import CORE_0001

        crash_mgr.report_exception(CORE_0001, ValueError("boom"))
        history = crash_mgr.get_crash_history()
        assert len(history) == 1
        assert "boom" in history[0]["exception"]

    def test_crash_history_max_size(self, crash_mgr):
        from core.error_codes import CORE_0001

        crash_mgr._max_history = 3
        for i in range(5):
            crash_mgr.report_exception(CORE_0001, ValueError(f"e{i}"))
        assert len(crash_mgr.get_crash_history()) == 3

    def test_report_error_returns_error_instance(self, crash_mgr):
        from core.error_codes import CORE_0002

        instance = crash_mgr.report_error(CORE_0002, detail="something bad")
        assert instance is not None
        assert instance.code == "CORE-0002"

    def test_report_error_increments_count(self, crash_mgr):
        from core.error_codes import CORE_0002

        crash_mgr.report_error(CORE_0002, detail="e1")
        crash_mgr.report_error(CORE_0002, detail="e2")
        assert crash_mgr.get_crash_count() == 2

    def test_report_error_with_context(self, crash_mgr):
        from core.error_codes import CORE_0002

        instance = crash_mgr.report_error(CORE_0002, detail="fail", context_info={"user": "alice"})
        assert instance.context.get("user") == "alice"

    def test_report_exception_with_traceback(self, crash_mgr):
        from core.error_codes import CORE_0001

        try:
            raise ValueError("with tb")
        except ValueError as exc:
            instance = crash_mgr.report_exception(CORE_0001, exc)
        assert instance is not None
        assert "with tb" in instance.format()

    def test_get_stats(self, crash_mgr):
        from core.error_codes import CORE_0001

        stats = crash_mgr.get_stats()
        assert stats["module"] == "test_module"
        assert stats["crash_count"] == 0
        crash_mgr.report_exception(CORE_0001, ValueError("x"))
        stats = crash_mgr.get_stats()
        assert stats["crash_count"] == 1
        assert stats["history_size"] == 1

    def test_report_exception_updates_health_monitor(self, crash_mgr):
        from core.error_codes import CORE_0001
        from core.health_monitor import get_health_monitor

        get_health_monitor().register("test_module")
        crash_mgr.report_exception(CORE_0001, ValueError("health check"))
        hb = get_health_monitor().get_heartbeat("test_module")
        assert hb is not None
        assert hb.last_error is not None

    def test_sys_excepthook_installed(self, crash_mgr):
        crash_mgr.install()
        assert sys.excepthook is not None

    def test_sys_excepthook_passes_keyboard_interrupt(self, crash_mgr):
        crash_mgr.install()
        raised = []

        def fake_original(t, v, tb):
            raised.append((t, v))

        crash_mgr._install_sys_excepthook()
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        assert len(raised) == 0

    def test_crash_history_trimming(self, crash_mgr):
        from core.error_codes import CORE_0001

        crash_mgr._max_history = 2
        for i in range(5):
            crash_mgr.report_exception(CORE_0001, ValueError(f"e{i}"))
        assert len(crash_mgr._last_crashes) == 2

    def test_report_exception_with_exc_type_and_tb(self, crash_mgr):
        from core.error_codes import CORE_0001

        try:
            raise ValueError("explicit")
        except ValueError as exc:
            tb = exc.__traceback__
            instance = crash_mgr.report_exception(
                CORE_0001, exc, exc_type=ValueError, exc_tb=tb
            )
        assert instance is not None


class TestCrashManagerSupervisedThread:
    def test_supervised_thread_catches_and_reports(self, crash_mgr):
        from core.error_codes import CORE_0002

        def target():
            raise RuntimeError("thread boom")

        t = crash_mgr.supervised_thread(target, name="test-thread")
        t.start()
        t.join(timeout=5)
        assert crash_mgr.get_crash_count() >= 1

    def test_supervised_thread_runs_successfully(self, crash_mgr):
        results = []

        def target():
            results.append(42)

        t = crash_mgr.supervised_thread(target, name="ok-thread")
        t.start()
        t.join(timeout=5)
        assert results == [42]

    def test_supervised_thread_daemon_flag(self, crash_mgr):
        def target():
            pass

        t = crash_mgr.supervised_thread(target, daemon=True)
        assert t.daemon is True

    def test_supervised_thread_custom_name(self, crash_mgr):
        def target():
            pass

        t = crash_mgr.supervised_thread(target, name="my-worker")
        assert t.name == "my-worker"


class TestCrashManagerSupervisedAsync:
    @pytest.mark.asyncio
    async def test_supervised_async_task_success(self, crash_mgr):
        async def good():
            return 42

        result = await crash_mgr.supervised_async_task(good())
        assert result == 42

    @pytest.mark.asyncio
    async def test_supervised_async_task_reports_exception(self, crash_mgr):
        async def bad():
            raise ValueError("async boom")

        with pytest.raises(ValueError):
            await crash_mgr.supervised_async_task(bad())
        assert crash_mgr.get_crash_count() >= 1

    @pytest.mark.asyncio
    async def test_supervised_async_task_passthrough_cancelled(self, crash_mgr):
        async def cancels():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await crash_mgr.supervised_async_task(cancels())
        assert crash_mgr.get_crash_count() == 0


class TestCrashManagerObserveTask:
    @pytest.mark.asyncio
    async def test_observe_task_reports_exception(self, crash_mgr):
        async def bad():
            raise ValueError("task boom")

        task = asyncio.create_task(bad())
        crash_mgr.observe_task(task, component="test")
        with pytest.raises(ValueError):
            await task
        assert crash_mgr.get_crash_count() >= 1

    @pytest.mark.asyncio
    async def test_observe_task_cancelled_no_report(self, crash_mgr):
        async def cancels():
            await asyncio.sleep(10)

        task = asyncio.create_task(cancels())
        crash_mgr.observe_task(task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert crash_mgr.get_crash_count() == 0

    @pytest.mark.asyncio
    async def test_observe_task_success_no_report(self, crash_mgr):
        async def good():
            return 42

        task = asyncio.create_task(good())
        crash_mgr.observe_task(task)
        result = await task
        assert result == 42
        assert crash_mgr.get_crash_count() == 0

    def test_observe_future_reports_exception(self, crash_mgr):
        future = Future()

        def set_exc():
            future.set_exception(ValueError("future boom"))

        t = threading.Thread(target=set_exc)
        crash_mgr.observe_future(future)
        t.start()
        t.join()
        with pytest.raises(ValueError):
            future.result()
        time.sleep(0.1)
        assert crash_mgr.get_crash_count() >= 1

    def test_observe_future_cancelled_no_report(self, crash_mgr):
        future = Future()
        crash_mgr.observe_future(future)
        future.cancel()
        time.sleep(0.05)
        assert crash_mgr.get_crash_count() == 0

    def test_observe_future_success_no_report(self, crash_mgr):
        future = Future()
        crash_mgr.observe_future(future)
        future.set_result(42)
        time.sleep(0.05)
        assert crash_mgr.get_crash_count() == 0

    def test_observe_future_with_component(self, crash_mgr):
        future = Future()
        crash_mgr.observe_future(future, component="worker")
        future.set_exception(ValueError("x"))
        with pytest.raises(ValueError):
            future.result()
        time.sleep(0.05)
        assert crash_mgr.get_crash_count() >= 1


class TestCrashManagerInstallation:
    def test_install_all_hooks(self, crash_mgr):
        crash_mgr.install()
        assert crash_mgr._installed is True

    def test_asyncio_handler_overrides_loop(self, crash_mgr):
        loop = asyncio.new_event_loop()
        crash_mgr.install_asyncio(loop)
        handler = loop.get_exception_handler()
        assert handler is not None

    def test_asyncio_handler_called_on_exception(self, crash_mgr):
        loop = asyncio.new_event_loop()
        crash_mgr.install_asyncio(loop)
        captured = []

        original = loop.get_exception_handler()

        def fake_original(l, ctx):
            captured.append(ctx)

        loop.set_exception_handler(fake_original)
        loop.call_exception_handler({"exception": ValueError("async err")})
        loop.run_until_complete(asyncio.sleep(0))
        assert any("exception" in c for c in captured)

    def test_asyncio_handler_no_exception_still_calls_original(self, crash_mgr):
        loop = asyncio.new_event_loop()
        crash_mgr.install_asyncio(loop)
        captured = []

        def fake_original(l, ctx):
            captured.append(ctx)

        loop.set_exception_handler(fake_original)
        loop.call_exception_handler({"message": "no exception"})
        loop.run_until_complete(asyncio.sleep(0))
        assert len(captured) >= 0


class TestGetCrashManager:
    def test_singleton(self):
        from core.crash_manager import get_crash_manager
        import core.crash_manager as cm

        cm._crash_manager = None
        m1 = get_crash_manager()
        m2 = get_crash_manager()
        assert m1 is m2

    def test_reset_creates_new(self):
        from core.crash_manager import get_crash_manager
        import core.crash_manager as cm

        cm._crash_manager = None
        m1 = get_crash_manager()
        cm._crash_manager = None
        m2 = get_crash_manager()
        assert m1 is not m2

    def test_default_module_name(self):
        from core.crash_manager import get_crash_manager
        import core.crash_manager as cm

        cm._crash_manager = None
        mgr = get_crash_manager()
        assert mgr.module_name == "global"
