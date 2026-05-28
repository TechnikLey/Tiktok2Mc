import pytest


class TestEventBus:
    # ------------------------------------------------------------------
    # Subscribe / publish basic
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_subscribe_all_receives_all_events(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe()
        await bus.publish("test.a", {"n": 1})
        msg = await q.get()
        assert msg["type"] == "test.a"
        assert msg["data"] == {"n": 1}
        assert "timestamp" in msg

    @pytest.mark.asyncio
    async def test_subscribe_filtered(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe("log", "status")
        await bus.publish("log", {"msg": "hi"})
        await bus.publish("other", {"x": 1})
        msg = await q.get()
        assert msg["type"] == "log"

    @pytest.mark.asyncio
    async def test_filtered_does_not_receive_other(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe("log")
        await bus.publish("other", {"x": 1})
        import asyncio

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(q.get(), timeout=0.05)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_type(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q1 = bus.subscribe("ev")
        q2 = bus.subscribe("ev")
        await bus.publish("ev", {})
        r1 = await q1.get()
        r2 = await q2.get()
        assert r1["type"] == "ev"
        assert r2["type"] == "ev"

    @pytest.mark.asyncio
    async def test_all_subscriber_receives_everything(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe()
        await bus.publish("any.type", {"v": 1})
        await bus.publish("another.type", {"v": 2})
        r1 = await q.get()
        r2 = await q.get()
        types = {r1["type"], r2["type"]}
        assert types == {"any.type", "another.type"}

    # ------------------------------------------------------------------
    # Unsubscribe
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        await bus.publish("x", {})
        import asyncio

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(q.get(), timeout=0.05)

    @pytest.mark.asyncio
    async def test_unsubscribe_twice_is_safe(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.unsubscribe(q)  # should not raise

    @pytest.mark.asyncio
    async def test_unsubscribe_does_not_affect_other(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        bus.unsubscribe(q1)
        await bus.publish("y", {})
        r2 = await q2.get()
        assert r2["type"] == "y"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_queue_full_drops_event(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe()
        # Fill the queue (maxsize=2000)
        for i in range(2000):
            await q.put({"i": i})
        # Next publish should drop (queue full) — should not raise
        await bus.publish("dropped", {})
        assert q.qsize() == 2000

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        # Should not raise
        await bus.publish("orphan", {})

    @pytest.mark.asyncio
    async def test_subscribe_multiple_types(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe("a", "b", "c")
        await bus.publish("a", {})
        await bus.publish("c", {})
        r1 = await q.get()
        r2 = await q.get()
        assert r1["type"] in ("a", "c")
        assert r2["type"] in ("a", "c")
        assert r1["type"] != r2["type"]

    @pytest.mark.asyncio
    async def test_timestamp_increases(self):
        from core.api.eventbus import EventBus

        bus = EventBus()
        q = bus.subscribe()
        await bus.publish("t1", {})
        await bus.publish("t2", {})
        r1 = await q.get()
        r2 = await q.get()
        assert r1["timestamp"] <= r2["timestamp"]

    # ------------------------------------------------------------------
    # Integration with event_singleton
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_module_singleton_works(self):
        from core.api.eventbus import event_bus

        q = event_bus.subscribe("singleton.test")
        await event_bus.publish("singleton.test", {"ok": True})
        msg = await q.get()
        assert msg["type"] == "singleton.test"
        assert msg["data"] == {"ok": True}
