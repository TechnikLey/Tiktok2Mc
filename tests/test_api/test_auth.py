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
