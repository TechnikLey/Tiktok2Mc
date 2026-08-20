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

    def test_foreign_origin_is_rejected(self):
        """Cross-origin requests must be rejected, not just served without CORS headers."""
        with TestClient(self._app()) as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={
                    "Origin": "https://evil.example",
                    "Host": "127.0.0.1:29185",
                    "X-API-Key": "secret123",
                },
            )
        assert resp.status_code == 403
        assert "access-control-allow-origin" not in resp.headers

    def test_foreign_origin_post_is_rejected(self):
        """Drive-by CSRF via no-cors POST must not reach the route."""
        with TestClient(self._app()) as tc:
            resp = tc.post(
                "/api/v1/rcon/command",
                headers={
                    "Origin": "https://evil.example",
                    "Host": "127.0.0.1:29185",
                    "X-API-Key": "secret123",
                },
                json={"command": "say hi"},
            )
        assert resp.status_code == 403

    def test_cross_site_fetch_site_is_rejected(self):
        """Sec-Fetch-Site: cross-site must be rejected even without Origin."""
        with TestClient(self._app()) as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={
                    "Host": "127.0.0.1:29185",
                    "Sec-Fetch-Site": "cross-site",
                    "X-API-Key": "secret123",
                },
            )
        assert resp.status_code == 403

    def test_same_site_fetch_site_is_allowed(self):
        with TestClient(self._app()) as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={
                    "Host": "127.0.0.1:29185",
                    "Sec-Fetch-Site": "same-origin",
                    "X-API-Key": "secret123",
                },
            )
        assert resp.status_code == 200

    def test_requests_without_origin_pass(self):
        """Non-browser clients (bridge, plugins, curl) send no Origin."""
        with TestClient(self._app()) as tc:
            resp = tc.get("/api/v1/health", headers={"X-API-Key": "secret123"})
        assert resp.status_code == 200

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


class TestDnsRebindingGuard:
    def _client(self):
        from core.api import create_app

        # Simulate a browser connecting from localhost (rebinding scenario).
        return TestClient(create_app(api_key="secret123"), client=("127.0.0.1", 51234))

    def test_localhost_client_with_foreign_host_is_rejected(self):
        with self._client() as tc:
            resp = tc.get("/api/v1/health", headers={"Host": "evil.example:29185"})
        assert resp.status_code == 403

    def test_localhost_client_with_ip_host_is_allowed(self):
        with self._client() as tc:
            resp = tc.get("/api/v1/health", headers={"Host": "192.168.1.50:29185"})
        assert resp.status_code == 200

    def test_localhost_client_with_loopback_host_is_allowed(self):
        with self._client() as tc:
            resp = tc.get("/api/v1/health", headers={"Host": "localhost:29185"})
        assert resp.status_code == 200

    def test_remote_client_with_foreign_host_is_allowed(self):
        """LAN clients may use the server machine's hostname; api_key governs them."""
        from core.api import create_app

        client = TestClient(
            create_app(api_key="secret123"), client=("192.168.1.77", 51234)
        )
        with client as tc:
            resp = tc.get(
                "/api/v1/health",
                headers={"Host": "server-pc:29185", "X-API-Key": "secret123"},
            )
        assert resp.status_code == 200
