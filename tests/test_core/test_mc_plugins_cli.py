"""Tests for MC Plugin CLI helper logic.

The actual _cli_* functions live in start.py which has heavy module-level
side-effects (config load, port scan, etc.) and cannot be imported in tests.
The same filesystem logic is exercised through the API route tests
(test_api/test_mc_plugins.py).  These tests cover the pure helper functions
and the filesystem operations directly.
"""

from __future__ import annotations

import re

import pytest


def _sanitize(name: str) -> str:
    name = re.sub(r"\.(jar|disabled)$", "", name, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9._-]", "", name)


class TestMcPluginSanitizeName:
    def test_plain_name(self):
        assert _sanitize("EssentialsX") == "EssentialsX"

    def test_strips_jar(self):
        assert _sanitize("MyPlugin.jar") == "MyPlugin"

    def test_strips_disabled_suffix(self):
        assert _sanitize("MyPlugin.disabled") == "MyPlugin"

    def test_strips_jar_from_double_extension(self):
        assert _sanitize("MyPlugin.jar.disabled") == "MyPlugin.jar"

    def test_removes_special_chars(self):
        assert _sanitize("My Plugin! @#") == "MyPlugin"

    def test_preserves_dots_and_dashes(self):
        assert _sanitize("my-plugin.v2.1") == "my-plugin.v2.1"

    def test_empty_after_strip(self):
        assert _sanitize("!!!") == ""

    def test_case_insensitive(self):
        assert _sanitize("Test.JAR") == "Test"


@pytest.fixture()
def plugins_dir(tmp_path):
    d = tmp_path / "server" / "default" / "plugins"
    d.mkdir(parents=True)
    return d


class TestMcPluginEnable:
    def test_enable(self, plugins_dir):
        disabled = plugins_dir / "MyPlugin.jar.disabled"
        disabled.write_bytes(b"plugin")
        enabled = plugins_dir / "MyPlugin.jar"
        disabled.rename(enabled)
        assert enabled.exists()
        assert not disabled.exists()

    def test_enable_already_enabled(self, plugins_dir):
        enabled = plugins_dir / "MyPlugin.jar"
        enabled.write_bytes(b"plugin")
        assert enabled.exists()

    def test_enable_nonexistent(self, plugins_dir):
        target = plugins_dir / "Ghost.jar"
        assert not target.exists()

    def test_enable_strips_extension(self, plugins_dir):
        disabled = plugins_dir / "Test.jar.disabled"
        disabled.write_bytes(b"plugin")
        enabled = plugins_dir / "Test.jar"
        disabled.rename(enabled)
        assert enabled.exists()
        assert not disabled.exists()


class TestMcPluginDisable:
    def test_disable(self, plugins_dir):
        enabled = plugins_dir / "MyPlugin.jar"
        enabled.write_bytes(b"plugin")
        disabled = plugins_dir / "MyPlugin.jar.disabled"
        enabled.rename(disabled)
        assert disabled.exists()
        assert not enabled.exists()

    def test_disable_already_disabled(self, plugins_dir):
        disabled = plugins_dir / "MyPlugin.jar.disabled"
        disabled.write_bytes(b"plugin")
        assert disabled.exists()

    def test_disable_nonexistent(self, plugins_dir):
        target = plugins_dir / "Ghost.jar.disabled"
        assert not target.exists()


class TestMcPluginDelete:
    def test_delete_enabled(self, plugins_dir):
        f = plugins_dir / "OldPlugin.jar"
        f.write_bytes(b"plugin")
        f.unlink()
        assert not f.exists()

    def test_delete_disabled(self, plugins_dir):
        f = plugins_dir / "OldPlugin.jar.disabled"
        f.write_bytes(b"plugin")
        f.unlink()
        assert not f.exists()

    def test_delete_nonexistent(self, plugins_dir):
        f = plugins_dir / "Ghost.jar"
        assert not f.exists()


class TestMcPluginScan:
    def test_scan_empty(self, plugins_dir):
        entries = [e for e in plugins_dir.iterdir() if e.is_file()]
        assert entries == []

    def test_scan_mixed(self, plugins_dir):
        (plugins_dir / "EssentialsX.jar").write_bytes(b"p")
        (plugins_dir / "Dynmap.jar.disabled").write_bytes(b"p")
        (plugins_dir / "subdir").mkdir()

        entries = sorted(
            [e for e in plugins_dir.iterdir() if e.is_file()],
            key=lambda p: p.name,
        )
        assert len(entries) == 2
        names = [e.name for e in entries]
        assert "Dynmap.jar.disabled" in names
        assert "EssentialsX.jar" in names
