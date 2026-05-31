"""Tests for restart/shutdown/cancel system endpoints."""

import json
from pathlib import Path
import pytest


class TestRestart:
    def test_restart_writes_signal_file(self, client, project_dir):
        resp = client.post("/api/v1/restart")
        assert resp.status_code == 200
        assert resp.json() == {"status": "restart_requested"}
        assert (project_dir / "core" / "runtime" / "restart").exists()


class TestShutdown:
    def test_shutdown_writes_signal_file(self, client, project_dir):
        resp = client.post("/api/v1/shutdown")
        assert resp.status_code == 200
        assert resp.json() == {"status": "shutdown_requested"}
        assert (project_dir / "core" / "runtime" / "shutdown").exists()

    def test_shutdown_now_writes_signal_file(self, client, project_dir):
        resp = client.post("/api/v1/shutdown/now")
        assert resp.status_code == 200
        assert resp.json() == {"status": "shutdown_now"}
        assert (project_dir / "core" / "runtime" / "shutdown_now").exists()

    def test_shutdown_cancel_writes_signal_file(self, client, project_dir):
        resp = client.post("/api/v1/shutdown/cancel")
        assert resp.status_code == 200
        assert resp.json() == {"status": "cancel_requested"}
        assert (project_dir / "core" / "runtime" / "shutdown_cancel").exists()


class TestShutdownStatus:
    def test_shutdown_status_idle_when_no_file(self, client):
        resp = client.get("/api/v1/shutdown/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "shutdown_pending": False,
            "remaining_seconds": None,
            "state": "idle",
        }

    def test_shutdown_status_returns_file_content(self, client, project_dir):
        runtime_dir = project_dir / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_file = runtime_dir / "shutdown_status"
        status_file.write_text(
            json.dumps({"remaining": 10, "state": "counting_down"}),
            encoding="utf-8",
        )
        try:
            resp = client.get("/api/v1/shutdown/status")
            assert resp.status_code == 200
            assert resp.json() == {
                "shutdown_pending": True,
                "remaining_seconds": 10,
                "state": "counting_down",
            }
        finally:
            status_file.unlink(missing_ok=True)

    def test_shutdown_status_handles_corrupt_json_gracefully(
        self, client, project_dir
    ):
        runtime_dir = project_dir / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_file = runtime_dir / "shutdown_status"
        status_file.write_text("not valid json", encoding="utf-8")
        try:
            resp = client.get("/api/v1/shutdown/status")
            assert resp.status_code == 200
            assert resp.json() == {
                "shutdown_pending": False,
                "remaining_seconds": None,
                "state": "idle",
            }
        finally:
            status_file.unlink(missing_ok=True)

    def test_shutdown_status_handles_read_error_gracefully(
        self, client, project_dir, monkeypatch
    ):
        runtime_dir = project_dir / "core" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_file = runtime_dir / "shutdown_status"
        status_file.write_text("{}", encoding="utf-8")

        def _broken_read(*args, **kwargs):
            raise PermissionError("access denied")

        monkeypatch.setattr(Path, "read_text", _broken_read)
        try:
            resp = client.get("/api/v1/shutdown/status")
            assert resp.status_code == 200
            assert resp.json() == {
                "shutdown_pending": False,
                "remaining_seconds": None,
                "state": "idle",
            }
        finally:
            status_file.unlink(missing_ok=True)
