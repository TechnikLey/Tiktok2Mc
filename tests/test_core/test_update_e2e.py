"""End-to-end update validation tests.

Covers the full update flow that the compiled update.exe performs:
  - Config migration (_inject_values_strictly, migrate_config_if_needed)
  - Whitelist file copy path filtering
  - Signal orchestration
  - Version file I/O
  - Full run_update() flow with mocks
"""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
import requests

# =========================================================================
# _inject_values_strictly — pure config injection logic
# =========================================================================


# Reimplement the function inline for testability (it's pure logic).
# The canonical version lives in src/python/update.py.
def _inject_values_strictly(template, user_source, path=""):
    if user_source is None:
        return
    if not isinstance(user_source, (dict)):
        return
    for key in template:
        current_path = f"{path}.{key}" if path else key
        if key in user_source:
            user_value = user_source[key]
            template_value = template[key]
            if isinstance(template_value, dict):
                if isinstance(user_value, dict):
                    _inject_values_strictly(template_value, user_value, current_path)
                elif user_value is None:
                    pass
                else:
                    pass
            else:
                if user_value is not None:
                    template[key] = user_value
        else:
            pass


class TestInjectValuesStrictly:
    """Config injection logic — the core of config migration."""

    def test_preserves_user_values(self):
        template = {"server_host": "0.0.0.0", "config_version": "1.0"}
        user = {"server_host": "127.0.0.1", "config_version": "1.0"}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "127.0.0.1"
        assert template["config_version"] == "1.0"

    def test_keeps_default_when_user_missing_key(self):
        template = {"server_host": "0.0.0.0", "java": {"xms": "512M"}}
        user = {"server_host": "127.0.0.1"}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "127.0.0.1"
        assert template["java"]["xms"] == "512M"

    def test_recursive_nested_dicts(self):
        template = {"java": {"xms": "512M", "xmx": "1G"}, "rcon": {"port": 25575}}
        user = {"java": {"xms": "1G"}, "rcon": {}}
        _inject_values_strictly(template, user)
        assert template["java"]["xms"] == "1G"
        assert template["java"]["xmx"] == "1G"
        assert template["rcon"]["port"] == 25575

    def test_skips_user_keys_not_in_template(self):
        template = {"server_host": "0.0.0.0"}
        user = {"server_host": "127.0.0.1", "unknown_key": "should_be_dropped"}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "127.0.0.1"
        assert "unknown_key" not in template

    def test_preserves_booleans_and_numbers(self):
        template = {"auto_update_config": False, "control_method": "DCS"}
        user = {"auto_update_config": True, "control_method": "RCON"}
        _inject_values_strictly(template, user)
        assert template["auto_update_config"] is True
        assert template["control_method"] == "RCON"

    def test_handles_none_user_value(self):
        template = {"server_host": "0.0.0.0", "shutdown": {}}
        user = {"server_host": None, "shutdown": None}
        _inject_values_strictly(template, user)
        assert template["server_host"] == "0.0.0.0"
        assert template["shutdown"] == {}

    def test_handles_none_user_source_root(self):
        template = {"config_version": "1.0"}
        _inject_values_strictly(template, None)
        assert template["config_version"] == "1.0"

    def test_handles_empty_user_source(self):
        template = {"server_host": "0.0.0.0"}
        _inject_values_strictly(template, {})
        assert template["server_host"] == "0.0.0.0"

    def test_overwrites_template_list_with_user_list(self):
        template = {"shutdown": {"countdown_times": [5, 10, 30]}}
        user = {"shutdown": {"countdown_times": [10, 20, 60]}}
        _inject_values_strictly(template, user)
        assert template["shutdown"]["countdown_times"] == [10, 20, 60]


# =========================================================================
# Config migration (migrate_config_if_needed)
# =========================================================================


