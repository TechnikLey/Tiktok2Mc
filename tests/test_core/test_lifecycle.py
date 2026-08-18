"""Lifecycle tests: signal file concept, manifest discovery, health check, bridge init."""

import json
from unittest.mock import MagicMock

# =========================================================================
# Signal file concept
# =========================================================================


class TestSignalFileConcept:
    """Tests for the runtime signal file pattern used by start.py."""

    def test_write_and_read_signal(self, tmp_path):
        signal_file = tmp_path / "plugin_start_test-plugin"
        signal_file.write_text("test-plugin", encoding="utf-8")
        assert signal_file.exists()
        assert signal_file.read_text(encoding="utf-8") == "test-plugin"

    def test_process_and_delete_signal(self, tmp_path):
        signal_file = tmp_path / "plugin_start_test-plugin"
        signal_file.write_text("test-plugin", encoding="utf-8")
        assert signal_file.exists()

        content = signal_file.read_text(encoding="utf-8")
        assert content == "test-plugin"
        signal_file.unlink()
        assert not signal_file.exists()

    def test_signal_naming_convention(self, tmp_path):
        name = "test-plugin"
        action = "stop"
        signal_file = tmp_path / f"plugin_{action}_{name}"
        signal_file.write_text(name, encoding="utf-8")
        assert signal_file.stem.lower() == f"plugin_{action}_{name}"
        assert signal_file.suffix == ""


# =========================================================================
# Plugin manifest discovery
# =========================================================================


class TestManifestDiscovery:
    """Tests for plugin.json manifest discovery (no API dependency)."""

    def test_single_manifest(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "my-plugin"
        plugin_dir.mkdir(parents=True)
        manifest = {
            "name": "my-plugin",
            "version": "1.0.0",
            "entry_point": "main.py",
            "display_name": "My Plugin",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=tmp_path / "plugins")
        discovered = launcher._discover_from_manifests()
        assert len(discovered) == 1
        assert discovered[0].name == "my-plugin"

    def test_invalid_json_skipped(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "bad-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("not json")

        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=tmp_path / "plugins")
        discovered = launcher._discover_from_manifests()
        assert len(discovered) == 0

    def test_missing_plugin_json_skipped(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "empty-plugin"
        plugin_dir.mkdir(parents=True)

        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=tmp_path / "plugins")
        discovered = launcher._discover_from_manifests()
        assert len(discovered) == 0

    def test_duplicate_names_skipped(self, tmp_path):
        for i, _ in enumerate(("dup-plugin", "dup-plugin")):
            d = tmp_path / "plugins" / f"dir{i}"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(
                json.dumps(
                    {
                        "name": "dup-plugin",
                        "version": "1.0",
                        "entry_point": "main.py",
                        "display_name": "Dup",
                    }
                )
            )

        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=tmp_path / "plugins")
        discovered = launcher._discover_from_manifests()
        assert len(discovered) == 1

    def test_multiple_plugins(self, tmp_path):
        for i in range(3):
            d = tmp_path / "plugins" / f"p{i}"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(
                json.dumps(
                    {
                        "name": f"p{i}",
                        "version": "1.0",
                        "entry_point": "main.py",
                        "display_name": f"P{i}",
                    }
                )
            )

        from core.api.launcher import PluginLauncher

        launcher = PluginLauncher(plugins_dir=tmp_path / "plugins")
        discovered = launcher._discover_from_manifests()
        assert len(discovered) == 3
        assert {m.name for m in discovered} == {"p0", "p1", "p2"}


# =========================================================================
# Plugin registration via API
# =========================================================================


class TestPluginRegistration:
    """Tests for the POST /api/v1/plugins/register endpoint."""

    def test_register_and_list(self, client):
        resp = client.post(
            "/api/v1/plugins/register",
            json={"name": "lifecycle-test", "path": "/fake.exe"},
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert body["plugin"]["name"] == "lifecycle-test"

        get_resp = client.get("/api/v1/plugins")
        names = [p["name"] for p in get_resp.json().get("plugins", [])]
        assert "lifecycle-test" in names

    def test_enable_disable_endpoints(self, client):
        client.post(
            "/api/v1/plugins/register",
            json={"name": "sig-test", "path": "/fake.exe", "enabled": False},
        )
        enable_resp = client.post("/api/v1/plugins/sig-test/enable")
        assert enable_resp.status_code == 200
        assert enable_resp.json()["enabled"] is True

        disable_resp = client.post("/api/v1/plugins/sig-test/disable")
        assert disable_resp.status_code == 200
        assert disable_resp.json()["enabled"] is False


# =========================================================================
# Health check logic (process dictionary, standalone)
# =========================================================================


class TestHealthCheck:
    """Tests for the health check pattern used by start.py."""

    def test_identifies_dead_processes(self):
        processes = {}
        processes["dead"] = MagicMock()
        processes["dead"].poll.return_value = 0
        processes["alive"] = MagicMock()
        processes["alive"].poll.return_value = None

        dead = [n for n, p in processes.items() if p.poll() is not None]
        assert "dead" in dead
        assert "alive" not in dead

    def test_all_alive_returns_empty_dead(self):
        processes = {}
        for i in range(3):
            processes[f"p{i}"] = MagicMock()
            processes[f"p{i}"].poll.return_value = None

        dead = [n for n, p in processes.items() if p.poll() is not None]
        assert dead == []

    def test_all_dead_returns_all(self):
        processes = {}
        for i in range(3):
            processes[f"p{i}"] = MagicMock()
            processes[f"p{i}"].poll.return_value = 1

        dead = [n for n, p in processes.items() if p.poll() is not None]
        assert len(dead) == 3


# =========================================================================
# Bridge initialization
# =========================================================================


class TestBridgeInit:
    """Tests for config loading and comment handler fetch."""

    def test_load_config_reads_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("server_host: 127.0.0.1\ntiktok:\n  user: test_user\n")

        from core.yaml_utils import load_yaml

        cfg = load_yaml(config_file)
        assert cfg["server_host"] == "127.0.0.1"
        assert cfg["tiktok"]["user"] == "test_user"
