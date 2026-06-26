"""Test isolation write guard.

Patches common file-system write operations so that any attempt to
modify files outside the dedicated test workspace raises an immediate
``PermissionError``.  Reads are never blocked.
"""

import builtins
import io
import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Set

logger = logging.getLogger("test_guard")


class WriteGuard:
    """Blocks file-system writes outside the allowed test roots."""

    def __init__(self, allowed_roots: Set[Path]):
        self.allowed_roots = frozenset(Path(p).resolve() for p in allowed_roots)
        self._originals: dict = {}
        self._active = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_allowed(self, path) -> bool:
        """Return *True* if *path* is inside an allowed root or system temp."""
        try:
            resolved = Path(path).resolve()
        except (TypeError, ValueError):
            return False

        for allowed in self.allowed_roots:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                pass

        # Allow pytest internals / system temp (but log a warning).
        try:
            resolved.relative_to(Path(tempfile.gettempdir()).resolve())
            return True
        except ValueError:
            pass

        return False

    def _check(self, path, operation: str):
        if not self._is_allowed(path):
            msg = (
                f"[TEST GUARD] Blocked {operation} on {path}. "
                f"All test writes must go under the dedicated test workspace."
            )
            logger.warning(msg)
            raise PermissionError(msg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._active:
            return
        self._active = True
        guard = self

        # -- pathlib.Path ------------------------------------------------
        self._originals["Path.write_text"] = Path.write_text
        self._originals["Path.write_bytes"] = Path.write_bytes
        self._originals["Path.mkdir"] = Path.mkdir
        self._originals["Path.touch"] = Path.touch
        self._originals["Path.rename"] = Path.rename
        self._originals["Path.replace"] = Path.replace
        self._originals["Path.unlink"] = Path.unlink
        self._originals["Path.rmdir"] = Path.rmdir
        self._originals["Path.chmod"] = Path.chmod

        def _write_text(self, *args, **kwargs):
            guard._check(self, "Path.write_text")
            return guard._originals["Path.write_text"](self, *args, **kwargs)

        def _write_bytes(self, *args, **kwargs):
            guard._check(self, "Path.write_bytes")
            return guard._originals["Path.write_bytes"](self, *args, **kwargs)

        def _mkdir(self, *args, **kwargs):
            guard._check(self, "Path.mkdir")
            return guard._originals["Path.mkdir"](self, *args, **kwargs)

        def _touch(self, *args, **kwargs):
            guard._check(self, "Path.touch")
            return guard._originals["Path.touch"](self, *args, **kwargs)

        def _rename(self, target, *args, **kwargs):
            guard._check(self, "Path.rename(source)")
            guard._check(target, "Path.rename(target)")
            return guard._originals["Path.rename"](self, target, *args, **kwargs)

        def _replace(self, target, *args, **kwargs):
            guard._check(self, "Path.replace(source)")
            guard._check(target, "Path.replace(target)")
            return guard._originals["Path.replace"](self, target, *args, **kwargs)

        def _unlink(self, *args, **kwargs):
            guard._check(self, "Path.unlink")
            return guard._originals["Path.unlink"](self, *args, **kwargs)

        def _rmdir(self, *args, **kwargs):
            guard._check(self, "Path.rmdir")
            return guard._originals["Path.rmdir"](self, *args, **kwargs)

        def _chmod(self, *args, **kwargs):
            guard._check(self, "Path.chmod")
            return guard._originals["Path.chmod"](self, *args, **kwargs)

        Path.write_text = _write_text
        Path.write_bytes = _write_bytes
        Path.mkdir = _mkdir
        Path.touch = _touch
        Path.rename = _rename
        Path.replace = _replace
        Path.unlink = _unlink
        Path.rmdir = _rmdir
        Path.chmod = _chmod

        # -- os.* --------------------------------------------------------
        self._originals["os.makedirs"] = os.makedirs
        self._originals["os.mkdir"] = os.mkdir
        self._originals["os.remove"] = os.remove
        self._originals["os.rmdir"] = os.rmdir
        self._originals["os.rename"] = os.rename
        self._originals["os.open"] = os.open

        def _os_makedirs(name, *args, **kwargs):
            guard._check(name, "os.makedirs")
            return guard._originals["os.makedirs"](name, *args, **kwargs)

        def _os_mkdir(name, *args, **kwargs):
            guard._check(name, "os.mkdir")
            return guard._originals["os.mkdir"](name, *args, **kwargs)

        def _os_remove(name, *args, **kwargs):
            guard._check(name, "os.remove")
            return guard._originals["os.remove"](name, *args, **kwargs)

        def _os_rmdir(name, *args, **kwargs):
            guard._check(name, "os.rmdir")
            return guard._originals["os.rmdir"](name, *args, **kwargs)

        def _os_rename(src, dst, *args, **kwargs):
            guard._check(src, "os.rename(src)")
            guard._check(dst, "os.rename(dst)")
            return guard._originals["os.rename"](src, dst, *args, **kwargs)

        def _os_open(path, flags, *args, **kwargs):
            write_flags = (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            )
            if flags & write_flags:
                guard._check(path, "os.open")
            return guard._originals["os.open"](path, flags, *args, **kwargs)

        os.makedirs = _os_makedirs
        os.mkdir = _os_mkdir
        os.remove = _os_remove
        os.rmdir = _os_rmdir
        os.rename = _os_rename
        os.open = _os_open

        # -- shutil.* ----------------------------------------------------
        self._originals["shutil.copy"] = shutil.copy
        self._originals["shutil.copy2"] = shutil.copy2
        self._originals["shutil.move"] = shutil.move
        self._originals["shutil.copytree"] = shutil.copytree
        self._originals["shutil.rmtree"] = shutil.rmtree

        def _shutil_copy(src, dst, *args, **kwargs):
            guard._check(dst, "shutil.copy(dst)")
            return guard._originals["shutil.copy"](src, dst, *args, **kwargs)

        def _shutil_copy2(src, dst, *args, **kwargs):
            guard._check(dst, "shutil.copy2(dst)")
            return guard._originals["shutil.copy2"](src, dst, *args, **kwargs)

        def _shutil_move(src, dst, *args, **kwargs):
            guard._check(src, "shutil.move(src)")
            guard._check(dst, "shutil.move(dst)")
            return guard._originals["shutil.move"](src, dst, *args, **kwargs)

        def _shutil_copytree(src, dst, *args, **kwargs):
            guard._check(dst, "shutil.copytree(dst)")
            return guard._originals["shutil.copytree"](src, dst, *args, **kwargs)

        def _shutil_rmtree(path, *args, **kwargs):
            guard._check(path, "shutil.rmtree")
            return guard._originals["shutil.rmtree"](path, *args, **kwargs)

        shutil.copy = _shutil_copy
        shutil.copy2 = _shutil_copy2
        shutil.move = _shutil_move
        shutil.copytree = _shutil_copytree
        shutil.rmtree = _shutil_rmtree

        # -- builtins.open / io.open -------------------------------------
        self._originals["builtins.open"] = builtins.open
        self._originals["io.open"] = io.open

        def _open(file, mode="r", *args, **kwargs):
            if isinstance(file, int):
                return guard._originals["builtins.open"](
                    file, mode, *args, **kwargs
                )
            write_modes = ("w", "a", "x", "r+", "w+", "a+", "x+")
            if any(str(mode).startswith(m) for m in write_modes):
                guard._check(file, f"open(mode={mode})")
            return guard._originals["builtins.open"](file, mode, *args, **kwargs)

        builtins.open = _open
        io.open = _open

        logger.info(
            "Test write guard activated. Allowed roots: %s",
            [str(p) for p in self.allowed_roots],
        )

    def stop(self):
        if not self._active:
            return
        self._active = False

        Path.write_text = self._originals["Path.write_text"]
        Path.write_bytes = self._originals["Path.write_bytes"]
        Path.mkdir = self._originals["Path.mkdir"]
        Path.touch = self._originals["Path.touch"]
        Path.rename = self._originals["Path.rename"]
        Path.replace = self._originals["Path.replace"]
        Path.unlink = self._originals["Path.unlink"]
        Path.rmdir = self._originals["Path.rmdir"]
        Path.chmod = self._originals["Path.chmod"]

        os.makedirs = self._originals["os.makedirs"]
        os.mkdir = self._originals["os.mkdir"]
        os.remove = self._originals["os.remove"]
        os.rmdir = self._originals["os.rmdir"]
        os.rename = self._originals["os.rename"]
        os.open = self._originals["os.open"]

        shutil.copy = self._originals["shutil.copy"]
        shutil.copy2 = self._originals["shutil.copy2"]
        shutil.move = self._originals["shutil.move"]
        shutil.copytree = self._originals["shutil.copytree"]
        shutil.rmtree = self._originals["shutil.rmtree"]

        builtins.open = self._originals["builtins.open"]
        io.open = self._originals["io.open"]

        logger.info("Test write guard deactivated.")
