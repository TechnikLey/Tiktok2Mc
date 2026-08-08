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
