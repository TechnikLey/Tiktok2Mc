"""Tests for the generic event ingest endpoint and the reserved event
family enforcement on POST /api/v1/events.

* ``POST /api/v1/events/ingest`` publishes a namespaced event on the bus
  and optionally dispatches an actions.mca trigger in the same call.
* Reserved core families (tiktok.*, minecraft.*) can only be published by
  the trusted bridge (``X-T2M-Source: bridge`` header).
"""

from unittest.mock import MagicMock, patch


class TestReservedEventFamilies:
    def test_inject_rejects_tiktok_without_bridge_header(self, client):
        resp = client.post("/api/v1/events", json={"type": "tiktok.gift", "data": {}})
        assert resp.status_code == 403
        assert "reserved" in resp.json()["detail"].lower()

    def test_inject_rejects_minecraft_without_bridge_header(self, client):
        resp = client.post(
            "/api/v1/events",
            json={"type": "minecraft.player_death", "data": {}},
        )
        assert resp.status_code == 403

    def test_inject_allows_tiktok_with_bridge_header(self, client):
        resp = client.post(
            "/api/v1/events",
            json={"type": "tiktok.gift", "data": {"user": "alice"}},
            headers={"X-T2M-Source": "bridge"},
        )
        assert resp.status_code == 200

    def test_inject_allows_own_namespaces(self, client):
        resp = client.post("/api/v1/events", json={"type": "test.event", "data": {}})
        assert resp.status_code == 200

    def test_ingest_rejects_reserved_family(self, client):
        resp = client.post(
            "/api/v1/events/ingest",
            json={"type": "tiktok.gift", "data": {}},
        )
        assert resp.status_code == 403

    def test_wrong_header_value_is_not_trusted(self, client):
        resp = client.post(
            "/api/v1/events",
            json={"type": "minecraft.chat", "data": {}},
            headers={"X-T2M-Source": "spoofed"},
        )
        assert resp.status_code == 403


class TestIngestEvent:
    def _patch_trigger_service(self, result=None):
        service = MagicMock()
        service.dispatch.return_value = result or {
            "status": "ok",
            "message": "",
            "trigger": "on_death",
            "user": "Notch",
        }
        return patch(
            "core.api.services.trigger_service.get_trigger_service",
            return_value=service,
        )

    def test_ingest_publishes_event(self, client):
        resp = client.post(
            "/api/v1/events/ingest",
            json={"type": "mygame.player_death", "data": {"player": "Notch"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["event"] == "mygame.player_death"
        assert "trigger" not in body

    def test_ingest_requires_type(self, client):
        resp = client.post("/api/v1/events/ingest", json={"data": {}})
        assert resp.status_code == 422

    def test_ingest_requires_namespaced_type(self, client):
        resp = client.post("/api/v1/events/ingest", json={"type": "nodot"})
        assert resp.status_code == 422

    def test_ingest_rejects_non_dict_data(self, client):
        resp = client.post(
            "/api/v1/events/ingest",
            json={"type": "mygame.event", "data": [1, 2]},
        )
        assert resp.status_code == 422

    def test_ingest_dispatches_trigger(self, client):
        with self._patch_trigger_service() as mocked_getter:
            resp = client.post(
                "/api/v1/events/ingest",
                json={
                    "type": "mygame.player_death",
                    "data": {"player": "Notch"},
                    "trigger": "on_death",
                    "user": "Notch",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["trigger"]["status"] == "ok"
        service = mocked_getter.return_value
        service.dispatch.assert_called_once()
        kwargs = service.dispatch.call_args.kwargs
        assert kwargs["trigger"] == "on_death"
        assert kwargs["user"] == "Notch"

    def test_ingest_user_falls_back_to_data(self, client):
        with self._patch_trigger_service() as mocked_getter:
            resp = client.post(
                "/api/v1/events/ingest",
                json={
                    "type": "mygame.level_up",
                    "data": {"user": "Alice"},
                    "trigger": "levelup",
                },
            )
        assert resp.status_code == 200
        kwargs = mocked_getter.return_value.dispatch.call_args.kwargs
        assert kwargs["user"] == "Alice"

    def test_ingest_gift_fields_forwarded(self, client):
        with self._patch_trigger_service() as mocked_getter:
            resp = client.post(
                "/api/v1/events/ingest",
                json={
                    "type": "external.simulation",
                    "gift_id": "555",
                    "gift_name": "Rose",
                    "trigger": "gift",
                },
            )
        assert resp.status_code == 200
        kwargs = mocked_getter.return_value.dispatch.call_args.kwargs
        assert kwargs["gift_id"] == "555"
        assert kwargs["gift_name"] == "Rose"

    def test_ingest_invalid_trigger_type_ignored(self, client):
        # A non-string trigger must not crash; only the publish happens.
        resp = client.post(
            "/api/v1/events/ingest",
            json={"type": "mygame.thing", "trigger": 42},
        )
        assert resp.status_code == 200
        assert "trigger" not in resp.json()

    def test_ingest_rejects_non_string_type(self, client):
        resp = client.post("/api/v1/events/ingest", json={"type": 42})
        assert resp.status_code == 422