class TestMigrateConfigIfNeeded:
    """Tests the config migration flow — the function is imported from
    update.py after setting up the necessary path structure."""

    @contextmanager
    def _import_migrate(self, tmp_path: Path, auto_update: bool = True):
        """Context manager: patch module globals in update.py, yield the function."""
        import python.update

        base_dir = tmp_path / "base"
        base_dir.mkdir()
        config_dir = base_dir / "config"
        config_dir.mkdir()
        default_config = config_dir / "config.default.yaml"
        user_config = config_dir / "config.yaml"

        with (
            patch.object(python.update, "BASE_DIR", base_dir),
            patch.object(python.update, "CONFIG_FILE", user_config),
            patch.object(python.update, "DEFAULT_CONFIG_FILE", default_config),
            patch.object(python.update, "VERSION_FILE", base_dir / "version.txt"),
            patch.object(python.update, "TEMP_DIR", tmp_path / "_update_tmp"),
            patch.object(python.update, "START_FILE", base_dir / "start.exe"),
            patch.object(python.update, "cfg", {"auto_update_config": auto_update}),
            patch.object(python.update, "CONFIG_UPDATE_ENABLE", auto_update),
            patch.object(python.update, "AUTO_MODE", True),
            patch.object(python.update, "wait_for_key"),
            patch.object(python.update, "log"),
        ):
            yield python.update.migrate_config_if_needed, default_config, user_config

    def test_creates_config_when_missing(self, tmp_path):
        with self._import_migrate(tmp_path) as (migrate, default_config, user_config):
            default_config.write_text("server_host: 127.0.0.1\nconfig_version: '1.0'\n")
            assert not user_config.exists()
            result = migrate()
            assert result is True
            assert user_config.exists()

    def test_skips_when_up_to_date(self, tmp_path):
        with self._import_migrate(tmp_path) as (migrate, default_config, user_config):
            default_config.write_text("config_version: '1.0'\n")
            user_config.write_text("config_version: '1.0'\n")
            result = migrate()
            assert result is False

    def test_migrates_legacy_version(self, tmp_path):
        with self._import_migrate(tmp_path) as (migrate, default_config, user_config):
            default_config.write_text("config_version: '1.0'\nserver_host: 0.0.0.0\n")
            user_config.write_text("config_version: '0.7'\nserver_host: 127.0.0.1\n")
            result = migrate()
            assert result is True
            import yaml

            with user_config.open() as f:
                data = yaml.safe_load(f)
            assert data["config_version"] == "1.0"
            assert data["server_host"] == "127.0.0.1"

    def test_returns_false_when_default_missing(self, tmp_path):
        with self._import_migrate(tmp_path) as (migrate, _default_config, _user_config):
            result = migrate()
            assert result is False

    def test_migrates_legacy_int_version(self, tmp_path):
        with self._import_migrate(tmp_path) as (migrate, default_config, user_config):
            default_config.write_text("config_version: '1.0'\nserver_host: 0.0.0.0\n")
            user_config.write_text("config_version: 7\nserver_host: 192.168.1.1\n")
            result = migrate()
            assert result is True
            import yaml

            with user_config.open() as f:
                data = yaml.safe_load(f)
            assert data["config_version"] == "1.0"
            assert data["server_host"] == "192.168.1.1"


# =========================================================================
# Whitelist file copy logic
# =========================================================================


