"""End-to-end update validation tests (P3a pointer architecture).

Covers the full update flow the compiled update.exe performs:

- CHECK  local version resolution (pointer → version.txt) + release check
- FETCH  asset selection, download, manifest/.sig fetch
- VERIFY_SIG  detached Ed25519 manifest signature (fail closed)
- VERIFY_SHA  archive .sha256 + per-file manifest checksums
- STAGE  staged ``app-<ver>/`` move into the install root
- FLIP   atomic ``current.json`` pointer flip (rollback data)
- PRUNE  old app version dirs (one rollback generation kept)
- NOTIFY progress file + relaunch in ``--auto`` mode

The old whitelist-copy / kill-signal choreography is gone; running
processes are never touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import python.update
from core.update_engine import manifest as manifest_mod
from core.update_engine.pointer import AppPointer, read_pointer, write_pointer

TAG = "v1.0.0"
TOOL = "1.0.0"
UPDATER = "0.3.0"


# =========================================================================
# Fixtures / helpers
# =========================================================================


def _runtime_suffix() -> str:
    return python.update.SUFFIX


def _archive_asset(platform: str) -> tuple[str, str]:
    """Return (asset_name, url) for the platform archive."""
    if platform == "win32":
        return "Tiktok2Mc_v1.0.0_Windows.zip", "https://fake/Windows.zip"
    return "Tiktok2Mc_v1.0.0_Linux.tar.gz", "https://fake/Linux.tar.gz"


def _release_payload(
    *,
    tag: str = TAG,
    with_archive: bool = True,
    with_manifest: bool = True,
    with_sig: bool = True,
    with_sha256: bool = True,
    platform: str = "win32",
) -> dict:
    assets: list[dict] = []
    if with_archive:
        name, url = _archive_asset(platform)
        assets.append({"name": name, "url": url})
    if with_manifest:
        assets.append({"name": "manifest.json", "url": "https://fake/manifest.json"})
    if with_sig:
        assets.append(
            {"name": "manifest.json.sig", "url": "https://fake/manifest.json.sig"}
        )
    if with_sha256 and with_archive:
        name, _ = _archive_asset(platform)
        assets.append({"name": name + ".sha256", "url": "https://fake/x.sha256"})
    return {"tag_name": tag, "assets": assets}


def _release_content(tool: str = TOOL, updater: str = UPDATER) -> dict[str, bytes]:
    """The extracted release zip content (root-relative, POSIX paths)."""
    suffix = _runtime_suffix()
    app = f"app-{tool}"
    return {
        f"{app}/version.txt": f"ToolVersion: {tool}\n".encode("utf-8"),
        f"{app}/core/app{suffix}": b"new-app-binary",
        f"{app}/core/gui{suffix}": b"new-gui-binary",
        f"{app}/core/update{suffix}": b"new-updater-binary",
        f"start{suffix}": b"new-start-binary",
        f"update{suffix}": b"new-update-binary",
        "current.json": json.dumps(
            {"active_app_dir": app, "tool_version": tool}
        ).encode("utf-8"),
        "version.txt": (f"ToolVersion: {tool}\nUpdaterVersion: {updater}\n").encode(
            "utf-8"
        ),
    }


def _signed_manifest(
    files: dict[str, bytes], *, key: Ed25519PrivateKey | None = None
) -> tuple[bytes, bytes, str]:
    """Serialize + sign a manifest over *files*; return (raw, sig, pub_hex)."""
    private_key = key or Ed25519PrivateKey.generate()
    from core.update_engine.manifest import Manifest, ManifestFile

    entries = [
        ManifestFile(
            path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
        for path, data in sorted(files.items())
    ]
    manifest = Manifest(
        tool_version=TOOL,
        config_version_expected="1.0",
        files=tuple(entries),
        updater_version=UPDATER,
        channel="stable",
        created_utc="2026-01-01T00:00:00Z",
    )
    raw = manifest_mod.serialize_manifest(manifest)
    signature = private_key.sign(raw)
    return raw, signature, private_key.public_key().public_bytes_raw().hex()


def _make_install(tmp_path: Path, tool: str = "0.9.0", updater: str = "0.1.0") -> Path:
    """A realistic pre-P3a flat install under tmp_path/install."""
    suffix = _runtime_suffix()
    base = tmp_path / "install"
    core = base / "core"
    core.mkdir(parents=True)
    (core / f"app{suffix}").write_bytes(b"old-app-binary")
    (core / f"gui{suffix}").write_bytes(b"old-gui-binary")
    (base / "runtime_marker").write_text("x", encoding="utf-8")
    config = base / "config"
    config.mkdir(exist_ok=True)
    (config / "config.yaml").write_text("config_version: '0.9'\n", encoding="utf-8")
    (base / "version.txt").write_text(
        f"ToolVersion: {tool}\nUpdaterVersion: {updater}\n", encoding="utf-8"
    )
    (base / f"start{suffix}").write_bytes(b"old-start-binary")
    (base / f"update{suffix}").write_bytes(b"old-update-binary")
    return base


# =========================================================================
# Local version resolution (CHECK)
# =========================================================================


class TestLocalVersionResolution:
    def test_prefers_pointer(self, tmp_path):
        write_pointer(
            tmp_path, AppPointer(active_app_dir="app-1.0.0", tool_version="1.2.3")
        )
        (tmp_path / "version.txt").write_text("ToolVersion: 0.1.0\n")
        assert python.update.get_local_tool_version(tmp_path) == "1.2.3"

    def test_falls_back_to_version_txt(self, tmp_path):
        (tmp_path / "version.txt").write_text("ToolVersion: 0.7.0\n")
        assert python.update.get_local_tool_version(tmp_path) == "0.7.0"

    def test_missing_everything(self, tmp_path):
        assert python.update.get_local_tool_version(tmp_path) == "0.0.0"


class TestSelectAsset:
    @pytest.mark.parametrize("platform", ["win32", "linux"])
    def test_platform_selection(self, tmp_path, platform):
        payload = _release_payload(platform=platform)
        with patch.object(python.update.sys, "platform", platform):
            asset, archive_name = python.update._select_asset(payload)
        assert asset is not None
        name, _ = _archive_asset(platform)
        assert asset["name"] == name
        assert archive_name in ("release.zip", "release.tar.gz")

    def test_no_assets(self, tmp_path):
        asset, _archive_name = python.update._select_asset({"assets": []})
        assert asset is None


# =========================================================================
# Orchestration
# =========================================================================


class TestRunUpdateOrchestration:
    """Full run_update() flow with mocked external dependencies."""

    @contextmanager
    def _flow(
        self,
        tmp_path: Path,
        release: dict,
        files: dict[str, bytes] | None = None,
        release_files: dict[str, bytes] | None = None,
        manifest_raw: bytes | None = None,
        sig_raw: bytes | None = None,
        pub_key_hex: str | None = None,
        verify_checksum_result: bool = True,
        download_error: Exception | None = None,
        local_tool: str = "0.9.0",
    ):
        """Set up a complete, patched run_update() environment.

        Yields ``(exit_mock, phases, base_dir)``.
        """
        files = files if files is not None else _release_content()
        manifest_raw_signed, sig_signed, key_hex = _signed_manifest(
            release_files or files
        )
        manifest_raw = manifest_raw if manifest_raw is not None else manifest_raw_signed
        sig_raw = sig_raw if sig_raw is not None else sig_signed

        base = _make_install(tmp_path, tool=local_tool)
        temp_dir = base / "_update_tmp"
        status_file = tmp_path / "update_status.json"

        # patched python.update.sys ("win32" default) selects zip extraction
        platform = getattr(self, "_forced_platform", "win32")

        archive_bytes = b"ARCHIVEDATA"

        release_resp = MagicMock()
        release_resp.status_code = 200
        release_resp.json.return_value = release

        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.content = manifest_raw

        sig_resp = MagicMock()
        sig_resp.status_code = 200
        sig_resp.content = sig_raw

        sha_resp = MagicMock()
        sha_resp.status_code = 200
        sha_resp.text = hashlib.sha256(archive_bytes).hexdigest() + "  x\n"

        def mock_get(url, **_kwargs):
            if "releases/latest" in url:
                return release_resp
            if url.endswith("/manifest.json"):
                return manifest_resp
            if url.endswith("/manifest.json.sig"):
                return sig_resp
            if url.endswith(".sha256"):
                return sha_resp
            raise AssertionError(f"unexpected URL: {url}")

        recorded_phases: list[tuple] = []

        def capture_phase(phase, progress=None, message=""):
            recorded_phases.append((phase, progress, message))

        def fake_download(url, target):
            if download_error is not None:
                raise download_error
            Path(target).write_bytes(archive_bytes)

        with ExitStack() as stack:
            ctx = [
                patch.object(python.update.sys, "platform", platform),
                patch.object(python.update, "BASE_DIR", base),
                patch.object(python.update, "TEMP_DIR", temp_dir),
                patch.object(
                    python.update, "START_FILE", base / f"start{_runtime_suffix()}"
                ),
                patch.object(python.update, "VERSION_FILE", base / "version.txt"),
                patch.object(python.update, "UPDATE_STATUS_FILE", status_file),
                patch.object(python.update, "AUTO_MODE", True),
                patch.object(python.update, "cfg", {"auto_update_config": False}),
                patch.object(python.update, "GITHUB_TOKEN", None),
                patch.object(
                    python.update, "SIGNING_PUBLIC_KEY", pub_key_hex or key_hex
                ),
                patch.object(python.update, "wait_for_key"),
                patch("python.update.requests.get", side_effect=mock_get),
                patch(
                    "python.update.download_with_progress", side_effect=fake_download
                ),
                patch("python.update._write_update_status", side_effect=capture_phase),
                patch("python.update._relaunch_tool_after_update", return_value=True),
                patch(
                    "python.update.verify_checksum",
                    return_value=verify_checksum_result,
                ),
                patch("python.update.sys.exit", side_effect=SystemExit),
            ]

            # Extraction layer depends on the forced platform
            if platform == "win32":

                def populate(dest):
                    for rel, data in files.items():
                        p = Path(dest) / rel
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(data)

                stack.enter_context(
                    patch("python.update.tarfile.open", autospec=True)
                )  # unused on win32 but keeps the mock surface identical

                zf = stack.enter_context(patch("python.update.zipfile.ZipFile"))
                zf.return_value.__enter__.return_value.extractall = lambda dest, **_kw: (
                    populate(dest)
                )
            else:
                tar_mock = stack.enter_context(patch("python.update.tarfile.open"))
                tar_ctx = tar_mock.return_value.__enter__.return_value
                tar_ctx.getmembers.return_value = []

                def populate(dest):
                    for rel, data in files.items():
                        p = Path(dest) / rel
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(data)

                tar_ctx.extractall = lambda dest, **_kw: populate(dest)

            entered = [stack.enter_context(c) for c in ctx]
            exit_mock = entered[-1]
            yield exit_mock, recorded_phases, base

    # -----------------------------------------------------------------
    # Happy path
    # -----------------------------------------------------------------

    @pytest.mark.parametrize("platform", ["win32", "linux"])
    def test_full_update_lifecycle(self, tmp_path, platform):
        """0.9 → 1.0: stage → flip → prune → notify with real files."""
        self._forced_platform = platform
        base_dir = tmp_path / "install"
        # Seed an old pointer + previous version dir so FLIP/PRUNE are exercised.
        old_app_dir = base_dir / "app-0.9.0"
        old_app_dir.mkdir(parents=True)
        (old_app_dir / "core").mkdir()
        (old_app_dir / "core" / f"app{_runtime_suffix()}").write_bytes(
            b"old-app-binary"
        )
        ancient = base_dir / "app-0.8.0"
        ancient.mkdir()
        write_pointer(base_dir, AppPointer("app-0.9.0", "0.9.0", previous_app_dir=None))

        with (
            self._flow(tmp_path, _release_payload(platform=platform)) as (
                exit_mock,
                phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()

        exit_mock.assert_called_once_with(0)

        app_dir = base_dir / "app-1.0.0"
        assert (app_dir / "core" / f"app{_runtime_suffix()}").read_bytes() == (
            b"new-app-binary"
        )
        assert (app_dir / "core" / f"gui{_runtime_suffix()}").is_file()

        pointer = read_pointer(base_dir)
        assert pointer is not None
        assert pointer.active_app_dir == "app-1.0.0"
        assert pointer.tool_version == "1.0.0"
        assert pointer.previous_app_dir == "app-0.9.0"

        # PRUNE: the rollback generation (0.9.0) survives, 0.8.0 is removed.
        assert not ancient.exists()
        assert old_app_dir.exists()
        assert app_dir.exists()

        # Legacy version file synced for pre-P3a readers.
        version_txt = (base_dir / "version.txt").read_text(encoding="utf-8")
        assert "ToolVersion: 1.0.0" in version_txt
        assert "UpdaterVersion: 0.3.0" in version_txt

        # Launcher binaries are queued, not overwritten (running process!).
        assert (base_dir / f"start_new{_runtime_suffix()}").read_bytes() == (
            b"new-start-binary"
        )
        assert (base_dir / f"start{_runtime_suffix()}").read_bytes() == (
            b"old-start-binary"
        )

        # Temp dir cleaned up, progress phases complete.
        assert not (base_dir / "_update_tmp").exists()
        assert phases[0][0] == "checking"
        assert any(p[0] == "downloading" for p in phases)
        assert any(p[0] == "installing" for p in phases)
        assert phases[-1][0] == "done"

    # -----------------------------------------------------------------
    # CHECK variations
    # -----------------------------------------------------------------

    def test_up_to_date_skips_update(self, tmp_path):
        self._forced_platform = "win32"
        write_pointer(tmp_path / "install", AppPointer("app-1.0.0", "1.0.0"))
        with (
            self._flow(
                tmp_path,
                _release_payload(),
                local_tool="1.0.0",
            ) as (exit_mock, _phases, _base),
            pytest.raises(SystemExit),
        ):
            # pointer already names the newest version → nothing to do
            python.update.run_update()
        exit_mock.assert_called_once_with(5)

    def test_beta_skipped_in_auto_mode(self, tmp_path):
        self._forced_platform = "win32"
        with (
            self._flow(tmp_path, _release_payload(tag="v1.1.0-beta")) as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(5)

    def test_transient_api_error_is_retried(self, tmp_path):
        """A transient network failure must be retried (backoff), then
        the flow continues — here it ends benignly with 'no update'."""
        self._forced_platform = "win32"
        release = _release_payload(tag="v0.9.0")
        release_resp = MagicMock()
        release_resp.status_code = 200
        release_resp.json.return_value = release
        calls: list = []

        def mock_get(url, **_kw):
            calls.append(url)
            if "releases/latest" in url and len(calls) == 1:
                raise requests.exceptions.ConnectionError("DNS hiccup")
            if "releases/latest" in url:
                return release_resp
            raise AssertionError(f"unexpected URL: {url}")

        base = _make_install(tmp_path)
        temp_dir = base / "_update_tmp"
        with (
            patch.object(python.update, "BASE_DIR", base),
            patch.object(python.update, "TEMP_DIR", temp_dir),
            patch.object(python.update, "START_FILE", base / "start.exe"),
            patch.object(python.update, "VERSION_FILE", base / "version.txt"),
            patch.object(
                python.update,
                "UPDATE_STATUS_FILE",
                tmp_path / "update_status.json",
            ),
            patch.object(python.update, "AUTO_MODE", True),
            patch.object(python.update, "wait_for_key"),
            patch("python.update.requests.get", side_effect=mock_get),
            patch("python.update.time.sleep"),
            patch("python.update.sys.exit", side_effect=SystemExit),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        assert len(calls) == 2  # retry happened

    def test_no_platform_asset(self, tmp_path):
        self._forced_platform = "win32"
        with (
            self._flow(tmp_path, _release_payload(with_archive=False)) as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(11)

    def test_download_failure(self, tmp_path):
        self._forced_platform = "win32"
        with (
            self._flow(
                tmp_path,
                _release_payload(),
                download_error=requests.exceptions.ConnectionError("drop"),
            ) as (exit_mock, _phases, _base),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(14)

    # -----------------------------------------------------------------
    # VERIFY_SIG / VERIFY_SHA
    # -----------------------------------------------------------------

    def test_signature_mismatch_rejects_update(self, tmp_path):
        """Manifest signed by someone else must be rejected with code 16."""
        self._forced_platform = "win32"
        files = _release_content()
        _raw, _sig, attacker_hex = _signed_manifest(files)
        wrong_key = Ed25519PrivateKey.generate()
        manifest_raw, sig_raw, _key = _signed_manifest(
            files, key=Ed25519PrivateKey.generate()
        )
        with (
            self._flow(
                tmp_path,
                _release_payload(),
                manifest_raw=manifest_raw,
                sig_raw=sig_raw,
                pub_key_hex=attacker_hex,
            ) as (exit_mock, _phases, _base),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(16)

    def test_missing_manifest_asset(self, tmp_path):
        self._forced_platform = "win32"
        with (
            self._flow(tmp_path, _release_payload(with_manifest=False)) as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(11)

    def test_missing_signature_asset(self, tmp_path):
        self._forced_platform = "win32"
        with (
            self._flow(tmp_path, _release_payload(with_sig=False)) as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(16)

    def test_archive_checksum_mismatch(self, tmp_path):
        self._forced_platform = "win32"
        with (
            self._flow(tmp_path, _release_payload(), verify_checksum_result=False) as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(13)

    def test_manifest_file_checksum_mismatch(self, tmp_path):
        """Packaged content differs from the signed manifest → code 13."""
        self._forced_platform = "win32"
        files = _release_content()
        release_files = dict(files)
        release_files[f"app-1.0.0/core/app{_runtime_suffix()}"] = b"tampered"
        with (
            self._flow(
                tmp_path,
                _release_payload(),
                files=files,
                release_files=release_files,
            ) as (exit_mock, _phases, _base),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(13)

    # -----------------------------------------------------------------
    # STAGE guard rails
    # -----------------------------------------------------------------

    def test_already_active_version_exits_ok(self, tmp_path):
        """Pointer already names the target version → benign exit, no move."""
        self._forced_platform = "win32"
        base_dir = tmp_path / "install"
        target = base_dir / "app-1.0.0"
        target.mkdir(parents=True)
        (target / "core").mkdir()
        (target / "core" / f"junk{_runtime_suffix()}").write_bytes(b"junk")
        # pointer is "stale" (tool 0.9.0) but its active dir == release target
        write_pointer(base_dir, AppPointer("app-1.0.0", "0.9.0"))

        with (
            self._flow(tmp_path, _release_payload(), local_tool="0.9.0") as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(0)
        # the junk dir is untouched — never staged over itself
        assert (target / "core" / f"junk{_runtime_suffix()}").exists()
        pointer = read_pointer(base_dir)
        assert pointer is not None and pointer.tool_version == "0.9.0"

    def test_stale_target_dir_is_replaced(self, tmp_path):
        """A leftover non-active app dir from an interrupted run is wiped."""
        self._forced_platform = "win32"
        base_dir = tmp_path / "install"
        junk = base_dir / "app-1.0.0"
        (junk / "core").mkdir(parents=True)
        (junk / "core" / f"stale{_runtime_suffix()}").write_bytes(b"stale")
        write_pointer(base_dir, AppPointer("app-0.9.0", "0.9.0"))

        files = _release_content()

        with (
            self._flow(tmp_path, _release_payload()) as (
                exit_mock,
                _phases,
                _base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()

        exit_mock.assert_called_once_with(0)
        assert (junk / "core" / f"app{_runtime_suffix()}").read_bytes() == (
            b"new-app-binary"
        )
        assert not (junk / "core" / f"stale{_runtime_suffix()}").exists()
        pointer = read_pointer(base_dir)
        assert pointer is not None and pointer.active_app_dir == "app-1.0.0"

    def test_legacy_first_flip_has_no_previous(self, tmp_path):
        """A flat install's first flip records rollback data only for the
        versioned layout — previous_app_dir is None here."""
        self._forced_platform = "win32"
        with (
            self._flow(tmp_path, _release_payload()) as (
                exit_mock,
                _phases,
                base,
            ),
            pytest.raises(SystemExit),
        ):
            python.update.run_update()
        exit_mock.assert_called_once_with(0)
        pointer = read_pointer(base)
        assert pointer is not None and pointer.previous_app_dir is None
        # The flat core/ is untouched (user data: never moved by the updater)
        assert (base / "core" / f"app{_runtime_suffix()}").read_bytes() == (
            b"old-app-binary"
        )


# =========================================================================
# Status reporting + relaunch helpers (GUI launcher feedback)
# =========================================================================


class TestUpdateStatusReporting:
    def test_write_status_writes_json(self, tmp_path):
        import python.update as upd

        status_file = tmp_path / "update_status.json"
        with (
            patch.object(upd, "UPDATE_STATUS_FILE", status_file),
            patch.object(upd, "log"),
        ):
            upd._write_update_status("downloading", progress=42)
        assert json.loads(status_file.read_text(encoding="utf-8")) == {
            "phase": "downloading",
            "progress": 42,
            "message": "",
        }

    def test_write_status_with_message(self, tmp_path):
        import python.update as upd

        status_file = tmp_path / "update_status.json"
        with (
            patch.object(upd, "UPDATE_STATUS_FILE", status_file),
            patch.object(upd, "log"),
        ):
            upd._write_update_status("error", message="Update failed.")
        assert json.loads(status_file.read_text(encoding="utf-8"))["message"] == (
            "Update failed."
        )

    def test_clear_status_removes_file(self, tmp_path):
        import python.update as upd

        status_file = tmp_path / "update_status.json"
        status_file.write_text("{}", encoding="utf-8")
        with (
            patch.object(upd, "UPDATE_STATUS_FILE", status_file),
            patch.object(upd, "log"),
        ):
            upd._clear_update_status()
        assert not status_file.exists()

    def test_status_helpers_are_noops_without_file(self):
        import python.update as upd

        with (
            patch.object(upd, "UPDATE_STATUS_FILE", None),
            patch.object(upd, "log"),
        ):
            upd._write_update_status("checking")
            upd._clear_update_status()

    def test_status_write_failure_is_swallowed(self, tmp_path):
        import python.update as upd

        status_file = tmp_path / "update_status.json"
        with (
            patch.object(upd, "UPDATE_STATUS_FILE", status_file),
            patch.object(upd, "log"),
            patch.object(
                status_file.__class__, "write_text", side_effect=OSError("locked")
            ),
        ):
            upd._write_update_status("checking")  # must not raise

    def test_relaunch_skipped_outside_auto_mode(self):
        import python.update as upd

        with (
            patch.object(upd, "AUTO_MODE", False),
            patch.object(upd, "subprocess") as mock_sp,
            patch.object(upd, "log"),
        ):
            assert upd._relaunch_tool_after_update() is True
        mock_sp.Popen.assert_not_called()

    def test_relaunch_launches_start_exe(self):
        import python.update as upd

        start_file = Path("install") / "start.exe"
        with (
            patch.object(upd, "AUTO_MODE", True),
            patch.object(upd, "START_FILE", start_file),
            patch.object(upd, "subprocess") as mock_sp,
            patch.object(upd, "log"),
        ):
            assert upd._relaunch_tool_after_update() is True
        assert mock_sp.Popen.call_count == 1
        cmd = mock_sp.Popen.call_args[0][0]
        assert str(cmd[0]).endswith("start.exe")

    def test_relaunch_returns_false_on_oserror(self):
        import python.update as upd

        mock_sp = MagicMock()
        mock_sp.Popen = MagicMock(side_effect=OSError("start.exe missing"))
        with (
            patch.object(upd, "AUTO_MODE", True),
            patch.object(upd, "START_FILE", Path("start.exe")),
            patch.object(upd, "subprocess", mock_sp),
            patch.object(upd, "log"),
        ):
            assert upd._relaunch_tool_after_update() is False


# =========================================================================
# Launcher binary queueing (no execv/--resume chain anymore)
# =========================================================================


class TestLauncherBinaryQueueing:
    def _exercise(
        self,
        tmp_path: Path,
        *,
        new_bytes: bytes = b"new-start-binary",
    ) -> dict[str, Path]:
        base = _make_install(tmp_path)
        content_root = base / "_update_tmp" / "content"
        content_root.mkdir(parents=True)
        suffix = _runtime_suffix()
        (content_root / f"start{suffix}").write_bytes(new_bytes)
        (content_root / f"update{suffix}").write_bytes(new_bytes)
        with (
            patch.object(python.update, "BASE_DIR", base),
            patch.object(python.update, "log"),
        ):
            python.update._swap_launcher_binaries(content_root)
        return {
            "start": base / f"start{suffix}",
            "start_new": base / f"start_new{suffix}",
            "update": base / f"update{suffix}",
            "update_new": base / f"update_new{suffix}",
            "content_root": content_root,
        }

    def test_different_binaries_queued(self, tmp_path):
        paths = self._exercise(tmp_path)
        assert paths["start"].read_bytes() == b"old-start-binary"
        assert paths["start_new"].exists()
        assert paths["start_new"].read_bytes() == b"new-start-binary"
        assert paths["update_new"].exists()

    def test_identical_binaries_not_queued(self, tmp_path):
        base = _make_install(tmp_path)
        content_root = base / "_update_tmp" / "content"
        content_root.mkdir(parents=True)
        suffix = _runtime_suffix()
        (content_root / f"start{suffix}").write_bytes(b"old-start-binary")
        with (
            patch.object(python.update, "BASE_DIR", base),
            patch.object(python.update, "log"),
        ):
            python.update._swap_launcher_binaries(content_root)
        assert not (base / f"start_new{suffix}").exists()


# =========================================================================
# Update source + signing key override (test-only env hooks)
# =========================================================================


class TestUpdateSourceOverride:
    """``_init()`` must keep honoring the test-only env hooks."""

    _GLOBALS = (
        "BASE_DIR",
        "TEMP_DIR",
        "START_FILE",
        "VERSION_FILE",
        "UPDATE_STATUS_FILE",
        "AUTO_MODE",
        "cfg",
        "GITHUB_TOKEN",
        "HEADERS_API",
        "HEADERS_ASSET",
        "API_URL",
        "SIGNING_PUBLIC_KEY",
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

    def test_signing_key_env_override(self, monkeypatch, tmp_path):
        import python.update

        test_key = Ed25519PrivateKey.generate()
        test_hex = test_key.public_key().public_bytes_raw().hex()
        snap = {n: getattr(python.update, n, None) for n in self._GLOBALS}
        try:
            monkeypatch.setenv("T2M_SIGNING_PUBLIC_KEY", test_hex)
            self._run_init(monkeypatch, tmp_path)
            assert python.update.SIGNING_PUBLIC_KEY == test_hex
        finally:
            for n, v in snap.items():
                setattr(python.update, n, v)
            monkeypatch.delenv("T2M_SIGNING_PUBLIC_KEY", raising=False)

    def test_no_signing_env_uses_embedded_key(self, monkeypatch, tmp_path):
        import python.update

        snap = {n: getattr(python.update, n, None) for n in self._GLOBALS}
        try:
            monkeypatch.delenv("T2M_SIGNING_PUBLIC_KEY", raising=False)
            self._run_init(monkeypatch, tmp_path)
            assert (
                python.update.SIGNING_PUBLIC_KEY
                == python.update.RELEASE_SIGNING_PUBLIC_KEY
            )
        finally:
            for n, v in snap.items():
                setattr(python.update, n, v)
            monkeypatch.delenv("T2M_SIGNING_PUBLIC_KEY", raising=False)
