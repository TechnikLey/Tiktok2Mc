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
        hints=["sudo apt install -y openjdk-25-jre-headless"],
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
        # "install" key only present when install_id is provided and install in progress
        assert "install" not in body  # no install_id provided

    def test_status_with_install_id(self, client):
        import uuid

        install_id = uuid.uuid4().hex[:8]
        resp = client.get(f"/api/v1/server/java/status?install_id={install_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        assert "install" not in body  # unknown install_id

    def test_install_already_installed(self, client, monkeypatch):
        monkeypatch.setattr(
            server_lifecycle, "detect_java", lambda *a, **k: _status(True)
        )
        resp = client.post("/api/v1/server/java/install")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_installed"

    def test_install_in_progress(self, client, monkeypatch):
        monkeypatch.setattr(
            server_lifecycle, "detect_java", lambda *a, **k: _status(False)
        )
        install_id = "test123"
        server_lifecycle._JAVA_INSTALL[install_id] = {
            "installing": True,
            "message": "test",
            "done": False,
            "ok": False,
        }
        try:
            resp = client.post("/api/v1/server/java/install")
            assert resp.status_code == 200
            assert resp.json()["status"] == "in_progress"
        finally:
            server_lifecycle._JAVA_INSTALL.pop(install_id, None)

    def test_install_not_auto_installable(self, client, monkeypatch):
        st = _status(False)
        st.auto_installable = False
        monkeypatch.setattr(server_lifecycle, "detect_java", lambda *a, **k: st)
        resp = client.post("/api/v1/server/java/install")
        assert resp.status_code == 400


class TestStartPrefight:
    def test_start_blocked_without_java(self, client, monkeypatch):
        monkeypatch.setattr(
            server_lifecycle, "detect_java", lambda *a, **k: _status(False)
        )
        resp = client.post("/api/v1/server/start")
        assert resp.status_code == 400
        assert "Java" in resp.json()["detail"]

    def test_start_proceeds_with_java(self, client, monkeypatch):
        monkeypatch.setattr(
            server_lifecycle, "detect_java", lambda *a, **k: _status(True)
        )
        resp = client.post("/api/v1/server/start")
        # Pre-flight passed; the default server is not registered in the test
        # app, so the supervisor reports 404 instead of starting a server.
        assert resp.status_code == 404


class TestReadInstanceLogTail:
    def test_reads_latest_log(self, tmp_path):
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "latest.log").write_text(
            'Loading...\nDone (5.4s)! For help, type "help"\n',
            encoding="utf-8",
        )
        tail = server_lifecycle._read_instance_log_tail(tmp_path)
        assert "Done (5.4s)!" in tail

    def test_falls_back_to_debug_log(self, tmp_path):
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "debug.log").write_text(
            "some debug output\n", encoding="utf-8"
        )
        tail = server_lifecycle._read_instance_log_tail(tmp_path)
        assert "some debug output" in tail

    def test_returns_empty_when_no_log(self, tmp_path):
        assert server_lifecycle._read_instance_log_tail(tmp_path) == ""

    def test_limits_to_last_lines(self, tmp_path):
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "latest.log").write_text(
            "\n".join(f"line {i}" for i in range(60)),
            encoding="utf-8",
        )
        tail = server_lifecycle._read_instance_log_tail(tmp_path, max_lines=10)
        assert tail.count("line ") == 10
        assert "line 59" in tail