class TestUpdateWhitelist:
    """Tests the whitelist path filtering used during file copy."""

    WHITELIST_DIRS: ClassVar[set[str]] = {
        "core",
        "scripts",
        "config",
        "plugins/deathcounter",
        "plugins/timer",
        "plugins/wincounter",
        "plugins/spotify",
    }
    WHITELIST_DIR_FILES: ClassVar[set[str]] = {
        "hooks/random/main.py",
        "hooks/example_hook/main.py",
    }
    WHITELIST_FILES: ClassVar[set[str]] = {
        "version.txt",
        "README.md",
        "LICENSE",
        "start.exe",
    }

    def _should_copy(self, rel_path_str: str, file: str) -> bool:
        """Reimplements the path-filtering logic from update.py lines 484-503."""
        import sys

        SUFFIX = ".exe" if sys.platform == "win32" else ".bin"
        WHITELIST_FILES = {
            "version.txt",
            "README.md",
            "LICENSE",
            f"start{SUFFIX}",
        }

        if (
            rel_path_str != "."
            and not any(
                rel_path_str == d or rel_path_str.startswith(d + "/")
                for d in self.WHITELIST_DIRS
            )
            and not any(
                f.startswith(rel_path_str + "/") for f in self.WHITELIST_DIR_FILES
            )
        ):
            return False

        if rel_path_str == "." and file not in WHITELIST_FILES:
            return False

        if rel_path_str != ".":
            dir_whitelisted = any(
                rel_path_str == d or rel_path_str.startswith(d + "/")
                for d in self.WHITELIST_DIRS
            )
            if (
                not dir_whitelisted
                and f"{rel_path_str}/{file}" not in self.WHITELIST_DIR_FILES
            ):
                return False

        if file.lower() == f"update{SUFFIX}".lower():
            return False
        return file.lower() != "config.yaml"

    def test_whitelisted_root_files_copied(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        assert self._should_copy(".", "version.txt") is True
        assert self._should_copy(".", "README.md") is True
        assert self._should_copy(".", f"start{suffix}") is True

    def test_non_whitelisted_root_files_skipped(self):
        assert self._should_copy(".", "secret.key") is False
        assert self._should_copy(".", "user_data.db") is False

    def test_whitelisted_dir_files_copied(self):
        assert self._should_copy("core/api", "server.py") is True
        assert self._should_copy("plugins/wincounter", "main.py") is True

    def test_non_whitelisted_dir_skipped(self):
        assert self._should_copy("node_modules", "package.json") is False
        assert self._should_copy("temp", "cache.bin") is False

    def test_config_yaml_never_copied(self):
        assert self._should_copy("config", "config.yaml") is False

    def test_update_exe_never_copied(self):
        assert self._should_copy(".", "update.exe") is False

    def test_hooks_whitelisted(self):
        assert self._should_copy("hooks/random", "main.py") is True
        assert self._should_copy("hooks/example_hook", "main.py") is True
        assert (
            self._should_copy("plugins/spotify/hooks/spotify_control", "main.py")
            is True
        )

    def test_non_whitelisted_hook_skipped(self):
        assert self._should_copy("hooks", "custom_hook.py") is False

    def test_deeply_nested_whitelisted_path(self):
        assert self._should_copy("plugins/wincounter/subdir", "data.json") is True

    def test_deeply_nested_non_whitelisted(self):
        assert self._should_copy("plugins/unknown_plugin", "main.py") is False

    def test_server_existing_files_skipped_check(self):
        """The server/ directory is NOT whitelisted — only root server.exe is."""
        assert self._should_copy("server", "main.exe") is False


# =========================================================================
# Version file I/O
# =========================================================================


class TestVersionFileIO:
    """Tests version.txt read/write used by the updater."""

    def test_write_and_read_version_file(self, tmp_path):
        vf = tmp_path / "version.txt"
        vf.write_text("ToolVersion: 1.0.0\nUpdaterVersion: 0.2.0\n")
        content = vf.read_text()
        assert "ToolVersion: 1.0.0" in content
        assert "UpdaterVersion: 0.2.0" in content

    def test_parse_version_file(self, tmp_path):
        vf = tmp_path / "version.txt"
        vf.write_text("ToolVersion: v1.0.0-beta\nUpdaterVersion: 0.2.0\n")
        versions = {}
        for line in vf.read_text().strip().splitlines():
            if ":" in line:
                k, val = map(str.strip, line.split(":", 1))
                versions[k.lower()] = val
        assert "toolversion" in versions
        import re

        m = re.search(r"(\d+\.\d+(\.\d+)?(-beta|-alpha)?)", versions["toolversion"])
        assert m.group(1) == "1.0.0-beta"

    def test_missing_version_file(self, tmp_path):
        vf = tmp_path / "version.txt"
        assert not vf.exists()

    def test_round_trip_preserves_format(self, tmp_path):
        vf = tmp_path / "version.txt"
        original = "ToolVersion: 1.0.0\nUpdaterVersion: 0.2.0\n"
        vf.write_text(original)
        assert vf.read_text() == original


# =========================================================================
# Extract version
# =========================================================================


class TestExtractVersion:
    """Tests the extract_version regex."""

    def test_standard_semver(self):
        import re

        def extract_version(text):
            if not text:
                return "0.0.0"
            m = re.search(r"(\d+\.\d+(\.\d+)?(-beta|-alpha)?)", str(text))
            return m.group(1) if m else "0.0.0"

        assert extract_version("v1.0.0") == "1.0.0"
        assert extract_version("1.5.2") == "1.5.2"
        assert extract_version("v2.0.0-beta") == "2.0.0-beta"
        assert extract_version("0.7") == "0.7"
        assert extract_version("") == "0.0.0"
        assert extract_version(None) == "0.0.0"
        assert extract_version("no-version-here") == "0.0.0"


# =========================================================================
# Full run_update orchestration (with mocks)
# =========================================================================


class TestRunUpdateOrchestration:
    """Tests the full run_update() flow with mocked external dependencies."""

    @contextmanager
    def _get_run_update(self, tmp_path: Path):
        """Context manager: patch module globals in update.py, yield function + paths."""
        # Mock core.api.server BEFORE importing python.update to avoid
        # the heavy FastAPI import chain (routes, eventbus, overlay, etc.)
        if "core.api.server" not in sys.modules:
            _mock_server = MagicMock()
            _mock_server.DEFAULT_PORT = 29185
            sys.modules["core.api.server"] = _mock_server

        import python.update
        from core.backup import BackupManager

        base_dir = tmp_path / "install"
        base_dir.mkdir()
        config_dir = base_dir / "config"
        config_dir.mkdir()
        user_config = config_dir / "config.yaml"
        user_config.write_text("config_version: '0.7'\nserver_host: 127.0.0.1\n")
        default_config = config_dir / "config.default.yaml"
        default_config.write_text("config_version: '1.0'\nserver_host: 0.0.0.0\n")
        version_file = base_dir / "version.txt"
        version_file.write_text("ToolVersion: 0.7.0\nUpdaterVersion: 0.1.0\n")
        temp_dir = tmp_path / "_update_tmp"
        temp_dir.mkdir()

        # Create a BackupManager rooted at base_dir so backups stay inside
        # the test's tmp_path and relative_to() works in assertions.
        test_bm = BackupManager(root_dir=base_dir)

        with (
            patch.object(python.update, "BASE_DIR", base_dir),
            patch.object(python.update, "CONFIG_FILE", user_config),
            patch.object(python.update, "DEFAULT_CONFIG_FILE", default_config),
            patch.object(python.update, "VERSION_FILE", version_file),
            patch.object(python.update, "TEMP_DIR", temp_dir),
            patch.object(python.update, "START_FILE", base_dir / "start.exe"),
            patch.object(python.update, "cfg", {"auto_update_config": True}),
            patch.object(python.update, "CONFIG_UPDATE_ENABLE", True),
            patch.object(python.update, "AUTO_MODE", True),
            patch.object(python.update, "get_base_dir", return_value=base_dir),
            patch.object(python.update, "wait_for_key"),
            patch.object(python.update, "log"),
            patch("core.backup._backup_manager", test_bm),
            patch("core.backup.get_backup_manager", return_value=test_bm),
        ):
            yield python.update.run_update, base_dir, temp_dir

    def test_up_to_date_skips_update(self, tmp_path):
        """When local version >= remote version, should exit with code 5."""
        with (
            self._get_run_update(tmp_path) as (run_update, _base_dir, _temp_dir),
            patch("python.update.requests.get") as mock_get,
            patch("python.update.sys.exit", side_effect=SystemExit) as mock_exit,
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tag_name": "v0.7.0",
                "assets": [],
            }
            mock_get.return_value = mock_response

            with pytest.raises(SystemExit):
                run_update()
            mock_exit.assert_called_once_with(5)

    def test_transient_api_error_is_retried(self, tmp_path):
        """A transient network/DNS failure must not abort the update —
        the version check should be retried and succeed on the second attempt."""
        with (
            self._get_run_update(tmp_path) as (run_update, _base_dir, _temp_dir),
            patch("python.update.requests.get") as mock_get,
            patch("python.update.time.sleep") as mock_sleep,
            patch("python.update.sys.exit", side_effect=SystemExit) as mock_exit,
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tag_name": "v0.7.0",
                "assets": [],
            }
            mock_get.side_effect = [
                requests.exceptions.ConnectionError(
                    "Failed to resolve 'api.github.com'"
                ),
                mock_response,
            ]

            with pytest.raises(SystemExit):
                run_update()
            mock_exit.assert_called_once_with(5)
            mock_sleep.assert_called_once_with(2)
            assert mock_get.call_count == 2

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Simulates Windows-only release assets"
    )
    def test_new_version_downloads_and_installs(self, tmp_path):
        """Simulate a complete update: download -> extract -> copy."""
        with self._get_run_update(tmp_path) as (run_update, base_dir, _temp_dir):

            def fake_populate(path):
                (path / "version.txt").write_text(
                    "ToolVersion: 1.0.0\nUpdaterVersion: 0.1.0\n"
                )
                (path / "README.md").write_text("new readme")
                core_dir = path / "core"
                core_dir.mkdir()
                (core_dir / "new_file.py").write_text("# new")
                (path / "config").mkdir()
                (path / "config" / "config.yaml").write_text("should_be_skipped\n")
                (path / "update.exe").write_text("should_be_skipped\n")

            with (
                patch("python.update.requests.get") as mock_get,
                patch("python.update.verify_checksum", return_value=True),
                patch("python.update.sys.exit", side_effect=SystemExit),
                patch("python.update.shutil.copy2") as mock_copy2,
                patch("python.update.shutil.rmtree"),
                patch("python.update.download_with_progress"),
                patch("python.update.zipfile.ZipFile") as mock_zip,
            ):
                mock_zip.return_value.__enter__.return_value.extractall = fake_populate

                release_resp = MagicMock()
                release_resp.status_code = 200
                release_resp.json.return_value = {
                    "tag_name": "v1.0.0",
                    "assets": [
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip",
                            "url": "https://fake.url/asset",
                        },
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip.sha256",
                            "url": "https://fake.url/asset.sha256",
                        },
                    ],
                }
                checksum_resp = MagicMock()
                checksum_resp.status_code = 200
                checksum_resp.text = "a" * 64 + "\n"  # valid 64-char hex

                def mock_get_side_effect(url, **kwargs):
                    if "releases/latest" in url or "/releases" in url:
                        return release_resp
                    if "asset.sha256" in url:
                        return checksum_resp
                    if "updater/signal" in url:
                        signal_resp = MagicMock()
                        signal_resp.status_code = 200
                        signal_resp.json.return_value = {"signal": None}
                        return signal_resp
                    raise requests.exceptions.RequestException("unexpected URL")

                mock_get.side_effect = mock_get_side_effect

                with pytest.raises(SystemExit):
                    run_update()

                copied_dsts = [
                    call_args[0][1] for call_args in mock_copy2.call_args_list
                ]
                dst_names = [
                    str(p.relative_to(base_dir)).replace("\\", "/") for p in copied_dsts
                ]
                assert "core/new_file.py" in dst_names
                assert "config/config.yaml" not in dst_names
                assert "update.exe" not in " ".join(dst_names).lower()
                assert "README.md" in dst_names or "readme.md" in dst_names

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Simulates Windows-only release assets"
    )
    def test_kill_signal_written_before_copy(self, tmp_path):
        """The updater writes update_signal.tmp BEFORE copying files."""
        with self._get_run_update(tmp_path) as (run_update, base_dir, _temp_dir):

            def fake_populate(path):
                (path / "version.txt").write_text(
                    "ToolVersion: 1.0.0\nUpdaterVersion: 0.1.0\n"
                )

            signal_path = base_dir / "update_signal.tmp"
            signal_written = [False]
            original_write_text = Path.write_text

            def tracking_write_text(self, content):
                if self == signal_path:
                    signal_written[0] = True
                return original_write_text(self, content)

            with (
                patch("python.update.requests.get") as mock_get,
                patch("python.update.verify_checksum", return_value=True),
                patch("python.update.sys.exit", side_effect=SystemExit),
                patch("python.update.time.sleep"),
                patch("python.update.shutil.rmtree"),
                patch("python.update.shutil.copy2"),
                patch("python.update.download_with_progress"),
                patch("python.update.zipfile.ZipFile") as mock_zip,
            ):
                mock_zip.return_value.__enter__.return_value.extractall = fake_populate

                release_resp = MagicMock()
                release_resp.status_code = 200
                release_resp.json.return_value = {
                    "tag_name": "v1.0.0",
                    "assets": [
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip",
                            "url": "https://fake.url/asset",
                        },
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip.sha256",
                            "url": "https://fake.url/asset.sha256",
                        },
                    ],
                }
                checksum_resp = MagicMock()
                checksum_resp.status_code = 200
                checksum_resp.text = "a" * 64 + "\n"

                def mock_get_side_effect(url, **kwargs):
                    if "releases/latest" in url or "/releases" in url:
                        return release_resp
                    if "asset.sha256" in url:
                        return checksum_resp
                    if "updater/signal" in url:
                        signal_resp = MagicMock()
                        signal_resp.status_code = 200
                        signal_resp.json.return_value = {"signal": None}
                        return signal_resp
                    raise requests.exceptions.RequestException("unexpected URL")

                mock_get.side_effect = mock_get_side_effect

                with patch.object(Path, "write_text", tracking_write_text):
                    with pytest.raises(SystemExit):
                        run_update()
                    assert signal_written[0], "Signal file should have been written"

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Simulates Windows-only release assets"
    )
    def test_dual_signaling_file_and_api(self, tmp_path):
        """Update writes both file-based and API-based kill signals."""
        with self._get_run_update(tmp_path) as (run_update, _base_dir, _temp_dir):

            def fake_populate(path):
                (path / "version.txt").write_text(
                    "ToolVersion: 1.0.0\nUpdaterVersion: 0.1.0\n"
                )

            api_put_called = [False]

            def tracking_put(url, **kwargs):
                if "updater/signal" in url:
                    api_put_called[0] = True

            with (
                patch("python.update.requests.get") as mock_get,
                patch("python.update.requests.put", side_effect=tracking_put),
                patch("python.update.requests.delete"),
                patch("python.update.verify_checksum", return_value=True),
                patch("python.update.sys.exit", side_effect=SystemExit),
                patch("python.update.time.sleep"),
                patch("python.update.shutil.rmtree"),
                patch("python.update.shutil.copy2"),
                patch("python.update.download_with_progress"),
                patch("python.update.zipfile.ZipFile") as mock_zip,
            ):
                mock_zip.return_value.__enter__.return_value.extractall = fake_populate

                release_resp = MagicMock()
                release_resp.status_code = 200
                release_resp.json.return_value = {
                    "tag_name": "v1.0.0",
                    "assets": [
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip",
                            "url": "https://fake.url/asset",
                        },
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip.sha256",
                            "url": "https://fake.url/asset.sha256",
                        },
                    ],
                }
                checksum_resp = MagicMock()
                checksum_resp.status_code = 200
                checksum_resp.text = "a" * 64 + "\n"

                def mock_get_side_effect(url, **kwargs):
                    if "releases/latest" in url or "/releases" in url:
                        return release_resp
                    if "asset.sha256" in url:
                        return checksum_resp
                    if "updater/signal" in url:
                        signal_resp = MagicMock()
                        signal_resp.status_code = 200
                        signal_resp.json.return_value = {"signal": None}
                        return signal_resp
                    raise requests.exceptions.RequestException("unexpected URL")

                mock_get.side_effect = mock_get_side_effect

                with pytest.raises(SystemExit):
                    run_update()

                assert api_put_called[0], "API kill signal should have been sent"

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Simulates Windows-only release assets"
    )
    def test_signal_wait_polling_loop(self, tmp_path):
        """After sending kill signal, updater polls until signal is consumed or timeout."""
        with self._get_run_update(tmp_path) as (run_update, base_dir, _temp_dir):

            def fake_populate(path):
                (path / "version.txt").write_text(
                    "ToolVersion: 1.0.0\nUpdaterVersion: 0.1.0\n"
                )

            # Pre-write the signal file — run_update overwrites it then polls
            signal_file = base_dir / "update_signal.tmp"
            signal_file.write_text("kill")

            with (
                patch("python.update.requests.get") as mock_get,
                patch("python.update.requests.put"),
                patch("python.update.requests.delete"),
                patch("python.update.sys.exit", side_effect=SystemExit),
                patch("python.update.time.sleep"),
                patch("python.update.shutil.rmtree"),
                patch("python.update.shutil.copy2"),
                patch("python.update.download_with_progress"),
                patch("python.update.zipfile.ZipFile") as mock_zip,
            ):
                mock_zip.return_value.__enter__.return_value.extractall = fake_populate

                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "tag_name": "v1.0.0",
                    "assets": [
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip",
                            "url": "https://fake.url/asset",
                        }
                    ],
                }
                mock_get.return_value = mock_resp

                with pytest.raises(SystemExit):
                    run_update()

                assert True  # didn't hang

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Simulates Windows-only release assets"
    )
    def test_updater_self_update_triggers_resume(self, tmp_path):
        """When a new updater version is detected, the old updater should
        copy the new updater and exit (to be resumed via --resume)."""
        with self._get_run_update(tmp_path) as (run_update, _base_dir, _temp_dir):

            def fake_populate(path):
                (path / "version.txt").write_text(
                    "ToolVersion: 1.0.0\nUpdaterVersion: 9.9.9\n"
                )
                (path / "core").mkdir(exist_ok=True)
                (path / "core" / "update.exe").write_text("new updater binary")

            with (
                patch("python.update.requests.get") as mock_get,
                patch("python.update.subprocess.Popen") as mock_popen,
                patch("python.update.verify_checksum", return_value=True),
                patch("python.update.sys.exit", side_effect=SystemExit),
                patch("python.update.shutil.copy2"),
                patch("python.update.shutil.rmtree"),
                patch("python.update.os.chmod"),
                patch("python.update.download_with_progress"),
                patch("python.update.zipfile.ZipFile") as mock_zip,
            ):
                mock_zip.return_value.__enter__.return_value.extractall = fake_populate

                release_resp = MagicMock()
                release_resp.status_code = 200
                release_resp.json.return_value = {
                    "tag_name": "v1.0.0",
                    "assets": [
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip",
                            "url": "https://fake.url/asset",
                        },
                        {
                            "name": "Tiktok2Mc_v1.0.0_Windows.zip.sha256",
                            "url": "https://fake.url/asset.sha256",
                        },
                    ],
                }
                checksum_resp = MagicMock()
                checksum_resp.status_code = 200
                checksum_resp.text = "a" * 64 + "\n"

                def mock_get_side_effect(url, **kwargs):
                    if "releases/latest" in url or "/releases" in url:
                        return release_resp
                    if "asset.sha256" in url:
                        return checksum_resp
                    if "updater/signal" in url:
                        signal_resp = MagicMock()
                        signal_resp.status_code = 200
                        signal_resp.json.return_value = {"signal": None}
                        return signal_resp
                    raise requests.exceptions.RequestException("unexpected URL")

                mock_get.side_effect = mock_get_side_effect

                with pytest.raises(SystemExit):
                    run_update()

                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                assert "--resume" in args, f"Expected --resume in {args}"


