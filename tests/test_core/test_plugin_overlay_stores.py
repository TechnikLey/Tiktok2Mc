import threading
import asyncio
import pytest


class TestPluginStateStore:
    def test_set_and_get_state(self):
        from core.api.plugin_overlay import PluginStateStore

        store = PluginStateStore()
        store.set_state("plugin_a", {"score": 100, "alive": True})
        state = store.get_state("plugin_a")
        assert state is not None
        assert state["score"] == 100

    def test_get_missing_plugin(self):
        from core.api.plugin_overlay import PluginStateStore

        store = PluginStateStore()
        assert store.get_state("nonexistent") is None

    def test_clear_state(self):
        from core.api.plugin_overlay import PluginStateStore

        store = PluginStateStore()
        store.set_state("p", {"k": "v"})
        store.clear("p")
        assert store.get_state("p") is None

    def test_clear_nonexistent(self):
        from core.api.plugin_overlay import PluginStateStore

        store = PluginStateStore()
        store.clear("nope")

    def test_overwrite_state(self):
        from core.api.plugin_overlay import PluginStateStore

        store = PluginStateStore()
        store.set_state("p", {"v": 1})
        store.set_state("p", {"v": 2})
        assert store.get_state("p")["v"] == 2

    def test_thread_safety(self):
        from core.api.plugin_overlay import PluginStateStore

        store = PluginStateStore()
        errors = []

        def writer():
            try:
                for i in range(100):
                    store.set_state(f"p{i}", {"n": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestCommandQueue:
    def test_enqueue_and_dequeue_all(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        cmd_id = q.enqueue("plugin_a", "do_something", arg1=42)
        assert cmd_id is not None
        cmds = q.dequeue_all("plugin_a")
        assert len(cmds) == 1
        assert cmds[0]["command"] == "do_something"
        assert cmds[0]["args"] == {"arg1": 42}

    def test_dequeue_empty_returns_empty_list(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        cmds = q.dequeue_all("nonexistent")
        assert cmds == []

    def test_multiple_commands(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        q.enqueue("p", "cmd1")
        q.enqueue("p", "cmd2")
        cmds = q.dequeue_all("p")
        assert len(cmds) == 2

    def test_clear_queue(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        q.enqueue("p", "cmd")
        q.clear("p")
        cmds = q.dequeue_all("p")
        assert cmds == []

    def test_clear_nonexistent(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        q.clear("nope")

    def test_enqueue_notifies_event(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        loop = asyncio.new_event_loop()
        q.set_loop(loop)
        q.enqueue("p", "cmd")
        cmds = q.dequeue_all("p")
        assert len(cmds) == 1

    @pytest.mark.asyncio
    async def test_wait_for_commands_returns_immediately_when_pending(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        q.enqueue("p", "cmd")
        await q.wait_for_commands("p", timeout=0.5)
        cmds = q.dequeue_all("p")
        assert len(cmds) == 1

    @pytest.mark.asyncio
    async def test_wait_for_commands_timeout(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        with pytest.raises(asyncio.TimeoutError):
            await q.wait_for_commands("p", timeout=0.05)

    @pytest.mark.asyncio
    async def test_wait_for_commands_triggered_by_enqueue(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        loop = asyncio.get_running_loop()
        q.set_loop(loop)

        async def delayed_enqueue():
            await asyncio.sleep(0.05)
            q.enqueue("p", "cmd")

        asyncio.create_task(delayed_enqueue())
        await q.wait_for_commands("p", timeout=2.0)
        cmds = q.dequeue_all("p")
        assert len(cmds) == 1

    def test_thread_safety(self):
        from core.api.plugin_overlay import CommandQueue

        q = CommandQueue()
        errors = []

        def writer():
            try:
                for i in range(50):
                    q.enqueue("shared", f"cmd{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        cmds = q.dequeue_all("shared")
        assert len(cmds) == 200


class TestOverlayHtmlStore:
    def test_set_and_get_html(self):
        from core.api.plugin_overlay import OverlayHtmlStore

        store = OverlayHtmlStore()
        store.set_html("plugin_a", "<h1>Hello</h1>")
        html = store.get_html("plugin_a")
        assert html == "<h1>Hello</h1>"

    def test_get_missing(self):
        from core.api.plugin_overlay import OverlayHtmlStore

        store = OverlayHtmlStore()
        assert store.get_html("nonexistent") is None

    def test_clear(self):
        from core.api.plugin_overlay import OverlayHtmlStore

        store = OverlayHtmlStore()
        store.set_html("p", "<h1>Hi</h1>")
        store.clear("p")
        assert store.get_html("p") is None

    def test_clear_nonexistent(self):
        from core.api.plugin_overlay import OverlayHtmlStore

        store = OverlayHtmlStore()
        store.clear("nope")

    def test_overwrite(self):
        from core.api.plugin_overlay import OverlayHtmlStore

        store = OverlayHtmlStore()
        store.set_html("p", "<h1>A</h1>")
        store.set_html("p", "<h1>B</h1>")
        assert store.get_html("p") == "<h1>B</h1>"
