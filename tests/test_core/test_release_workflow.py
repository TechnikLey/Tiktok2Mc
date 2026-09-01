"""Tests for the CI release workflow (Linux portable archive).

These tests verify that the GitHub Actions release workflow produces the
portable ``Linux.tar.gz`` from the build runner's own artifact rather than
re-archiving a downloaded bundle. Re-archiving the downloaded bundle broke
under GitHub's 2 GiB release-asset limit, because ``upload-artifact@v4``
dereferences the shared PyQt6 runtime symlinks and inflates the bundle many
times over before it is downloaded again.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build.yml"
BUILD_PY = REPO_ROOT / "build.py"


class TestBuildWorkflowArchiveSteps:
    """Verify the workflow creates the Linux archive on the build runner."""

    def test_workflow_file_exists(self):
        assert WORKFLOW.exists(), f"build.yml not found at {WORKFLOW}"

    def test_linux_portable_archive_uploaded_from_build_dir(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        assert "TikTok2Mc-Linux-Archive" in content
        assert "path: build/TikTok2Mc-Linux.tar.gz" in content
        assert "Upload Linux Portable Archive (Linux only)" in content
        assert "if: matrix.os == 'ubuntu-latest'" in content

    def test_linux_portable_archive_downloaded_before_release(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        assert "Download Linux Portable Archive" in content
        assert "name: TikTok2Mc-Linux-Archive" in content
        assert "path: archive-linux/" in content

    def test_create_archives_copies_archive_artifact(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        assert (
            "cp archive-linux/TikTok2Mc-Linux.tar.gz "
            "./TikTok2Mc-${{ github.ref_name }}-Linux.tar.gz"
        ) in content
        assert "sha256sum TikTok2Mc-${{ github.ref_name }}-Linux.tar.gz" in content

    def test_create_archives_does_not_retar_downloaded_bundle(self):
        """Regression guard: re-archiving the downloaded bundle broke the 2 GiB limit."""
        content = WORKFLOW.read_text(encoding="utf-8")
        # Only the Windows bundle is zipped in Create Archives; the Linux bundle
        # must never be re-archived from download-artifact output here.
        assert "tar -czf" not in content
        assert "-C build-linux ." not in content

    def test_release_files_list_includes_linux_archive(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        archive = "TikTok2Mc-${{ github.ref_name }}-Linux.tar.gz"
        assert archive in content
        assert f"{archive}.sha256" in content

    def test_workflow_comment_explains_symlink_reason(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        assert "upload-artifact dereferences" in content
        assert "2 GiB" in content


class TestBuildWaypointIntegrity:
    """Verify the build.py archive extraction still keeps symlinks intact.

    The Linux portable archive stays small only because the shared PyQt6
    runtime appears once as a real directory while every consumer references
    it via symlink. Re-archiving with dereference (or via an artifact round
    trip) would duplicate multi-GiB runtime copies and exceed the 2 GiB cap.
    """

    def test_build_py_linux_installer_tar_includes_symlinks(self):
        content = BUILD_PY.read_text(encoding="utf-8")
        assert "entry.is_symlink()" in content
        assert 'tarfile.open(tar_path, "w:gz")' in content

    def test_build_py_uses_default_non_dereferencing_tarfile(self):
        content = BUILD_PY.read_text(encoding="utf-8")
        # tarfile.add() only follows symlinks when dereference=True is passed;
        # the installer tar must store them as links to stay small.
        assert "dereference=True" not in content
