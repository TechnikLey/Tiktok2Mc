"""Plugin sandboxing and resource limits.

Applies OS-level resource restrictions to plugin subprocesses to limit
the blast radius of misbehaving or compromised plugins.

* **Linux** — uses ``resource.setrlimit`` via *preexec_fn* (memory, CPU,
  file descriptors, processes) and lowers niceness.
* **Windows** — lowers process priority.  Optional job-object memory
  limits are applied post-spawn when possible.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Built-in sandbox profiles (J.2 Nr. 10-Rest). Select one globally via
# ``plugin_sandbox.profile`` in config.yaml, or per plugin via
# ``"sandbox_profile"`` in its plugin.json. An empty name keeps the
# legacy behaviour (raw flat keys from config.yaml).
SANDBOX_PROFILES: dict[str, dict[str, Any]] = {
    "light": {
        "max_memory_mb": 1024,
        "max_cpu_time": None,  # no CPU cap
        "max_files": 256,
        "max_processes": 64,
        "priority_class": "below_normal",
    },
    "moderate": {
        "max_memory_mb": 512,
        "max_cpu_time": 3600,
        "max_files": 256,
        "max_processes": 32,
        "priority_class": "below_normal",
    },
    "strict": {
        "max_memory_mb": 256,
        "max_cpu_time": 900,
        "max_files": 128,
        "max_processes": 8,
        "priority_class": "idle",
    },
}


class PluginSandbox:
    """Configure and apply cross-platform resource limits for plugins."""

    def __init__(
        self,
        max_memory_mb: int | None = None,
        max_cpu_time: int | None = None,
        max_files: int = 256,
        max_processes: int = 32,
        priority_class: str | None = "below_normal",
    ):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_time = max_cpu_time
        self.max_files = max_files
        self.max_processes = max_processes
        self.priority_class = priority_class

    @classmethod
    def from_profile(cls, profile: str) -> PluginSandbox | None:
        """Build a sandbox from a built-in profile name.

        Returns ``None`` for unknown names so callers can fall back to
        the legacy flat config keys with a warning.
        """
        preset = SANDBOX_PROFILES.get(str(profile or "").strip().lower())
        if preset is None:
            return None
        return cls(**preset)

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> PluginSandbox | None:
        """Build a sandbox from a ``plugin_sandbox`` config section.

        When ``profile`` names a built-in profile it wins over the flat
        keys; otherwise the raw values are used (legacy behaviour).
        """
        profile = str(cfg.get("profile", "") or "").strip()
        if profile:
            sb = cls.from_profile(profile)
            if sb is not None:
                return sb
            log.warning(
                "[SANDBOX] Unknown plugin_sandbox.profile %r — using flat keys",
                profile,
            )
        return cls(
            max_memory_mb=cfg.get("max_memory_mb"),
            max_cpu_time=cfg.get("max_cpu_time"),
            max_files=cfg.get("max_files", 256),
            max_processes=cfg.get("max_processes", 32),
            priority_class=cfg.get("priority_class", "below_normal"),
        )

    # -----------------------------------------------------------------
    # Windows helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _is_windows_job() -> bool:
        """Return ``True`` if the current process is already in a job."""
        try:
            import ctypes
        except ImportError:
            return False
        kernel = ctypes.windll.kernel32
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            return False
        info = ctypes.c_int()
        ret = kernel.IsProcessInJob(kernel.GetCurrentProcess(), job, ctypes.byref(info))
        kernel.CloseHandle(job)
        return bool(info.value) if ret else False

    def _apply_windows_job(self, proc: subprocess.Popen) -> None:
        """Assign *proc* to a new job object with memory limits."""
        try:
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.windll.kernel32
            job = kernel.CreateJobObjectW(None, None)
            if not job:
                return

            # JOBOBJECT_EXTENDED_LIMIT_INFORMATION (simplified)
            # We only set the process memory limit flag and value.
            class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", wintypes.LARGE_INTEGER * 8),
                    ("IoInfo", wintypes.ULARGE_INTEGER * 8),
                    ("ProcessMemoryLimit", wintypes.LARGE_INTEGER),
                    ("JobMemoryLimit", wintypes.LARGE_INTEGER),
                    ("PeakProcessMemoryUsed", wintypes.LARGE_INTEGER),
                    ("PeakJobMemoryLimit", wintypes.LARGE_INTEGER),
                ]

            mem_limit = (self.max_memory_mb or 512) * 1024 * 1024
            jobli = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            jobli.BasicLimitInformation = (wintypes.LARGE_INTEGER * 8)(
                *(0 for _ in range(8))
            )
            # JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00001000
            jobli.BasicLimitInformation[0] = 0x00001000
            jobli.ProcessMemoryLimit = mem_limit

            kernel.SetInformationJobObject(
                job,
                9,  # JobObjectExtendedLimitInformation
                ctypes.byref(jobli),
                ctypes.sizeof(jobli),
            )
            handle = ctypes.c_void_p(proc._handle)
            kernel.AssignProcessToJobObject(job, handle)
            log.debug(
                "Assigned plugin PID %d to job object (mem limit %d MB)",
                proc.pid,
                self.max_memory_mb or 512,
            )
        except (OSError, TypeError, AttributeError) as exc:
            log.debug("Failed to apply Windows job object: %s", exc)

    # -----------------------------------------------------------------
    # Linux helpers
    # -----------------------------------------------------------------
    def _linux_preexec(self) -> None:
        """preexec_fn for Linux ``Popen`` calls."""
        import resource

        if self.max_memory_mb:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.max_memory_mb * 1024 * 1024, resource.RLIM_INFINITY),
            )
        if self.max_cpu_time:
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.max_cpu_time, resource.RLIM_INFINITY),
            )
        if self.max_files:
            resource.setrlimit(
                resource.RLIMIT_NOFILE,
                (self.max_files, resource.RLIM_INFINITY),
            )
        if self.max_processes:
            resource.setrlimit(
                resource.RLIMIT_NPROC,
                (self.max_processes, resource.RLIM_INFINITY),
            )
        try:
            os.nice(10)
        except (
            OSError,
            AttributeError,
        ):  # best-effort priority lowering (os.nice absent on Windows)
            pass

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def get_popen_kwargs(self) -> dict[str, Any]:
        """Return keyword arguments to merge into ``subprocess.Popen``."""
        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            flags = 0
            if self.priority_class == "below_normal":
                flags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
            elif self.priority_class == "idle":
                flags |= subprocess.IDLE_PRIORITY_CLASS
            kwargs["creationflags"] = flags
        else:
            kwargs["preexec_fn"] = self._linux_preexec
        return kwargs

    def apply_post_spawn(self, proc: subprocess.Popen) -> None:
        """Apply restrictions that must be set after the process starts."""
        if sys.platform == "win32" and self.max_memory_mb:
            self._apply_windows_job(proc)


def resolve_plugin_sandbox(
    global_sandbox: PluginSandbox | None,
    plugin_name: str,
    plugin_dir,
) -> PluginSandbox | None:
    """Resolve the sandbox for a single plugin (J.2 Nr. 10-Rest).

    A valid ``"sandbox_profile"`` in the plugin's ``plugin.json`` overrides
    the global profile/config. Returns ``None`` when sandboxing is off
    (``global_sandbox is None``). Manifest problems fall back to the
    global sandbox so plugins always launch.
    """
    if global_sandbox is None:
        return None
    try:
        manifest_file = Path(plugin_dir) / "plugin.json"
        if manifest_file.is_file():
            import json

            with manifest_file.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            profile = str(raw.get("sandbox_profile", "") or "").strip()
            if profile:
                sb = PluginSandbox.from_profile(profile)
                if sb is not None:
                    log.info(
                        "[SANDBOX] Plugin '%s' uses profile '%s'",
                        plugin_name,
                        profile,
                    )
                    return sb
                log.warning(
                    "[SANDBOX] Plugin '%s' declares unknown sandbox_profile %r "
                    "— falling back to global config",
                    plugin_name,
                    profile,
                )
    except (OSError, ValueError) as exc:
        log.warning("[SANDBOX] Manifest read failed for '%s': %s", plugin_name, exc)
    return global_sandbox
