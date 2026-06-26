"""Isolation safety tests.

These verify that the write guard is active and that no files outside the
dedicated test workspace were modified during the test session.
"""

import tempfile
from pathlib import Path

import pytest


class TestWriteGuardIsActive:
    """Prove that the write guard blocks writes outside tests/workspace/."""

    def test_guard_blocks_path_write_text(self):
        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_write_text.txt"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            blocked.write_text("must fail")

    def test_guard_blocks_path_write_bytes(self):
        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_write_bytes.bin"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            blocked.write_bytes(b"must fail")

    def test_guard_blocks_path_mkdir(self):
        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_mkdir"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            blocked.mkdir()

    def test_guard_blocks_path_touch(self):
        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_touch.txt"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            blocked.touch()

    def test_guard_blocks_path_unlink(self):
        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_unlink.txt"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            blocked.unlink(missing_ok=True)

    def test_guard_blocks_open_for_write(self):
        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_open.txt"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            with open(blocked, "w") as fh:
                fh.write("must fail")

    def test_guard_blocks_os_makedirs(self):
        import os

        blocked = Path(__file__).resolve().parent.parent / "src" / "guard_test_os_makedirs"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            os.makedirs(blocked)

    def test_guard_blocks_shutil_copy(self, tmp_path):
        import shutil

        src = tmp_path / "src.txt"
        src.write_text("hello")
        dst = Path(__file__).resolve().parent.parent / "src" / "guard_test_shutil_copy.txt"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            shutil.copy(src, dst)

    def test_guard_blocks_shutil_rmtree(self):
        import shutil

        blocked = Path(__file__).resolve().parent.parent / "src"
        with pytest.raises(PermissionError, match="TEST GUARD"):
            shutil.rmtree(blocked)

    def test_guard_allows_writes_inside_workspace(self, tmp_path):
        """Sanity-check that the guard does NOT block allowed writes."""
        allowed = tmp_path / "allowed.txt"
        allowed.write_text("success")
        assert allowed.read_text() == "success"


class TestNoProjectFilesModified:
    """Post-hoc verification that the project tree is untouched."""

    def test_no_project_files_modified(self, request):
        before = request.config.stash.get("isolation_snapshot_before", None)
        project_root = request.config.stash.get("isolation_project_root", None)
        assert before is not None, "Session snapshot was not recorded"

        after = {}
        for p in project_root.rglob("*"):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(project_root)
            except ValueError:
                continue
            skip = False
            for part in rel.parts:
                if part in (
                    ".git",
                    ".pytest_cache",
                    "workspace",
                    "__pycache__",
                    ".tmp_path_factory",
                ):
                    skip = True
                    break
            if skip:
                continue
            try:
                stat = p.stat()
                after[str(rel)] = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                pass

        changes = []
        for path, data in after.items():
            if path not in before:
                changes.append(f"CREATED: {path}")
            elif before[path] != data:
                changes.append(f"MODIFIED: {path}")
        for path in before:
            if path not in after:
                changes.append(f"DELETED: {path}")

        assert not changes, (
            "SESSION ISOLATION VIOLATION: files outside tests/workspace/ "
            "were modified during test execution:\n"
            + "\n".join(changes[:50])
        )
