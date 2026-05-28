"""Tests for ``GET /api/v1/updates/check``."""

import json
import pytest


class TestToolUpdateCheck:
    def test_returns_200_with_structure(self, client):
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert "current_version" in body
        assert "update_available" in body
        assert "latest_version" in body
        assert "release_url" in body
        assert "published_at" in body

    def test_current_version_matches_api_version(self, client):
        from core.api.models import API_VERSION

        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        assert resp.json()["current_version"] == API_VERSION

    def test_handles_github_unreachable_gracefully(self, client, monkeypatch):
        import urllib.request

        def fake_urlopen(req, **_kw):
            raise urllib.error.URLError("mock failure")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] is not None
        assert body["latest_version"] is None
        assert body["update_available"] is False

    def test_update_available_when_newer_release(self, client, monkeypatch):
        import urllib.request

        release_data = {
            "tag_name": "v99.99.99",
            "html_url": "https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v99.99.99",
            "published_at": "2026-06-01T00:00:00Z",
        }

        def fake_urlopen(req, **_kw):
            return _FakeResponse(json.dumps(release_data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["update_available"] is True
        assert body["latest_version"] == "99.99.99"
        assert body["release_url"] == release_data["html_url"]

    def test_no_update_when_same_version(self, client, monkeypatch):
        import urllib.request
        from core.api.models import API_VERSION

        def fake_urlopen(req, **_kw):
            data = {
                "tag_name": f"v{API_VERSION}",
                "html_url": f"https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v{API_VERSION}",
                "published_at": "2026-05-28T00:00:00Z",
            }
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["update_available"] is False
        assert body["latest_version"] == API_VERSION

    def test_no_update_when_older_release(self, client, monkeypatch):
        import urllib.request

        def fake_urlopen(req, **_kw):
            data = {
                "tag_name": "v0.9.0",
                "html_url": "https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v0.9.0",
                "published_at": "2026-04-01T00:00:00Z",
            }
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["update_available"] is False
        assert body["latest_version"] == "0.9.0"

    def test_handles_invalid_release_json(self, client, monkeypatch):
        import urllib.request

        def fake_urlopen(req, **_kw):
            return _FakeResponse(b"not json")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] is not None

    def test_direct_call_check_tool_update(self):
        from core.api.updater import check_tool_update

        result = check_tool_update("1.0.0")
        assert "current_version" in result
        assert result["current_version"] == "1.0.0"

    def test_check_tool_update_with_mocked_newer(self, monkeypatch):
        from core.api.updater import check_tool_update
        import urllib.request

        def fake_urlopen(req, **_kw):
            data = {
                "tag_name": "v2.0.0",
                "html_url": "https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v2.0.0",
                "published_at": "2026-07-01T00:00:00Z",
            }
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = check_tool_update("1.0.0")
        assert result["update_available"] is True
        assert result["latest_version"] == "2.0.0"

    def test_check_tool_update_with_mocked_error(self, monkeypatch):
        from core.api.updater import check_tool_update
        import urllib.request

        def fake_urlopen(req, **_kw):
            raise urllib.error.URLError("network error")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = check_tool_update("1.0.0")
        assert result["error"] is not None
        assert result["update_available"] is False

    def test_check_tool_update_empty_tag(self, monkeypatch):
        from core.api.updater import check_tool_update
        import urllib.request

        def fake_urlopen(req, **_kw):
            data = {"tag_name": ""}
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = check_tool_update("1.0.0")
        assert result["error"] is not None
        assert result["update_available"] is False


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
