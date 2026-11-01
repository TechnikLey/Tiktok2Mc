#!/usr/bin/env python3
"""End-to-end updater test harness (update.exe / update.bin) — P3a flow.

Builds a realistic old installation, serves a GitHub-compatible fake
release (assembled P3a layout + signed manifest) via ``mock_github.py``
and runs the *compiled* updater against it, so the real production code
path of ``src/python/update.py`` is exercised end to end: version check,
asset selection, download, manifest signature verification (Ed25519,
detached ``.sig``), archive + per-file checksums, staging of
``app-<ver>/`` into the install root, atomic ``current.json`` pointer
flip, pruning of old version dirs and exit codes.

The updater never touches running processes (no kill choreography) and
no longer copies whitelisted files or migrates the user config — the
launcher does that at the next boot (``resolve_app_base`` +
``swap_pending_launcher_binaries``; covered by the ``launch_maintenance``
scenario and unit tests).

The only simulated part is the HTTP source: a local server that behaves
like the GitHub Releases API. Everything else is the real compiled
binary.

Usage::

    python tools/update_test/run_update_test.py --list
    python tools/update_test/run_update_test.py --scenario success
    python tools/update_test/run_update_test.py all
    python tools/update_test/run_update_test.py all --clean

See ``tools/update_test/README.md`` for details and the known Windows
Defender false positive on freshly built unsigned PyInstaller binaries.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
# ``src/`` first so ``import core.*`` resolves to the source package
# (the repo-root ``core/`` directory only holds runtime artifacts).
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)
from mock_github import (  # noqa: E402
    MANIFEST_ASSET,
    SIG_ASSET,
    MockGitHubServer,
    MockGitHubState,
    build_release_json,
)
from ruamel.yaml import YAML  # noqa: E402

from core.api.server import DEFAULT_PORT  # noqa: E402
from core.update_engine.manifest import (  # noqa: E402
    ManifestFile,
    generate_manifest,
    write_manifest,
)
from core.update_engine.pointer import (  # noqa: E402
    AppPointer,
    read_pointer,
    write_pointer,
)
from core.version import (  # noqa: E402
    EXPECTED_CONFIG_VERSION,
    TOOL_VERSION,
    UPDATER_VERSION,
)

if os.name == "nt":
    os.system("")

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"
PLATFORM_LABEL = "Windows" if sys.platform == "win32" else "Linux"
ARCHIVE_EXT = "zip" if sys.platform == "win32" else "tar.gz"
UPDATE_SOURCE_ENV = "TIKTOK2MC_UPDATE_SOURCE"
SIGNING_KEY_ENV = "T2M_SIGNING_PUBLIC_KEY"
SIGNAL_PATH = "/api/v1/updater/signal"

C = "\033[96m"
G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
X = "\033[0m"

# ---------------------------------------------------------------------------
# Templates (realistic, versioned configs so the launcher-side migration
# can be asserted afterwards)
# ---------------------------------------------------------------------------

INSTALL_CONFIG = (
    "config_version: '0.7'\n"
    "server_host: 192.168.1.100\n"
    "control_method: RCON\n"
    "auto_update_config: true\n"
    "show_sudo_warning: false\n"
    "java:\n"
    "  xms: 1G\n"
    "  xmx: 2G\n"
)

INSTALL_DEFAULT = (
    "config_version: '0.7'\n"
    "server_host: 0.0.0.0\n"
    "control_method: DCS\n"
    "auto_update_config: true\n"
    "show_sudo_warning: false\n"
    "java:\n"
    "  xms: 512M\n"
    "  xmx: 1G\n"
)

RELEASE_DEFAULT = (
    "config_version: '1.0'\n"
    "server_host: 0.0.0.0\n"
    "control_method: DCS\n"
    "auto_update_config: true\n"
    "show_sudo_warning: false\n"
    "java:\n"
    "  xms: 512M\n"
    "  xmx: 1G\n"
    "  new_option: default\n"
)


@dataclass
class RunResult:
    returncode: int
    output: str
    timed_out: bool = False


# ---------------------------------------------------------------------------
# Control-plane port reservation
# ---------------------------------------------------------------------------


class _SignalHandler(BaseHTTPRequestHandler):
    """Mimics ``GET/PUT/DELETE /api/v1/updater/signal`` from the running app."""

    @property
    def _state(self) -> SignalAPIServer:
        return self.server.signal_state  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        if urllib.parse.urlparse(self.path).path == SIGNAL_PATH:
            self._json(200, {"signal": self._state.value})
        else:
            self.send_error(404)

    def do_PUT(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        self._state.value = payload.get("signal")
        self._json(200, {"signal": self._state.value})

    def do_DELETE(self) -> None:
        self._state.value = None
        self._json(200, {"signal": None})

    def _json(self, status: int, obj: Any) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


class SignalAPIServer:
    """Reserve ``DEFAULT_PORT`` while the harness runs (legacy endpoint).

    The P3a updater never talks to this endpoint anymore; binding it here
    primarily **reserves the control-plane port** so no real Tiktok2Mc
    instance can be running during the test. The legacy signal contract
    stays served for backwards compatibility with pre-P3a updaters.
    """

    def __init__(self) -> None:
        self.value: str | None = None
        self._httpd = ThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), _SignalHandler)
        self._httpd.signal_state = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="mock-signal-api"
        )

    def start(self) -> SignalAPIServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class Harness:
    def __init__(
        self,
        *,
        updater_binary: Path,
        scratch: Path,
        old_tool: str,
        old_updater: str,
        new_tool: str,
        new_updater: str,
    ) -> None:
        self.updater = updater_binary
        self.scratch = scratch
        self.old_tool = old_tool
        self.old_updater = old_updater
        self.new_tool = new_tool
        self.new_updater = new_updater
        # Per-run signing key: the harness signs the release manifest with
        # its own key and tells the compiled updater to trust it via the
        # T2M_SIGNING_PUBLIC_KEY env override (mirrors
        # TIKTOK2MC_UPDATE_SOURCE). Signature-failure scenarios sign with a
        # deliberately wrong key (self.bad_key).
        self.release_key = Ed25519PrivateKey.generate()
        self.bad_key = Ed25519PrivateKey.generate()

    # ---- helpers ---------------------------------------------------------

    def expect(self, cond: bool, msg: str) -> None:
        if not cond:
            raise AssertionError(msg)

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_versions(self, install: Path) -> dict[str, str]:
        result = {"tool": "", "updater": ""}
        vf = install / "version.txt"
        if not vf.exists():
            return result
        for line in vf.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            k = key.strip().lower()
            if "toolversion" in k:
                result["tool"] = val.strip()
            elif "updaterversion" in k:
                result["updater"] = val.strip()
        return result

    def read_config(self, install: Path) -> dict[str, Any]:
        yaml = YAML(typ="rt")
        with (install / "config" / "config.yaml").open(encoding="utf-8") as f:
            data = yaml.load(f)
        return data or {}

    def read_pointer(self, install: Path) -> AppPointer | None:
        return read_pointer(install)

    def app_dir(self, install: Path, tool: str | None = None) -> Path:
        return install / f"app-{tool or self.new_tool}"

    def save_output(self, scenario: str, output: str) -> Path:
        log_dir = self.scratch / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{scenario}.log"
        path.write_text(output, encoding="utf-8")
        return path

    # ---- installations ---------------------------------------------------

    def _base_install(self) -> Path:
        install = self.scratch / "install"
        if install.exists():
            shutil.rmtree(install)
        install.mkdir(parents=True)
        shutil.copy2(self.updater, install / f"update{SUFFIX}")
        self.write(
            install / "version.txt", self._version_txt(self.old_tool, self.old_updater)
        )
        self.write(install / "config" / "config.yaml", INSTALL_CONFIG)
        self.write(install / "config" / "config.default.yaml", INSTALL_DEFAULT)
        return install

    def _version_txt(self, tool: str, updater: str) -> str:
        return f"ToolVersion: {tool}\nUpdaterVersion: {updater}\n"

    def prepare_install(self) -> Path:
        """Legacy flat installation (pre-P3a): program content at root."""
        install = self._base_install()
        self.write(install / "README.md", "old readme")
        self.write(install / "LICENSE", "old license")
        self.write(install / f"start{SUFFIX}", "old start")
        self.write(install / "core" / f"app{SUFFIX}", "old app")
        self.write(install / "core" / f"server{SUFFIX}", "old server")
        self.write(install / "core" / "marker.txt", "OLD")
        self.write(install / "plugins" / "wincounter" / "main.py", "old wincounter")
        return install

    def prepare_versioned_install(self) -> Path:
        """Versioned installation with pointer, two old versions and a
        stale leftover app dir for the target version."""
        install = self._base_install()
        # Versioned installs keep the launcher binaries at the root.
        self.write(install / f"start{SUFFIX}", "old start")
        for tool, content in ((self.old_tool, "old app"), ("0.6.0", "ancient app")):
            app_dir = install / f"app-{tool}"
            self.write(app_dir / "core" / f"app{SUFFIX}", content)
            self.write(app_dir / "core" / "marker.txt", tool.upper())
        self.write(
            self.app_dir(install) / "core" / f"app{SUFFIX}", "stale app"
        )  # leftover from an interrupted previous run
        write_pointer(
            install,
            AppPointer(
                active_app_dir=f"app-{self.old_tool}",
                tool_version=self.old_tool,
            ),
        )
        return install

    # ---- release (P3a layout + signed manifest) ---------------------------

    def prepare_release(
        self, *, with_updater: bool = False, updater_version: str | None = None
    ) -> Path:
        """Assembled P3a release: app-<ver>/ program content + root shells
        + pointer + signed manifest (the production ``build.py`` output)."""
        release = self.scratch / "release"
        if release.exists():
            shutil.rmtree(release)
        release.mkdir(parents=True)
        rel_updater = updater_version or self.new_updater
        app_dir = self.app_dir(release)

        # -- program content (goes into app-<ver>/) --
        self.write(app_dir / "core" / f"app{SUFFIX}", "new app")
        self.write(app_dir / "core" / f"server{SUFFIX}", "new server")
        self.write(app_dir / "core" / "marker.txt", "NEW")
        self.write(app_dir / "plugins" / "wincounter" / "main.py", "new wincounter")

        # -- root shells + user-facing trees (NOT updated by the updater) --
        self.write(release / f"start{SUFFIX}", "new start")
        if with_updater:
            # simuliert ein aktualisiertes Update-Binary im Release
            self.write(release / f"update{SUFFIX}", f"new update {rel_updater}")
        else:
            self.write(release / f"update{SUFFIX}", "new update")
        self.write(release / "config" / "config.default.yaml", RELEASE_DEFAULT)
        # Mirrors build.py: the per-version config template rides along in
        # the app dir so the launcher first-start hook (candidate 1) picks
        # up the NEW version's template, not the previous install's.
        self.write(app_dir / "config" / "config.default.yaml", RELEASE_DEFAULT)
        self.write(release / "README.md", "new readme (root, not staged)")

        # -- pointer + version metadata (P3a fresh-install contract) --
        write_pointer(
            release,
            AppPointer(
                active_app_dir=f"app-{self.new_tool}",
                tool_version=self.new_tool,
            ),
        )
        self.write(
            release / "version.txt", self._version_txt(self.new_tool, rel_updater)
        )

        # -- signed manifest (mirrors build.py's release assembly) --
        manifest = generate_manifest(
            app_dir,
            tool_version=self.new_tool,
            config_version_expected=EXPECTED_CONFIG_VERSION,
            updater_version=rel_updater,
            prefix=app_dir.name,
        )
        extra: list[ManifestFile] = []
        for rel in (
            f"start{SUFFIX}",
            f"update{SUFFIX}",
            "current.json",
            "version.txt",
        ):
            data = (release / rel).read_bytes()
            extra.append(
                ManifestFile(
                    path=rel,
                    sha256=hashlib.sha256(data).hexdigest(),
                    size=len(data),
                )
            )
        from dataclasses import replace as _dc_replace

        manifest = _dc_replace(manifest, files=manifest.files + tuple(extra))
        write_manifest(release, manifest, self.release_key)
        return release

    def make_archive(self, release: Path) -> tuple[Path, str]:
        name = f"Tiktok2Mc_v{self.new_tool}_{PLATFORM_LABEL}.{ARCHIVE_EXT}"
        path = self.scratch / name
        if sys.platform == "win32":
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(release.rglob("*")):
                    if f.is_file():
                        zf.write(f, arcname=f.relative_to(release).as_posix())
        else:
            with tarfile.open(path, "w:gz") as tf:
                for f in sorted(release.rglob("*")):
                    if f.is_file():
                        tf.add(f, arcname=f.relative_to(release).as_posix())
        # The manifest + .sig double as standalone release assets, served
        # by the mock server next to the archive (which also carries them).
        for asset in (MANIFEST_ASSET, SIG_ASSET):
            src = release / asset
            if src.is_file():
                shutil.copy2(src, self.scratch / asset)
        return path, name

    def write_checksum(self, archive: Path, archive_name: str) -> None:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (self.scratch / f"{archive_name}.sha256").write_text(
            f"{digest}  {archive_name}\n", encoding="utf-8"
        )

    def start_server(
        self,
        *,
        tag_name: str,
        archive_name: str,
        include_checksum: bool = True,
        include_manifest: bool = True,
        include_sig: bool = True,
        release_status: int = 200,
        release_body: bytes = b"",
        asset_delay: float = 0.0,
        asset_fail: set[str] | None = None,
        release_json: dict[str, Any] | None = None,
    ) -> MockGitHubServer:
        state = MockGitHubState(
            release_dir=self.scratch,
            release_json={},
            release_status=release_status,
            release_body=release_body,
            asset_delay=asset_delay,
            asset_fail=asset_fail or set(),
        )
        server = MockGitHubServer(state)
        if release_json is None:
            release_json = build_release_json(
                tag_name,
                f"{server.base_url}/assets/{archive_name}",
                archive_name,
                include_checksum=include_checksum,
                include_manifest=include_manifest,
                include_sig=include_sig,
            )
        state.release_json = release_json
        server.start()
        return server

    # ---- running the compiled updater ------------------------------------

    def run_updater(
        self,
        install: Path,
        api_url: str,
        *,
        auto: bool = True,
        stdin_data: bytes | None = None,
        timeout: float = 120.0,
        kill_after: float | None = None,
        signing_key_hex: str | None = None,
    ) -> RunResult:
        env = os.environ.copy()
        env[UPDATE_SOURCE_ENV] = api_url
        if signing_key_hex is None:
            signing_key_hex = self.release_key.public_key().public_bytes_raw().hex()
        env[SIGNING_KEY_ENV] = signing_key_hex
        cmd = [str(install / f"update{SUFFIX}")]
        if auto:
            cmd.append("--auto")
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
        )
        try:
            if kill_after is not None:
                time.sleep(kill_after)
                self._kill_tree(proc)
                out, _ = proc.communicate(timeout=15)
                return RunResult(
                    proc.returncode, out.decode(errors="replace"), timed_out=True
                )
            out, _ = proc.communicate(input=stdin_data, timeout=timeout)
            return RunResult(proc.returncode, out.decode(errors="replace"))
        except subprocess.TimeoutExpired:
            self._kill_tree(proc)
            try:
                out, _ = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                out = b""
            return RunResult(
                proc.returncode, out.decode(errors="replace"), timed_out=True
            )

    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> None:
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        else:
            proc.kill()

    # ---- assertions ------------------------------------------------------

    def assert_updated(
        self,
        install: Path,
        expected_updater: str | None = None,
        *,
        expected_update_new: str = "new update",
    ) -> None:
        """The updater staged ``app-<ver>/``, flipped the pointer and left
        user data + running binaries alone."""
        target_updater = expected_updater or self.new_updater
        pointer = self.read_pointer(install)
        if pointer is not None:
            self.expect(
                pointer.active_app_dir == f"app-{self.new_tool}",
                f"pointer = {pointer.active_app_dir!r} (expected app-{self.new_tool!r})",
            )
            self.expect(
                pointer.tool_version == self.new_tool,
                f"pointer tool_version = {pointer.tool_version!r}",
            )
        self.expect(
            (self.app_dir(install) / "core" / f"app{SUFFIX}").read_text(
                encoding="utf-8"
            )
            == "new app",
            "app dir core/app was not staged",
        )
        self.expect(
            (self.app_dir(install) / "core" / "marker.txt").read_text(encoding="utf-8")
            == "NEW",
            "app dir core/marker.txt was not staged",
        )
        self.expect(
            (self.app_dir(install) / "plugins" / "wincounter" / "main.py").read_text(
                encoding="utf-8"
            )
            == "new wincounter",
            "plugin file was not staged",
        )
        v = self.read_versions(install)
        self.expect(
            v["tool"] == self.new_tool,
            f"version.txt tool = {v['tool']!r} (expected {self.new_tool!r})",
        )
        self.expect(
            v["updater"] == target_updater,
            f"version.txt updater = {v['updater']!r} (expected {target_updater!r})",
        )
        # Running processes are untouched: the launcher binaries are QUEUED.
        self.expect(
            (install / f"start{SUFFIX}").read_text(encoding="utf-8")
            in ("old start", "small new start"),
            "start was overwritten while it might be running",
        )
        self.expect(
            (install / f"start_new{SUFFIX}").read_text(encoding="utf-8") == "new start",
            "start_new was not queued for the next launcher boot",
        )
        self.expect(
            (install / f"update_new{SUFFIX}").read_text(encoding="utf-8")
            == expected_update_new,
            f"update_new was not queued as {expected_update_new!r}",
        )
        # User data never travels with the update package.
        self.expect(
            (install / "config" / "config.yaml").read_text(encoding="utf-8")
            == INSTALL_CONFIG,
            "config.yaml must never be overwritten by the updater",
        )
        self.expect(
            not (install / "_update_tmp").exists(),
            "_update_tmp was not cleaned up",
        )
        self.expect(
            not (install / "update_signal.tmp").exists(),
            "P3a updater must not create update_signal.tmp",
        )

    def assert_unchanged(self, install: Path) -> None:
        pointer = self.read_pointer(install)
        self.expect(
            pointer is None or pointer.tool_version == self.old_tool,
            "pointer flipped although nothing should have been installed",
        )
        self.expect(
            (install / "core" / f"app{SUFFIX}").read_text(encoding="utf-8")
            == "old app",
            "core/app was modified although nothing should have been installed",
        )
        v = self.read_versions(install)
        self.expect(
            v["tool"] == self.old_tool,
            f"version.txt tool = {v['tool']!r} (expected {self.old_tool!r})",
        )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_success(h: Harness) -> bool:
    """Legacy flat install 0.7 -> assembled P3a release."""
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("success", r.output)
    h.expect(r.returncode == 0, f"exit {r.returncode} (expected 0)\n{r.output}")
    h.assert_updated(install)
    print(f"{G}  OK: app dir staged, pointer flipped, launcher queued, exit 0{X}")
    return True


def scenario_up_to_date(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.old_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("up_to_date", r.output)
    h.expect(r.returncode == 5, f"exit {r.returncode} (expected 5)\n{r.output}")
    h.expect("up to date" in r.output.lower(), "expected 'up to date' message")
    h.assert_unchanged(install)
    print(f"{G}  OK: no update needed, exit 5{X}")
    return True


def scenario_missing_asset(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    _, name = h.make_archive(release)
    release_json = {
        "tag_name": f"v{h.new_tool}",
        "assets": [
            {"name": "Tiktok2Mc_setup.exe", "url": f"{h.scratch.as_uri()}/setup.exe"}
        ],
    }
    server = h.start_server(
        tag_name=f"v{h.new_tool}", archive_name=name, release_json=release_json
    )
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("missing_asset", r.output)
    h.expect(r.returncode == 11, f"exit {r.returncode} (expected 11)\n{r.output}")
    h.expect(
        "no matching release asset" in r.output.lower(),
        "expected asset-not-found message",
    )
    h.assert_unchanged(install)
    print(f"{G}  OK: missing asset aborts update, exit 11{X}")
    return True


def scenario_missing_manifest(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(
        tag_name=f"v{h.new_tool}", archive_name=name, include_manifest=False
    )
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("missing_manifest", r.output)
    h.expect(r.returncode == 11, f"exit {r.returncode} (expected 11)\n{r.output}")
    h.assert_unchanged(install)
    print(f"{G}  OK: missing manifest aborts update, exit 11{X}")
    return True


def scenario_missing_sig(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(
        tag_name=f"v{h.new_tool}", archive_name=name, include_sig=False
    )
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("missing_sig", r.output)
    h.expect(r.returncode == 16, f"exit {r.returncode} (expected 16)\n{r.output}")
    h.assert_unchanged(install)
    print(f"{G}  OK: missing .sig rejects update, exit 16{X}")
    return True


def scenario_sig_fail(h: Harness) -> bool:
    """Manifest signed with an unknown key must be rejected (fail closed)."""
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        # The updater is told to trust h.release_key (the default), but the
        # served signature was made with an attacker key.
        manifest_raw = (h.scratch / MANIFEST_ASSET).read_bytes()
        (h.scratch / SIG_ASSET).write_bytes(h.bad_key.sign(manifest_raw))
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("sig_fail", r.output)
    h.expect(r.returncode == 16, f"exit {r.returncode} (expected 16)\n{r.output}")
    h.expect("signature" in r.output.lower(), "expected signature verification message")
    h.assert_unchanged(install)
    print(f"{G}  OK: unknown signing key rejected, exit 16{X}")
    return True


def scenario_bad_checksum(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    _, name = h.make_archive(release)
    (h.scratch / f"{name}.sha256").write_text(f"{'f' * 64}  {name}\n", encoding="utf-8")
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("bad_checksum", r.output)
    h.expect(r.returncode == 13, f"exit {r.returncode} (expected 13)\n{r.output}")
    h.expect("checksum" in r.output.lower(), "expected checksum message")
    h.assert_unchanged(install)
    print(f"{G}  OK: bad checksum aborts update, install untouched{X}")
    return True


def scenario_tampered_file(h: Harness) -> bool:
    """Archive sha256 matches but a packaged file differs from the signed
    per-file manifest → reject (per-file verification)."""
    install = h.prepare_install()
    release = h.prepare_release()
    # Tamper AFTER manifest signing: rebuild the app file in the *release*,
    # then re-pack WITHOUT regenerating manifest checksums. To keep archive
    # and .sha256 consistent, re-create the archive + checksum manually.
    target = h.app_dir(release) / "core" / f"app{SUFFIX}"
    target.write_text("tampered app", encoding="utf-8")
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    from core.update_engine.manifest import parse_manifest_bytes

    manifest = parse_manifest_bytes((h.scratch / MANIFEST_ASSET).read_bytes())
    entry = next(
        iter(
            f for f in manifest.files if f.path == f"app-{h.new_tool}/core/app{SUFFIX}"
        )
    )
    h.expect(
        entry.sha256 != hashlib.sha256(target.read_bytes()).hexdigest(),
        "tamper did not change hash",
    )
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("tampered_file", r.output)
    h.expect(r.returncode == 13, f"exit {r.returncode} (expected 13)\n{r.output}")
    h.assert_unchanged(install)
    print(f"{G}  OK: tampered packaged file rejected via manifest, exit 13{X}")
    return True


def scenario_invalid_version(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name="this-is-not-a-version", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("invalid_version", r.output)
    h.expect(r.returncode == 5, f"exit {r.returncode} (expected 5)\n{r.output}")
    h.assert_unchanged(install)
    print(f"{G}  OK: invalid tag treated as no update, exit 5{X}")
    return True


def scenario_api_error(h: Harness) -> bool:
    install = h.prepare_install()
    server = h.start_server(
        tag_name=f"v{h.new_tool}",
        archive_name="unused.zip",
        release_status=500,
        release_body=b"boom",
    )
    try:
        r = h.run_updater(install, server.api_url, timeout=60.0)
    finally:
        server.stop()
    h.save_output("api_error", r.output)
    h.expect(r.returncode == 10, f"exit {r.returncode} (expected 10)\n{r.output}")
    h.expect("API error" in r.output, "expected API error message")
    h.assert_unchanged(install)
    print(f"{G}  OK: API error handled (retried, then abort), exit 10{X}")
    return True


def scenario_download_error(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(
        tag_name=f"v{h.new_tool}", archive_name=name, asset_fail={name}
    )
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("download_error", r.output)
    h.expect(r.returncode == 14, f"exit {r.returncode} (expected 14)\n{r.output}")
    h.assert_unchanged(install)
    print(f"{G}  OK: download failure aborts update, exit 14{X}")
    return True


def scenario_abort_download(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(
        tag_name=f"v{h.new_tool}", archive_name=name, asset_delay=30.0
    )
    try:
        r = h.run_updater(install, server.api_url, kill_after=6.0)
    finally:
        server.stop()
    h.expect(r.returncode != 0, f"updater was not killed (exit {r.returncode})")
    h.assert_unchanged(install)
    print(f"{G}  OK: interrupted updater left the installation untouched{X}")
    return True


def scenario_self_update(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release(with_updater=True, updater_version="9.9.9")
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.expect(r.returncode == 0, f"exit {r.returncode} (expected 0)\n{r.output}")
    h.expect(
        (install / f"update_new{SUFFIX}").read_text(encoding="utf-8").endswith("9.9.9"),
        f"update_new{SUFFIX} does not carry the new updater version",
    )
    h.assert_updated(
        install, expected_updater="9.9.9", expected_update_new="new update 9.9.9"
    )
    print(f"{G}  OK: updater binary queued at root for the next launcher boot{X}")
    return True


def scenario_locked_file(h: Harness) -> bool:
    """A file locked inside the (stale) target dir must abort with 15.

    The updater wipes the stale target dir, then moves the staged dir into
    place — a held lock keeps the stale dir alive, so the move fails.
    """
    if sys.platform != "win32":
        print(f"{Y}  (skipped — Windows-only scenario){X}")
        return True
    install = h.prepare_versioned_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    target = h.app_dir(install) / "core" / f"app{SUFFIX}"
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateFileW(
        str(target), 0x80000000, 0, None, 3, 0, None
    )  # no shared access
    if not handle or handle == ctypes.c_void_p(-1).value:
        server.stop()
        print(f"{Y}  (skipped — could not lock {target.name}){X}")
        return True
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        kernel32.CloseHandle(handle)
        server.stop()
    h.expect(r.returncode == 15, f"exit {r.returncode} (expected 15)\n{r.output}")
    pointer = h.read_pointer(install)
    h.expect(
        pointer is None or pointer.tool_version == h.old_tool,
        "pointer was flipped although the install failed",
    )
    print(f"{G}  OK: locked target dir aborts update with pointer intact, exit 15{X}")
    return True


def scenario_retry_after_failure(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    (h.scratch / f"{name}.sha256").write_text(f"{'f' * 64}  {name}\n", encoding="utf-8")
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r1 = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.expect(
        r1.returncode == 13,
        f"first run exit {r1.returncode} (expected 13)\n{r1.output}",
    )
    h.assert_unchanged(install)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r2 = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.expect(
        r2.returncode == 0, f"retry exit {r2.returncode} (expected 0)\n{r2.output}"
    )
    h.assert_updated(install)
    print(f"{G}  OK: failed update then successful retry{X}")
    return True


def scenario_beta_prompt(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    tag = f"v{h.new_tool}-beta"
    server = h.start_server(tag_name=tag, archive_name=name)
    try:
        r1 = h.run_updater(install, server.api_url, auto=False, stdin_data=b"n\n")
    finally:
        server.stop()
    h.expect(
        r1.returncode == 5, f"decline exit {r1.returncode} (expected 5)\n{r1.output}"
    )
    h.assert_unchanged(install)
    server = h.start_server(tag_name=tag, archive_name=name)
    try:
        r2 = h.run_updater(install, server.api_url, auto=False, stdin_data=b"y\n")
    finally:
        server.stop()
    h.expect(
        r2.returncode == 0, f"accept exit {r2.returncode} (expected 0)\n{r2.output}"
    )
    h.assert_updated(install)
    print(f"{G}  OK: beta decline exits 5, beta accept updates{X}")
    return True


def scenario_versioned_install(h: Harness) -> bool:
    """Versioned install: stale target dir replaced, pointer correctly
    flipped (previous kept as rollback), ancient version pruned."""
    install = h.prepare_versioned_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.expect(r.returncode == 0, f"exit {r.returncode} (expected 0)\n{r.output}")

    pointer = h.read_pointer(install)
    h.expect(pointer is not None, "pointer missing after update")
    assert pointer is not None  # for type checkers
    h.expect(
        pointer.active_app_dir == f"app-{h.new_tool}",
        f"pointer = {pointer.active_app_dir!r}",
    )
    h.expect(
        pointer.previous_app_dir == f"app-{h.old_tool}",
        f"previous_app_dir = {pointer.previous_app_dir!r} (expected app-{h.old_tool})",
    )
    # Stale leftover target dir was wiped and re-staged.
    h.expect(
        (h.app_dir(install) / "core" / f"app{SUFFIX}").read_text(encoding="utf-8")
        == "new app",
        "stale target dir was not replaced by the staged content",
    )
    # The rollback generation survived, the ancient generation was pruned.
    h.expect(
        (install / f"app-{h.old_tool}" / "core" / f"app{SUFFIX}").read_text(
            encoding="utf-8"
        )
        == "old app",
        "rollback generation (previous version) must be kept",
    )
    h.expect(
        not (install / "app-0.6.0").exists(),
        "old version dir was not pruned",
    )
    h.assert_updated(install)
    print(f"{G}  OK: stale dir replaced, previous kept, old dir pruned{X}")
    return True


def scenario_launch_maintenance(h: Harness) -> bool:
    """Full choreography: updater run (legacy flat install) → next boot's
    launcher maintenance (layout migration + queued binary swap → stable)."""
    from core.update_engine.launch_layout import (
        resolve_app_base,
        swap_pending_launcher_binaries,
    )

    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.expect(r.returncode == 0, f"exit {r.returncode} (expected 0)\n{r.output}")

    # Boot 1: layout resolves from the pointer; legacy flat core/ is not
    # touched (the updater already left it for the pointer-based layout).
    app_base, migrated = resolve_app_base(install, install)
    h.expect(
        app_base == h.app_dir(install),
        f"app base = {app_base} (expected {h.app_dir(install)})",
    )
    h.expect(migrated is False, "unexpected migration of a pointer-based install")

    # Boot 2: queued launcher binaries get installed.
    swapped = swap_pending_launcher_binaries(install, SUFFIX)
    h.expect(swapped == {"start": True, "update": True}, f"swapped = {swapped!r}")
    h.expect(
        (install / f"update{SUFFIX}").read_text(encoding="utf-8") == "new update",
        "queued updater binary was not installed",
    )
    h.expect(
        (install / f"start{SUFFIX}").read_text(encoding="utf-8") == "new start",
        "queued start binary was not installed",
    )

    # Boot 3: nothing pending → stable, no further changes.
    swapped = swap_pending_launcher_binaries(install, SUFFIX)
    h.expect(swapped == {"start": False, "update": False}, f"reswapped: {swapped!r}")
    app_base2, migrated2 = resolve_app_base(install, install)
    h.expect(
        app_base2 == app_base and migrated2 == migrated, "boot 3 drifted from boot 1"
    )
    print(f"{G}  OK: launcher boots stable into the new version{X}")
    return True


def scenario_config_migration_parity(h: Harness) -> bool:
    """Config migration parity: the updater leaves the user config alone;
    the launcher first-start hook migrates it (template from the app dir)
    while preserving user values."""
    from core.update_engine.launch_layout import run_first_start_config_hook

    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.expect(r.returncode == 0, f"exit {r.returncode} (expected 0)\n{r.output}")

    # Updater phase: user config untouched.
    cfg = h.read_config(install)
    h.expect(
        str(cfg.get("config_version")) != "1.0",
        "updater migrated the config (must not)",
    )

    # Launcher phase: first-start hook. The hook resolves user data via
    # core.paths — the T2M_DATA_HOME override (test-only hook, mirrors
    # TIKTOK2MC_UPDATE_SOURCE) isolates it into the scratch install so the
    # harness never touches the developer's real config/runtime.
    old_home = os.environ.get("T2M_DATA_HOME")
    os.environ["T2M_DATA_HOME"] = str(install)
    try:
        result = run_first_start_config_hook(install)
        h.expect(result is not None, "first-start hook was a no-op")
        assert result is not None
        cfg = h.read_config(install)
        h.expect(
            str(cfg.get("config_version")) == "1.0",
            f"config_version = {cfg.get('config_version')!r}",
        )
        h.expect(
            cfg.get("server_host") == "192.168.1.100",
            f"user server_host lost: {cfg.get('server_host')!r}",
        )
        h.expect(
            cfg.get("java", {}).get("xms") == "1G",
            f"user java.xms lost: {cfg.get('java', {}).get('xms')!r}",
        )
        second = run_first_start_config_hook(install)
        h.expect(second is None, "hook must be a no-op in the same tool version")
    finally:
        if old_home is None:
            os.environ.pop("T2M_DATA_HOME", None)
        else:
            os.environ["T2M_DATA_HOME"] = old_home
    print(f"{G}  OK: config migrated by the launcher hook with values preserved{X}")
    return True


SCENARIOS: list[tuple[str, str, Callable[[Harness], bool]]] = [
    (
        "success",
        "legacy flat install -> assembled release, full update",
        scenario_success,
    ),
    (
        "versioned_update",
        "stale dir replaced, previous kept, old dir pruned",
        scenario_versioned_install,
    ),
    ("up_to_date", "installed version == latest -> no update", scenario_up_to_date),
    ("missing_asset", "release has no platform archive", scenario_missing_asset),
    (
        "missing_manifest",
        "release has no manifest.json asset",
        scenario_missing_manifest,
    ),
    ("missing_sig", "release has no .sig asset", scenario_missing_sig),
    ("sig_fail", "manifest signed with unknown key", scenario_sig_fail),
    ("bad_checksum", "archive checksum does not match", scenario_bad_checksum),
    (
        "tampered_file",
        "packaged file differs from signed manifest",
        scenario_tampered_file,
    ),
    ("invalid_version", "malformed release tag", scenario_invalid_version),
    ("api_error", "GitHub API returns HTTP 500", scenario_api_error),
    ("download_error", "archive download fails (404)", scenario_download_error),
    ("abort_download", "updater killed mid-download", scenario_abort_download),
    ("self_update", "new updater version in release", scenario_self_update),
    ("locked_file", "locked stale target dir (Windows)", scenario_locked_file),
    (
        "retry_after_failure",
        "failed update then successful retry",
        scenario_retry_after_failure,
    ),
    ("beta_prompt", "beta release prompt (decline + accept)", scenario_beta_prompt),
    (
        "launch_maintenance",
        "bootstrap migration + queued binary swap across launcher boots",
        scenario_launch_maintenance,
    ),
    (
        "config_migration_parity",
        "config migration moved to the launcher first-start hook",
        scenario_config_migration_parity,
    ),
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_scenario(h: Harness, name: str) -> bool:
    func = dict((n, f) for n, _, f in SCENARIOS)[name]
    api = None
    try:
        api = SignalAPIServer()
    except OSError:
        print(f"{R}  FAIL: port {DEFAULT_PORT} is already in use. Close any running{X}")
        print(
            f"{R}        Tiktok2Mc instance (the updater talks to the control plane{X}"
        )
        print(f"{R}        on this port) and try again.{X}")
        return False
    api.start()
    try:
        return func(h)
    finally:
        api.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scenario", nargs="?", default=None, help="scenario name or 'all'"
    )
    parser.add_argument("--list", action="store_true", help="list available scenarios")
    parser.add_argument(
        "--updater",
        default=None,
        type=Path,
        help=f"path to the compiled updater (default: build/release/update{SUFFIX})",
    )
    parser.add_argument("--scratch", default=None, type=Path, help="scratch directory")
    parser.add_argument(
        "--clean", action="store_true", help="remove scratch dir after the run"
    )
    parser.add_argument("--old-tool", default="0.7.0", help="installed tool version")
    parser.add_argument(
        "--old-updater", default="1.0.0", help="installed updater version"
    )
    parser.add_argument(
        "--new-tool",
        default=None,
        help=f"released tool version (default: {TOOL_VERSION.lstrip('v')})",
    )
    parser.add_argument(
        "--new-updater",
        default=None,
        help=f"released updater version (default: {UPDATER_VERSION.lstrip('v')})",
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, desc, _ in SCENARIOS:
            print(f"  {name:<22} {desc}")
        return 0

    updater = (
        args.updater or (_ROOT / "build" / "release" / f"update{SUFFIX}")
    ).resolve()
    if not updater.exists():
        print(f"{R}Compiled updater not found: {updater}{X}")
        print(f"{Y}Build it first:  python build.py app --only update{X}")
        return 2

    new_tool = (args.new_tool or TOOL_VERSION.lstrip("v")).strip()
    new_updater = (args.new_updater or UPDATER_VERSION.lstrip("v")).strip()

    if args.scratch:
        scratch = args.scratch.resolve()
        scratch.mkdir(parents=True, exist_ok=True)
    else:
        scratch = Path(tempfile.mkdtemp(prefix="tiktok2mc_update_test_"))

    h = Harness(
        updater_binary=updater,
        scratch=scratch,
        old_tool=args.old_tool,
        old_updater=args.old_updater,
        new_tool=new_tool,
        new_updater=new_updater,
    )

    names = [n for n, _, _ in SCENARIOS]
    if args.scenario in (None, "all"):
        chosen = names
    elif args.scenario in names:
        chosen = [args.scenario]
    else:
        print(f"{R}Unknown scenario: {args.scenario}{X}")
        for name, desc, _ in SCENARIOS:
            print(f"  {name:<22} {desc}")
        return 2

    print(f"{C}Updater:      {updater}{X}")
    print(f"{C}Old version:  {args.old_tool} (updater {args.old_updater}){X}")
    print(f"{C}New version:  {new_tool} (updater {new_updater}){X}")
    print(f"{C}Scratch dir:  {scratch}{X}")

    results: list[tuple[str, bool]] = []
    for name in chosen:
        desc = dict((n, d) for n, d, _ in SCENARIOS)[name]
        print(f"\n{C}== {name}{X} — {desc}")
        try:
            ok = _run_scenario(h, name)
        except AssertionError as e:
            print(f"{R}  FAIL: {e}{X}")
            ok = False
        except Exception as e:  # noqa: BLE001
            print(f"{R}  ERROR: {e!r}{X}")
            ok = False
        results.append((name, ok))

    print("\n" + "=" * 50)
    failed = 0
    for name, ok in results:
        mark = f"{G}PASS{X}" if ok else f"{R}FAIL{X}"
        print(f"  {name:<22} {mark}")
        failed += 0 if ok else 1
    print("=" * 50)
    print(
        f"{G if failed == 0 else R}Result: {len(results) - failed}/{len(results)} passed{X}"
    )

    if not args.clean:
        print(f"\nScratch dir kept at: {scratch}")
    else:
        shutil.rmtree(scratch, ignore_errors=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
