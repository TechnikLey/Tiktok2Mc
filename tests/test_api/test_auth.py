"""Tests for API key authentication middleware."""

from fastapi.testclient import TestClient


def test_no_auth_when_api_key_empty():
    from core.api import create_app

    app = create_app(api_key="")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health")
    assert resp.status_code == 200


def test_auth_blocks_missing_key():
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health")
    assert resp.status_code == 401


def test_auth_blocks_wrong_key():
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_auth_allows_correct_key():
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200


def test_auth_localhost_bypass():
    """Verify the middleware marks localhost as allowed."""
    from core.api.server import _LOCALHOSTS

    assert "127.0.0.1" in _LOCALHOSTS
    assert "localhost" in _LOCALHOSTS
    assert "::1" in _LOCALHOSTS


def test_auth_allows_correct_key_via_query_param():
    """SSE (EventSource) cannot set headers, so ?key= must also work."""
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health?key=secret123")
    assert resp.status_code == 200


def test_auth_rejects_wrong_key_via_query_param():
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health?key=wrong")
    assert resp.status_code == 401


def test_auth_header_takes_precedence_over_query_param():
    """A bad ?key= must not grant access when a valid header is present."""
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/health?key=wrong", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200


def test_auth_allows_preflight_options_without_key():
    """CORS preflights carry no API key; they must pass the auth middleware."""
    from core.api import create_app

    app = create_app(api_key="secret123")
    with TestClient(app) as tc:
        resp = tc.options(
            "/api/v1/health",
            headers={
                "Origin": "http://192.168.1.50:29185",
                "Host": "192.168.1.50:29185",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200


class TestSameHostCORS:
    def _app(self):
        from core.api import create_app

        return create_app(api_key="secret123")

    def test_same_host_origin_is_reflected(self):
        with TestClient(self._app()) as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={
                    "Origin": "http://192.168.1.50:29185",
                    "Host": "192.168.1.50:29185",
                    "X-API-Key": "secret123",
                },
            )
        assert resp.status_code == 200
        assert (
            resp.headers.get("access-control-allow-origin")
            == "http://192.168.1.50:29185"
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_foreign_origin_gets_no_cors_headers(self):
        with TestClient(self._app()) as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={
                    "Origin": "https://evil.example",
                    "Host": "127.0.0.1:29185",
                    "X-API-Key": "secret123",
                },
            )
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers

    def test_preflight_reflects_same_host_origin(self):
        with TestClient(self._app()) as tc:
            resp = tc.options(
                "/api/v1/health",
                headers={
                    "Origin": "http://192.168.1.50:29185",
                    "Host": "192.168.1.50:29185",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "x-api-key,content-type",
                },
            )
        assert resp.status_code == 200
        assert (
            resp.headers.get("access-control-allow-origin")
            == "http://192.168.1.50:29185"
        )
        assert "GET" in resp.headers.get("access-control-allow-methods", "")
        assert (
            "x-api-key" in resp.headers.get("access-control-allow-headers", "").lower()
        )

    def test_localhost_origin_always_allowed(self):
        with TestClient(self._app()) as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={
                    "Origin": "http://127.0.0.1:29185",
                    "Host": "127.0.0.1:29185",
                    "X-API-Key": "secret123",
                },
            )
        assert resp.status_code == 200
        assert (
            resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:29185"
        )
