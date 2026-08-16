"""Tests for the config bundle export/import feature.

The bundle is a ZIP of the active config files (config.yaml, actions.mca,
event_commands.yaml, plugin/hook configs) plus a ``bundle.json`` manifest.
"""

import io
import json
import zipfile

MINIMAL_ACTIONS = "# test actions\nfollow:/say hi\n"


def _make_bundle(files: dict[str, str], manifest: bool = True) -> bytes:
    """Build a ZIP bundle from ``{bundle_name: content}``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if manifest:
            zf.writestr(
                "bundle.json",
                json.dumps(
                    {
                        "format_version": 1,
                        "tool_version": "v1.0.0",
                        "config_version": "1.0",
                        "created": "2026-08-17T00:00:00+00:00",
                        "files": sorted(files.keys()),
                    }
                ),
            )
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _seed_project(project_dir, plugin_name="testplugin", hook_name="demohook"):
    """Create the config files the bundle feature collects."""
    cfg_file = project_dir / "config.yaml"
    cfg_file.write_text(
        'config_version: "1.0"\nserver_host: "127.0.0.1"\n', encoding="utf-8"
    )
    (project_dir / "data" / "actions.mca").write_text(MINIMAL_ACTIONS, encoding="utf-8")
    (project_dir / "data" / "event_commands.yaml").write_text(
        'event_commands:\n  ping: "say pong"\n', encoding="utf-8"
    )
    plugin_cfg = project_dir / "src" / "plugins" / plugin_name / "config.yaml"
    plugin_cfg.parent.mkdir(parents=True, exist_ok=True)
    plugin_cfg.write_text("enabled: true\n", encoding="utf-8")
    hook_cfg = project_dir / "src" / "hooks" / hook_name / "config.yaml"
    hook_cfg.parent.mkdir(parents=True, exist_ok=True)
    hook_cfg.write_text("enabled: true\n", encoding="utf-8")


def _read_zip(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        return {info.filename: zf.read(info.filename) for info in zf.infolist()}


class TestExport:
    def test_export_bundle_contains_active_files(self, client, project_dir):
        _seed_project(project_dir)
        resp = client.get("/api/v1/config-bundle")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")

        files = _read_zip(resp.content)
        assert "bundle.json" in files
        assert "config/config.yaml" in files
        assert "data/actions.mca" in files
        assert "data/event_commands.yaml" in files
        assert "plugins/testplugin/config.yaml" in files
        assert "hooks/demohook/config.yaml" in files

        manifest = json.loads(files["bundle.json"])
        assert manifest["format_version"] == 1
        assert "config/config.yaml" in manifest["files"]
        assert files["config/config.yaml"].startswith(b"config_version")

    def test_export_skips_defaults_and_absent_optional_files(self, client, project_dir):
        # No data/actions.mca -> defaults templates must NOT be exported
        resp = client.get("/api/v1/config-bundle")
        assert resp.status_code == 200
        files = _read_zip(resp.content)
        assert "config/config.yaml" in files
        assert "data/actions.mca" not in files
        assert "defaults/config.yaml" not in files
        assert "defaults/actions.mca" not in files
        assert "defaults/event_commands.yaml" not in files
        assert all(not k.startswith("plugins/") for k in files)
        assert all(not k.startswith("hooks/") for k in files)


class TestImport:
    def test_import_applies_all_files_with_backup(self, client, project_dir):
        _seed_project(project_dir)
        bundle = _make_bundle(
            {
                "config/config.yaml": (
                    'config_version: "1.0"\nserver_host: "0.0.0.0"\n'
                ),
                "data/actions.mca": "# imported\nlike:/say like\n",
                "data/event_commands.yaml": 'event_commands:\n  hi: "say hi"\n',
                "plugins/testplugin/config.yaml": "enabled: false\n",
                "hooks/demohook/config.yaml": "enabled: false\n",
            }
        )

        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 5
        assert "config/config.yaml" in body["applied"]
        assert "plugins/testplugin/config.yaml" in body["applied"]

        assert (project_dir / "config.yaml").read_text(encoding="utf-8").find(
            "0.0.0.0"
        ) != -1
        assert (project_dir / "data" / "actions.mca").read_text(
            encoding="utf-8"
        ) == "# imported\nlike:/say like\n"
        assert (project_dir / "data" / "event_commands.yaml").read_text(
            encoding="utf-8"
        ).find("hi") != -1
        assert (
            project_dir / "src" / "plugins" / "testplugin" / "config.yaml"
        ).read_text(encoding="utf-8") == "enabled: false\n"
        assert (project_dir / "src" / "hooks" / "demohook" / "config.yaml").read_text(
            encoding="utf-8"
        ) == "enabled: false\n"

    def test_import_creates_safety_backup(self, client, project_dir):
        _seed_project(project_dir)
        before = (project_dir / "config.yaml").read_text(encoding="utf-8")
        bundle = _make_bundle(
            {"config/config.yaml": ('config_version: "1.0"\nserver_host: "9.9.9.9"\n')}
        )
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 200

        backup_dir = project_dir / "data" / "backups" / "config"
        backups = list(backup_dir.glob("*.yaml.bak"))
        assert backups, "expected a safety backup for config.yaml"
        assert any(before in b.read_text(encoding="utf-8") for b in backups)

    def test_import_rejects_non_zip(self, client):
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("x.zip", b"not a zip", "application/zip")},
        )
        assert resp.status_code == 422

    def test_import_rejects_unsupported_file(self, client, project_dir):
        bundle = _make_bundle({"evil/secret.txt": "boom"})
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 422
        assert "Unsupported file" in resp.json()["detail"]

    def test_import_rejects_path_traversal(self, client, project_dir):
        bundle = _make_bundle({"../../config.yaml": "pwned"})
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 422

    def test_import_rejects_invalid_actions(self, client, project_dir):
        bundle = _make_bundle({"data/actions.mca": "no-colon-and-no-command\n"})
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 422
        assert "actions" in resp.json()["detail"]

    def test_import_rejects_invalid_config(self, client, project_dir):
        bundle = _make_bundle({"config/config.yaml": ": broken: ["})
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 422

    def test_import_empty_bundle_422(self, client, project_dir):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("bundle.json", "{}")
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", buffer.getvalue(), "application/zip")},
        )
        assert resp.status_code == 422

    def test_import_roundtrip_export(self, client, project_dir):
        _seed_project(project_dir)
        exported = client.get("/api/v1/config-bundle").content
        # Modify the source files, then re-import the exported bundle
        (project_dir / "config.yaml").write_text(
            'config_version: "1.0"\nserver_host: "8.8.8.8"\n', encoding="utf-8"
        )
        resp = client.post(
            "/api/v1/config-bundle/import",
            files={"file": ("bundle.zip", exported, "application/zip")},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 5
        restored = (project_dir / "config.yaml").read_text(encoding="utf-8")
        assert restored.find("127.0.0.1") != -1
        assert (project_dir / "data" / "actions.mca").read_text(
            encoding="utf-8"
        ) == MINIMAL_ACTIONS
