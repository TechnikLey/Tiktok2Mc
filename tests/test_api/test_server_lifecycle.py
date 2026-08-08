"""Tests for server lifecycle Java pre-flight + status/install endpoints."""


from core import java_utils
from core.api.routes import server_lifecycle


def _status(ok: bool) -> java_utils.JavaStatus:
    if ok:
        return java_utils.JavaStatus(
            ok=True,
            path="/fake/java",
            version="21.0.2",
            source="system",
        )
    return java_utils.JavaStatus(
        ok=False,
        reason="No Java found for the test environment.",
        hints=["sudo apt install -y openjdk-21-jre-headless"],
        auto_installable=True,
    )


class TestJavaStatusEndpoint:
    def test_status_returns_structure(self, client):
        resp = client.get("/api/v1/server/java/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        assert "hints" in body
        assert "minJavaVersion" in body
        assert "install" in body

    def test_install_already_installed(self, client, monkeypatch):
        monkeypatch.setattr(server_lifecycle, "detect_java", lambda *a, **k: _status(True))
        resp = client.post("/api/v1/server/java/install")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_installed"

    def test_install_in_progress(self, client, monkeypatch):
        monkeypatch.setattr(server_lifecycle, "detect_java", lambda *a, **k: _status(False))
        server_lifecycle._JAVA_INSTALL["installing"] = True
        try:
            resp = client.post("/api/v1/server/java/install")
            assert resp.status_code == 200
            assert resp.json()["status"] == "in_progress"
        finally:
            server_lifecycle._JAVA_INSTALL["installing"] = False

    def test_install_not_auto_installable(self, client, monkeypatch):
        st = _status(False)
        st.auto_installable = False
        monkeypatch.setattr(server_lifecycle, "detect_java", lambda *a, **k: st)
        resp = client.post("/api/v1/server/java/install")
        assert resp.status_code == 400


class TestStartPrefight:
    def test_start_blocked_without_java(self, client, monkeypatch):
        monkeypatch.setattr(server_lifecycle, "detect_java", lambda *a, **k: _status(False))
        resp = client.post("/api/v1/server/start")
        assert resp.status_code == 400
        assert "Java" in resp.json()["detail"]

    def test_start_proceeds_with_java(self, client, monkeypatch):
        monkeypatch.setattr(server_lifecycle, "detect_java", lambda *a, **k: _status(True))
        resp = client.post("/api/v1/server/start")
        # Pre-flight passed; the default server is not registered in the test
        # app, so the supervisor reports 404 instead of starting a server.
        assert resp.status_code == 404
