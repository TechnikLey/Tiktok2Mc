"""Tests for core.sandbox"""

import subprocess
import sys
from typing import ClassVar

from core.sandbox import PluginSandbox


class TestPluginSandbox:
    def test_default_init(self):
        sb = PluginSandbox()
        assert sb.max_memory_mb is None
        assert sb.max_cpu_time is None
        assert sb.max_files == 256
        assert sb.max_processes == 32
        assert sb.priority_class == "below_normal"

    def test_custom_init(self):
        sb = PluginSandbox(
            max_memory_mb=128,
            max_cpu_time=60,
            max_files=64,
            max_processes=8,
            priority_class="idle",
        )
        assert sb.max_memory_mb == 128
        assert sb.max_cpu_time == 60
        assert sb.max_files == 64
        assert sb.max_processes == 8
        assert sb.priority_class == "idle"

    def test_popen_kwargs_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        sb = PluginSandbox(priority_class="below_normal")
        kwargs = sb.get_popen_kwargs()
        assert kwargs["creationflags"] == subprocess.BELOW_NORMAL_PRIORITY_CLASS

    def test_popen_kwargs_windows_idle(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        sb = PluginSandbox(priority_class="idle")
        kwargs = sb.get_popen_kwargs()
        assert kwargs["creationflags"] == subprocess.IDLE_PRIORITY_CLASS

    def test_popen_kwargs_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        sb = PluginSandbox()
        kwargs = sb.get_popen_kwargs()
        assert "preexec_fn" in kwargs
        # preexec_fn is callable
        assert callable(kwargs["preexec_fn"])

    def test_linux_preexec_sets_limits(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        sb = PluginSandbox(
            max_memory_mb=64, max_cpu_time=30, max_files=32, max_processes=4
        )

        # Mock resource module
        class FakeResource:
            RLIMIT_AS = 0
            RLIMIT_CPU = 1
            RLIMIT_NOFILE = 2
            RLIMIT_NPROC = 3
            RLIM_INFINITY = -1
            _calls: ClassVar[list] = []

            @staticmethod
            def setrlimit(resource, limits):
                FakeResource._calls.append((resource, limits))

        monkeypatch.setitem(sys.modules, "resource", FakeResource())
        sb._linux_preexec()
        resources = [call[0] for call in FakeResource._calls]
        assert FakeResource.RLIMIT_AS in resources
        assert FakeResource.RLIMIT_CPU in resources
        assert FakeResource.RLIMIT_NOFILE in resources
        assert FakeResource.RLIMIT_NPROC in resources

    def test_is_windows_job_no_crash(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        sb = PluginSandbox()
        # Should not crash even if ctypes/windll aren't available in test env
        result = sb._is_windows_job()
        assert isinstance(result, bool)


class TestSandboxProfiles:
    def test_known_profiles_exist(self):
        from core.sandbox import SANDBOX_PROFILES

        assert set(SANDBOX_PROFILES) == {"light", "moderate", "strict"}

    def test_from_profile_light(self):
        sb = PluginSandbox.from_profile("light")
        assert sb is not None
        assert sb.max_memory_mb == 1024
        assert sb.max_cpu_time is None
        assert sb.max_processes == 64

    def test_from_profile_strict(self):
        sb = PluginSandbox.from_profile("STRICT")
        assert sb is not None
        assert sb.max_memory_mb == 256
        assert sb.max_cpu_time == 900
        assert sb.priority_class == "idle"

    def test_from_profile_unknown_returns_none(self):
        assert PluginSandbox.from_profile("nope") is None
        assert PluginSandbox.from_profile("") is None

    def test_moderate_matches_legacy_defaults(self):
        """The moderate profile equals the historic flat default values."""
        sb = PluginSandbox.from_profile("moderate")
        legacy = PluginSandbox(
            max_memory_mb=512,
            max_cpu_time=3600,
            max_files=256,
            max_processes=32,
            priority_class="below_normal",
        )
        for attr in (
            "max_memory_mb",
            "max_cpu_time",
            "max_files",
            "max_processes",
            "priority_class",
        ):
            assert getattr(sb, attr) == getattr(legacy, attr)

    def test_from_config_profile_wins_over_flat_keys(self):
        cfg = {
            "profile": "light",
            "max_memory_mb": 9999,
            "max_cpu_time": 1,
            "max_files": 8,
            "max_processes": 2,
            "priority_class": "idle",
        }
        sb = PluginSandbox.from_config(cfg)
        assert sb is not None
        assert sb.max_memory_mb == 1024
        assert sb.max_processes == 64

    def test_from_config_empty_profile_uses_flat_keys(self):
        cfg = {"profile": "", "max_memory_mb": 9999, "priority_class": "idle"}
        sb = PluginSandbox.from_config(cfg)
        assert sb is not None
        assert sb.max_memory_mb == 9999
        assert sb.priority_class == "idle"

    def test_from_config_unknown_profile_falls_back(self):
        cfg = {"profile": "bogus", "max_memory_mb": 777}
        sb = PluginSandbox.from_config(cfg)
        assert sb is not None
        assert sb.max_memory_mb == 777

    def test_per_plugin_manifest_override(self, tmp_path):
        """resolve_plugin_sandbox honours sandbox_profile in plugin.json."""
        import json

        from core.sandbox import resolve_plugin_sandbox

        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "sandbox_profile": "strict"}),
            encoding="utf-8",
        )
        global_sb = PluginSandbox.from_profile("light")
        assert global_sb is not None

        sb = resolve_plugin_sandbox(global_sb, "my-plugin", plugin_dir)
        assert sb is not None
        assert sb.max_memory_mb == 256

        # Without override the global sandbox is returned unchanged
        assert resolve_plugin_sandbox(global_sb, "other", tmp_path) is global_sb

        # Unknown profile in manifest -> falls back to the global sandbox
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "sandbox_profile": "bogus"}),
            encoding="utf-8",
        )
        assert resolve_plugin_sandbox(global_sb, "my-plugin", plugin_dir) is global_sb

        # Sandbox disabled -> always None
        assert resolve_plugin_sandbox(None, "my-plugin", plugin_dir) is None