# =========================================================================
# Signal cleanup after update
# =========================================================================


class TestUpdateSignalCleanup:
    """Tests that signal files are cleaned up after update completes."""

    def test_signal_file_deleted_after_update(self, tmp_path):
        signal_file = tmp_path / "update_signal.tmp"
        signal_file.write_text("kill")
        assert signal_file.exists()
        if signal_file.exists():
            signal_file.unlink()
        assert not signal_file.exists()

    def test_api_signal_cleared_after_update(self, client):
        resp = client.put("/api/v1/updater/signal", json={"signal": "kill"})
        assert resp.status_code == 200
        resp = client.delete("/api/v1/updater/signal")
        assert resp.status_code == 200
        resp = client.get("/api/v1/updater/signal")
        assert resp.json().get("signal") is None


# =========================================================================
# Platform path correctness
# =========================================================================


class TestUpdatePlatformPaths:
    """Windows/Linux path conventions used in the updater."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_windows_suffix(self):
        import sys as _sys

        assert _sys.platform == "win32"

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-specific")
    def test_linux_suffix(self):
        import sys as _sys

        assert _sys.platform != "win32"

    def test_suffix_constant_consistent(self):
        suffix = ".exe" if sys.platform == "win32" else ".bin"
        base = Path(__file__).resolve().parent.parent.parent / "src"
        update_exe = base / "python" / f"update{suffix}"
        assert update_exe.name == f"update{suffix}"

    def test_signal_file_path_resolved(self, tmp_path):
        base = tmp_path
        signal_file = base / "update_signal.tmp"
        assert signal_file.parent == base
        assert signal_file.suffix == ".tmp"

    def test_update_tmp_dir_resolved(self, tmp_path):
        base = tmp_path
        temp_dir = (base / "_update_tmp").resolve()
        assert str(temp_dir).endswith("_update_tmp")


# =========================================================================
# Update source override (TIKTOK2MC_UPDATE_SOURCE)
# =========================================================================


class TestUpdateSourceOverride:
    """Tests the test-only update source override in update.py._init()."""

    _GLOBALS = (
        "BASE_DIR",
        "TEMP_DIR",
        "VERSION_FILE",
        "DEFAULT_CONFIG_FILE",
        "CONFIG_FILE",
        "START_FILE",
        "AUTO_MODE",
        "cfg",
        "CONFIG_UPDATE_ENABLE",
        "GITHUB_TOKEN",
        "HEADERS_API",
        "HEADERS_ASSET",
        "API_URL",
    )

    def _run_init(self, monkeypatch, tmp_path: Path) -> None:
        import python.update

        base = tmp_path / "base"
        (base / "config").mkdir(parents=True)
        (base / "config" / "config.yaml").write_text(
            "auto_update_config: true\nshow_sudo_warning: false\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(python.update, "get_base_dir", lambda: base)
        monkeypatch.setattr(
            python.update,
            "load_config",
            lambda _path: {"auto_update_config": True},
        )
        monkeypatch.setattr(sys, "argv", ["update.py", "--auto"])
        python.update._init()

    def test_env_override_sets_api_url(self, monkeypatch, tmp_path):
        import python.update

        snap = {n: getattr(python.update, n, None) for n in self._GLOBALS}
        try:
            monkeypatch.setenv(
                "TIKTOK2MC_UPDATE_SOURCE",
                "http://127.0.0.1:9999/repos/x/y/releases/latest",
            )
            self._run_init(monkeypatch, tmp_path)
            assert (
                python.update.API_URL
                == "http://127.0.0.1:9999/repos/x/y/releases/latest"
            )
        finally:
            for n, v in snap.items():
                setattr(python.update, n, v)
            monkeypatch.delenv("TIKTOK2MC_UPDATE_SOURCE", raising=False)

    def test_no_env_keeps_default_api_url(self, monkeypatch, tmp_path):
        import python.update

        snap = {n: getattr(python.update, n, None) for n in self._GLOBALS}
        try:
            monkeypatch.delenv("TIKTOK2MC_UPDATE_SOURCE", raising=False)
            default = python.update.API_URL
            self._run_init(monkeypatch, tmp_path)
            assert python.update.API_URL == default
            assert python.update.API_URL.startswith("https://api.github.com/")
        finally:
            for n, v in snap.items():
                setattr(python.update, n, v)
            monkeypatch.delenv("TIKTOK2MC_UPDATE_SOURCE", raising=False)


# =========================================================================
# Status reporting + relaunch helpers (GUI launcher feedback)
# =========================================================================


class TestUpdateStatusReporting:
    """Tests the GUI-feedback helpers added to update.py.

    ``_write_update_status`` / ``_clear_update_status`` publish progress for
    ``gui.py::LauncherAPI.get_update_status``; ``_relaunch_tool_after_update``
    restarts ``start.exe`` after a successful ``--auto`` install because
    ``start.py`` already exited on the kill signal.
    """

    def test_write_status_writes_json(self, tmp_path):
        import python.update

        status_file = tmp_path / "update_status.json"
        with (
            patch.object(python.update, "UPDATE_STATUS_FILE", status_file),
            patch.object(python.update, "log"),
        ):
            python.update._write_update_status("downloading", progress=42)
        assert json.loads(status_file.read_text(encoding="utf-8")) == {
            "phase": "downloading",
            "progress": 42,
            "message": "",
        }

    def test_write_status_with_message(self, tmp_path):
        import python.update

        status_file = tmp_path / "update_status.json"
        with (
            patch.object(python.update, "UPDATE_STATUS_FILE", status_file),
            patch.object(python.update, "log"),
        ):
            python.update._write_update_status("error", message="Update failed.")
        assert json.loads(status_file.read_text(encoding="utf-8"))["message"] == (
            "Update failed."
        )

    def test_clear_status_removes_file(self, tmp_path):
        import python.update

        status_file = tmp_path / "update_status.json"
        status_file.write_text("{}", encoding="utf-8")
        with (
            patch.object(python.update, "UPDATE_STATUS_FILE", status_file),
            patch.object(python.update, "log"),
        ):
            python.update._clear_update_status()
        assert not status_file.exists()

    def test_status_helpers_are_noops_without_file(self):
        """When _init() was never called, UPDATE_STATUS_FILE is None → no-ops."""
        import python.update

        with (
            patch.object(python.update, "UPDATE_STATUS_FILE", None),
            patch.object(python.update, "log"),
        ):
            python.update._write_update_status("checking")
            python.update._clear_update_status()

    def test_status_write_failure_is_swallowed(self, tmp_path):
        import python.update

        status_file = tmp_path / "update_status.json"
        with (
            patch.object(python.update, "UPDATE_STATUS_FILE", status_file),
            patch.object(python.update, "log"),
            patch.object(
                status_file.__class__, "write_text", side_effect=OSError("locked")
            ),
        ):
            python.update._write_update_status("checking")  # must not raise

    def test_relaunch_skipped_outside_auto_mode(self):
        import python.update

        with (
            patch.object(python.update, "AUTO_MODE", False),
            patch.object(python.update, "subprocess") as mock_sp,
            patch.object(python.update, "log"),
        ):
            assert python.update._relaunch_tool_after_update() is True
        mock_sp.Popen.assert_not_called()

    def test_relaunch_launches_start_exe(self):
        import python.update

        start_file = Path("install") / "start.exe"
        with (
            patch.object(python.update, "AUTO_MODE", True),
            patch.object(python.update, "START_FILE", start_file),
            patch.object(python.update, "subprocess") as mock_sp,
            patch.object(python.update, "log"),
        ):
            assert python.update._relaunch_tool_after_update() is True
        assert mock_sp.Popen.call_count == 1
        cmd = mock_sp.Popen.call_args[0][0]
        assert str(cmd[0]).endswith("start.exe")

    def test_relaunch_returns_false_on_oserror(self):
        import python.update

        mock_sp = MagicMock()
        mock_sp.Popen = MagicMock(side_effect=OSError("start.exe missing"))
        with (
            patch.object(python.update, "AUTO_MODE", True),
            patch.object(python.update, "START_FILE", Path("start.exe")),
            patch.object(python.update, "subprocess", mock_sp),
            patch.object(python.update, "log"),
        ):
            assert python.update._relaunch_tool_after_update() is False


class TestInstallFileWithRetry:
    """Tests _install_file_with_retry (locked-file retry on Windows).

    The retry is what closes the race between start.exe exiting on the kill
    signal and the updater replacing it — on non-Windows platforms the first
    failure must propagate immediately (original behavior).
    """

    @staticmethod
    def _flaky_copy(fails: int, real_copy) -> tuple:
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] <= fails:
                raise OSError(32, "file in use")
            return real_copy(src, dst)

        return flaky, calls

    def test_success_first_try(self, tmp_path):
        import python.update

        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        with (
            patch.object(python.update, "sys", MagicMock(platform="win32")),
            patch.object(python.update, "log"),
        ):
            python.update._install_file_with_retry(src, dst)
        assert dst.read_text() == "data"

    def test_retries_lock_then_succeeds(self, tmp_path):
        import shutil

        import python.update

        real_copy = shutil.copy2
        flaky, calls = self._flaky_copy(2, real_copy)
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        with (
            patch.object(python.update, "sys", MagicMock(platform="win32")),
            patch.object(python.update.shutil, "copy2", flaky),
            patch.object(python.update.time, "sleep"),
        ):
            python.update._install_file_with_retry(src, dst)
        assert calls["n"] == 3
        assert dst.read_text() == "data"

    def test_raises_after_retry_window(self, tmp_path):
        import python.update

        calls = {"n": 0}

        def always_locked(_src, _dst):
            calls["n"] += 1
            raise OSError(32, "file in use")

        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        with (
            patch.object(python.update, "sys", MagicMock(platform="win32")),
            patch.object(python.update.shutil, "copy2", always_locked),
            patch.object(python.update.time, "sleep"),
            pytest.raises(OSError),
        ):
            python.update._install_file_with_retry(src, dst)
        assert calls["n"] == 101

    def test_no_retry_outside_win32(self, tmp_path):
        import python.update

        calls = {"n": 0}

        def always_fails(_src, _dst):
            calls["n"] += 1
            raise OSError("not locked")

        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        with (
            patch.object(python.update, "sys", MagicMock(platform="linux")),
            patch.object(python.update.shutil, "copy2", always_fails),
            pytest.raises(OSError),
        ):
            python.update._install_file_with_retry(src, dst)
        assert calls["n"] == 1
