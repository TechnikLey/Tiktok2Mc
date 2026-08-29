"""Tests for ``GET /api/v1/updates/check``."""

import json


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

    def test_current_version_matches_tool_version(self, client):
        from core.version import TOOL_VERSION

        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        assert resp.json()["current_version"] == TOOL_VERSION.lstrip("v")

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

        from core.version import TOOL_VERSION

        same = TOOL_VERSION.lstrip("v")

        def fake_urlopen(req, **_kw):
            data = {
                "tag_name": f"v{same}",
                "html_url": f"https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v{same}",
                "published_at": "2026-05-28T00:00:00Z",
            }
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client.get("/api/v1/updates/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["update_available"] is False
        assert body["latest_version"] == same
        assert body["current_version"] == same

    def test_check_tool_update_accepts_v_prefix(self, monkeypatch):
        import urllib.request

        from core.api.updater import check_tool_update

        def fake_urlopen(req, **_kw):
            data = {
                "tag_name": "v1.2.3",
                "html_url": "https://github.com/TechnikLey/Tiktok2Mc/releases/tag/v1.2.3",
                "published_at": "2026-07-01T00:00:00Z",
            }
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = check_tool_update("v1.0.0")
        assert result["current_version"] == "1.0.0"
        assert result["update_available"] is True
        assert result["latest_version"] == "1.2.3"

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
        import urllib.request

        from core.api.updater import check_tool_update

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
        import urllib.request

        from core.api.updater import check_tool_update

        def fake_urlopen(req, **_kw):
            raise urllib.error.URLError("network error")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = check_tool_update("1.0.0")
        assert result["error"] is not None
        assert result["update_available"] is False

    def test_check_tool_update_empty_tag(self, monkeypatch):
        import urllib.request

        from core.api.updater import check_tool_update

        def fake_urlopen(req, **_kw):
            data = {"tag_name": ""}
            return _FakeResponse(json.dumps(data).encode("utf-8"))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = check_tool_update("1.0.0")
        assert result["error"] is not None
        assert result["update_available"] is False


class TestToolUpdateResult:
    def test_returns_200_with_empty_structure(self, client, monkeypatch):
        import core.api.updater as updater

        monkeypatch.setattr(updater, "_last_update_result", None)
        resp = client.get("/api/v1/updates/result")
        assert resp.status_code == 200
        body = resp.json()
        assert body["exit_code"] is None
        assert body["ok"] is True
        assert body["message"] is None

    def test_returns_recorded_result(self, client, monkeypatch):
        import core.api.updater as updater

        updater.set_last_update_result(
            13, ok=False, message="Checksum verification failed."
        )
        try:
            resp = client.get("/api/v1/updates/result")
            assert resp.status_code == 200
            body = resp.json()
            assert body["exit_code"] == 13
            assert body["ok"] is False
            assert body["message"] == "Checksum verification failed."
            assert body["timestamp"] is not None
        finally:
            monkeypatch.setattr(updater, "_last_update_result", None)

    def test_set_and_get_roundtrip(self, monkeypatch):
        import core.api.updater as updater

        updater.set_last_update_result(5, ok=True, message="No update needed.")
        try:
            stored = updater.get_last_update_result()
            assert stored is not None
            assert stored["exit_code"] == 5
            assert stored["ok"] is True
            assert stored["message"] == "No update needed."
        finally:
            monkeypatch.setattr(updater, "_last_update_result", None)


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
