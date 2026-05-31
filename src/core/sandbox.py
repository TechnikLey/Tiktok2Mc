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
from typing import Any

log = logging.getLogger(__name__)


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
        ret = kernel.IsProcessInJob(
            kernel.GetCurrentProcess(), job, ctypes.byref(info)
        )
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
        except Exception as exc:
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
        except Exception:
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
