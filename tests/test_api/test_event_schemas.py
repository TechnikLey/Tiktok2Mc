"""Tests for the versioned event payload contract (data_schema).

Plugins declare ``data_schema`` (+ ``version``) per emitted event in
plugin.json. Publishing a declared event type with missing required keys
or mistyped values is rejected with ``422 API-0010`` on POST /events and
POST /events/ingest; undeclared event types pass through unvalidated.
"""

import json

import pytest

from core.api.services.reaction_catalog import (
    invalidate_event_schema_cache,
    validate_event_payload,
)

SCHEMA_MANIFEST = {
    "name": "schemademo",
    "version": "1.0.0",
    "entry_point": "src/plugins/schemademo/main.py",
    "display_name": "Schema Demo",
    "permissions": ["events"],
    "emitted_events": [
        {
            "key": "schemademo.scored",
            "name": "Scored",
            "desc": "A player scored",
            "version": 2,
            "data_schema": [
                {"key": "player", "type": "string", "required": True},
                {"key": "points", "type": "number", "required": True},
                {"key": "combo", "type": "boolean"},
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_event_schema_cache()
    yield
    invalidate_event_schema_cache()


@pytest.fixture
def schema_plugin(project_dir):
    plugins_dir = project_dir / "src" / "plugins"
    plugin_dir = plugins_dir / "schemademo"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps(SCHEMA_MANIFEST), encoding="utf-8"
    )
    return plugins_dir


class TestValidateEventPayload:
    def test_missing_required_key(self, schema_plugin):
        violations = validate_event_payload(
            "schemademo.scored", {"player": "Notch"}, plugins_dir=schema_plugin
        )
        assert any("points" in v for v in violations)

    def test_valid_payload_passes(self, schema_plugin):
        assert (
            validate_event_payload(
                "schemademo.scored",
                {"player": "Notch", "points": 5, "combo": True},
                plugins_dir=schema_plugin,
            )
            == []
        )

    def test_wrong_type_rejected(self, schema_plugin):
        violations = validate_event_payload(
            "schemademo.scored",
            {"player": "Notch", "points": "many"},
            plugins_dir=schema_plugin,
        )
        assert any("'points' must be number" in v for v in violations)

    def test_bool_is_not_number(self, schema_plugin):
        violations = validate_event_payload(
            "schemademo.scored",
            {"player": "Notch", "points": True},
            plugins_dir=schema_plugin,
        )
        assert any("'points' must be number (got bool)" in v for v in violations)

    def test_extra_keys_allowed(self, schema_plugin):
        result = validate_event_payload(
            "schemademo.scored",
            {"player": "x", "points": 1, "extra": [1]},
            plugins_dir=schema_plugin,
        )
        assert result == []

    def test_undeclared_event_passes_through(self, schema_plugin):
        assert (
            validate_event_payload(
                "totally.unknown", {"anything": 1}, plugins_dir=schema_plugin
            )
            == []
        )

    def test_optional_keys_may_be_absent(self, schema_plugin):
        assert (
            validate_event_payload(
                "schemademo.scored",
                {"player": "x", "points": 1},
                plugins_dir=schema_plugin,
            )
            == []
        )


class TestSchemaEnforcementRoutes:
    def test_inject_rejects_schema_violation(self, client, schema_plugin):
        resp = client.post(
            "/api/v1/events", json={"type": "schemademo.scored", "data": {}}
        )
        assert resp.status_code == 422
        assert "API-0010" in resp.json()["detail"]

    def test_ingest_rejects_schema_violation(self, client, schema_plugin):
        resp = client.post(
            "/api/v1/events/ingest",
            json={"type": "schemademo.scored", "data": {"player": "x"}},
        )
        assert resp.status_code == 422

    def test_ingest_accepts_valid_payload(self, client, schema_plugin):
        resp = client.post(
            "/api/v1/events/ingest",
            json={
                "type": "schemademo.scored",
                "data": {"player": "x", "points": 3},
            },
        )
        assert resp.status_code == 200

    def test_catalog_exposes_version_and_schema(self, client, schema_plugin):
        resp = client.get("/api/v1/reactions/catalog")
        assert resp.status_code == 200
        events = resp.json()["events"]
        entry = events["schemademo.scored"]
        assert entry["version"] == 2
        keys = {f["key"] for f in entry["data_schema"]}
        assert {"player", "points", "combo"} <= keys
