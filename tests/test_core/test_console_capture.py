import pytest


@pytest.fixture(autouse=True)
def _reset_console_capture():
    import core.api.services.console_capture as cc

    saved_single = cc._console_capture
    saved_dict = dict(cc._captures)
    cc._console_capture = None
    cc._captures.clear()
    yield
    cc._console_capture = saved_single
    cc._captures.update(saved_dict)


class TestConsoleCapture:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, tmp_path):
        from core.api.services.console_capture import ConsoleCapture

        cap = ConsoleCapture("instance_1", tmp_path)
        assert cap._task is None
        await cap.start()
        assert cap._task is not None
        assert cap._running is True
        await cap.stop()

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self, tmp_path):
        from core.api.services.console_capture import ConsoleCapture

        cap = ConsoleCapture("test", tmp_path)
        await cap.start()
        t = cap._task
        await cap.start()
        assert cap._task is t
        await cap.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, tmp_path):
        from core.api.services.console_capture import ConsoleCapture

        cap = ConsoleCapture("test", tmp_path)
        await cap.start()
        assert cap._running is True
        await cap.stop()
        assert cap._running is False
        assert cap._task is None

    @pytest.mark.asyncio
    async def test_stop_without_start(self, tmp_path):
        from core.api.services.console_capture import ConsoleCapture

        cap = ConsoleCapture("test", tmp_path)
        await cap.stop()

    @pytest.mark.asyncio
    async def test_get_inode_returns_zero_on_error(self, tmp_path):
        from core.api.services.console_capture import ConsoleCapture

        cap = ConsoleCapture("test", tmp_path)
        inode = cap._get_inode()
        assert inode == 0

    @pytest.mark.asyncio
    async def test_get_inode_with_file(self, tmp_path):
        from core.api.services.console_capture import ConsoleCapture

        log_file = tmp_path / "logs" / "latest.log"
        log_file.parent.mkdir()
        log_file.write_text("test", encoding="utf-8")
        cap = ConsoleCapture("test", tmp_path)
        inode = cap._get_inode()
        assert isinstance(inode, int)


class TestConsoleCaptureManager:
    def test_init_console_capture(self, tmp_path):
        from core.api.services.console_capture import init_console_capture

        cap = init_console_capture(tmp_path)
        assert cap is not None
        assert cap.instance_id == "default"

    def test_get_console_capture_none(self):
        from core.api.services.console_capture import get_console_capture

        cap = get_console_capture()
        assert cap is None

    def test_get_instance_capture_none(self):
        from core.api.services.console_capture import get_instance_capture

        cap = get_instance_capture("nonexistent")
        assert cap is None

    def test_start_stop_instance_capture(self, tmp_path):
        from core.api.services.console_capture import (
            get_instance_capture,
            start_instance_capture,
            stop_instance_capture,
        )

        cap = start_instance_capture("svr_1", tmp_path)
        assert cap is not None
        assert get_instance_capture("svr_1") is cap
        stop_instance_capture("svr_1")
        assert get_instance_capture("svr_1") is None
