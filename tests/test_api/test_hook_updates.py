"""Tests for the hook update endpoints (/api/v1/hooks/updates*)."""

import pytest


@pytest.fixture(autouse=True)
def _clear_hook_registry():
    from core.hook_registry import get_hook_registry

    reg = get_hook_registry()
    for h in reg.list():
        reg.unregister(h.name)
    yield
    reg = get_hook_registry()
    for h in reg.list():
        reg.unregister(h.name)


class _StubChecker:
    """Replaces PackageUpdateChecker to avoid network access."""

    def __init__(self, results=None):
        self.results = results or []

    def check_updates(self, pkgs):
        return [
            dict(r) for r in self.results if r.get("name") in {p["name"] for p in pkgs}
        ]

    def install_update(self, pkg, base_dir):  # pragma: no cover - stubbed away
        return False


def _available_result(name="remote"):
    return {
        "name": name,
        "display_name": name.title(),
        "current_version": "1.0.0",
        "latest_version": "2.0.0",
        "update_available": True,
        "update_url": "https://example.com/x",
        "checked_at": 0.0,
        "error": None,
    }


class TestHookUpdatesEndpoint:
    def test_returns_200_when_empty(self, client):
        resp = client.get("/api/v1/hooks/updates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["hooks"] == []
        assert body["total"] == 0
        assert body["updates_available"] == 0

    def test_skips_hooks_without_update_url(self, client):
        from core.hook_registry import HookRegistration, get_hook_registry

        get_hook_registry().register(HookRegistration(name="plain", version="1.0.0"))
        resp = client.get("/api/v1/hooks/updates")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_reports_hook_with_update_url(self, client, monkeypatch):
        from core.api.routes import hooks as hooks_mod
        from core.hook_registry import HookRegistration, get_hook_registry

        get_hook_registry().register(
            HookRegistration(
                name="remote", version="1.0.0", update_url="https://example.com/x"
            )
        )
        monkeypatch.setattr(
            hooks_mod, "_hook_updater", _StubChecker([_available_result()])
        )

        resp = client.get("/api/v1/hooks/updates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["updates_available"] == 1
        assert body["hooks"][0]["name"] == "remote"


class TestHookUpdatesInstall:
    def test_refuses_non_standalone_hook(self, client, monkeypatch, project_dir):
        """A hook without its own directory in the main hooks dir is skipped."""
        from core.api.routes import hooks as hooks_mod
        from core.hook_registry import HookRegistration, get_hook_registry

        (project_dir / "src" / "hooks").mkdir(parents=True, exist_ok=True)
        get_hook_registry().register(
            HookRegistration(
                name="pluginbundled",
                version="1.0.0",
                plugin="some-plugin",
                update_url="https://example.com/x",
            )
        )
        monkeypatch.setattr(
            hooks_mod,
            "_hook_updater",
            _StubChecker([_available_result("pluginbundled")]),
        )

        resp = client.post("/api/v1/hooks/updates/install", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["installed"] == 0
        assert body["failed"] == 1
        result = body["results"][0]
        assert result["success"] is False
        assert "Not a standalone hook" in result["error"]

    def test_no_updates_is_noop(self, client, monkeypatch, project_dir):
        from core.api.routes import hooks as hooks_mod
        from core.hook_registry import HookRegistration, get_hook_registry

        (project_dir / "src" / "hooks").mkdir(parents=True, exist_ok=True)
        get_hook_registry().register(HookRegistration(name="quiet", version="1.0.0"))
        monkeypatch.setattr(hooks_mod, "_hook_updater", _StubChecker())

        resp = client.post("/api/v1/hooks/updates/install", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"results": [], "installed": 0, "failed": 0}

    def test_missing_hooks_dir_returns_500(self, client, monkeypatch, project_dir):
        """Without any hooks directory the install cannot proceed."""
        import shutil

        # Ensure neither layout variant exists.
        shutil.rmtree(project_dir / "src" / "hooks", ignore_errors=True)
        shutil.rmtree(project_dir / "hooks", ignore_errors=True)

        resp = client.post("/api/v1/hooks/updates/install", json={})
        assert resp.status_code == 500
