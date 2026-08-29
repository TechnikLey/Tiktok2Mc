#!/usr/bin/env python3
"""End-to-end updater test harness (update.exe / update.bin).

Builds a realistic old installation, serves a GitHub-compatible fake
release via ``mock_github.py`` and runs the *compiled* updater against
it, so the real production code path of ``src/python/update.py`` is
exercised end to end: version check, asset selection, download, checksum
verification, extraction, updater self-update, whitelisted file copy,
config migration and exit codes.

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
from mock_github import (  # noqa: E402
    MockGitHubServer,
    MockGitHubState,
    build_release_json,
)
from ruamel.yaml import YAML  # noqa: E402

from core.api.server import DEFAULT_PORT  # noqa: E402
from core.version import TOOL_VERSION, UPDATER_VERSION  # noqa: E402

if os.name == "nt":
    os.system("")

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"
PLATFORM_LABEL = "Windows" if sys.platform == "win32" else "Linux"
ARCHIVE_EXT = "zip" if sys.platform == "win32" else "tar.gz"
UPDATE_SOURCE_ENV = "TIKTOK2MC_UPDATE_SOURCE"
SIGNAL_PATH = "/api/v1/updater/signal"

C = "\033[96m"
G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
X = "\033[0m"

# ---------------------------------------------------------------------------
# Templates (realistic, versioned configs so migration can be asserted)
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
# Control-plane signal simulation
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
    """Fake control-plane kill-signal endpoint on ``DEFAULT_PORT``.

    In production this endpoint is provided by the running app and
    ``start.py`` consumes the kill signal. Binding it here means the
    compiled updater's API signaling behaves exactly like production,
    and — because we hold the port — no real instance can be
    accidentally signalled during the test.
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


class FileSignalConsumer(threading.Thread):
    """Mimics start.py: deletes ``update_signal.tmp`` as soon as it appears.

    Without a consumer the compiled updater would wait up to 30 seconds
    in its kill-signal wait loop. Consuming the file (exactly like
    ``start.py`` does) keeps the flow realistic and fast.
    """

    def __init__(self, install: Path) -> None:
        super().__init__(daemon=True, name="signal-consumer")
        self._signal = install / "update_signal.tmp"
        # NOTE: must not be named ``_stop`` — that would shadow
        # ``threading.Thread._stop()`` and ``join()`` would call the
        # ``threading.Event`` instance instead of the method.
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(0.2):
            try:
                if self._signal.exists():
                    self._signal.unlink()
            except OSError:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=2.0)


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

    def save_output(self, scenario: str, output: str) -> Path:
        log_dir = self.scratch / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{scenario}.log"
        path.write_text(output, encoding="utf-8")
        return path

    # ---- install / release / archive ------------------------------------

    def prepare_install(self) -> Path:
        install = self.scratch / "install"
        if install.exists():
            shutil.rmtree(install)
        install.mkdir(parents=True)
        shutil.copy2(self.updater, install / f"update{SUFFIX}")
        self.write(
            install / "version.txt",
            f"ToolVersion: {self.old_tool}\nUpdaterVersion: {self.old_updater}\n",
        )
        self.write(install / "README.md", "old readme")
        self.write(install / "LICENSE", "old license")
        self.write(install / f"start{SUFFIX}", "old start")
        self.write(install / "core" / f"app{SUFFIX}", "old app")
        self.write(install / "core" / f"server{SUFFIX}", "old server")
        self.write(install / "core" / "marker.txt", "OLD")
        self.write(install / "plugins" / "wincounter" / "main.py", "old wincounter")
        self.write(install / "config" / "config.yaml", INSTALL_CONFIG)
        self.write(install / "config" / "config.default.yaml", INSTALL_DEFAULT)
        return install

    def prepare_release(
        self, *, with_updater: bool = False, updater_version: str | None = None
    ) -> Path:
        release = self.scratch / "release"
        if release.exists():
            shutil.rmtree(release)
        release.mkdir(parents=True)
        rel_updater = updater_version or self.new_updater
        self.write(
            release / "version.txt",
            f"ToolVersion: {self.new_tool}\nUpdaterVersion: {rel_updater}\n",
        )
        self.write(release / "README.md", "new readme")
        self.write(release / "LICENSE", "new license")
        self.write(release / f"start{SUFFIX}", "new start")
        self.write(release / "core" / f"app{SUFFIX}", "new app")
        self.write(release / "core" / f"server{SUFFIX}", "new server")
        self.write(release / "core" / "marker.txt", "NEW")
        self.write(release / "config" / "config.yaml", "must_not_be_copied\n")
        self.write(release / "config" / "config.default.yaml", RELEASE_DEFAULT)
        self.write(release / "plugins" / "wincounter" / "main.py", "new wincounter")
        if with_updater:
            shutil.copy2(self.updater, release / "core" / f"update{SUFFIX}")
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
    ) -> RunResult:
        env = os.environ.copy()
        env[UPDATE_SOURCE_ENV] = api_url
        cmd = [str(install / f"update{SUFFIX}")]
        if auto:
            cmd.append("--auto")
        consumer = FileSignalConsumer(install)
        consumer.start()
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
        finally:
            consumer.stop()

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

    def wait_for_self_update(self, install: Path, timeout: float = 180.0) -> None:
        """Wait for the ``update_new.exe --resume`` child process to finish."""
        proc_name = f"update_new{SUFFIX}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if (
                not self._proc_running(proc_name)
                and self.read_versions(install)["tool"] == self.new_tool
            ):
                return
            time.sleep(1.0)
        raise AssertionError("self-update child process did not finish in time")

    @staticmethod
    def _proc_running(name: str) -> bool:
        try:
            if sys.platform == "win32":
                r = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                    capture_output=True,
                    text=True,
                    errors="replace",  # tasklist output is not always cp1252-clean
                    timeout=15,
                    check=False,
                )
                return (r.stdout or "").lower().find(name.lower()) != -1
            r = subprocess.run(
                ["pgrep", "-x", name],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                check=False,
            )
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return True  # assume still running; keeps the wait loop conservative

    # ---- assertions ------------------------------------------------------

    def assert_updated(
        self, install: Path, expected_updater: str | None = None
    ) -> None:
        target_updater = expected_updater or self.new_updater
        v = self.read_versions(install)
        self.expect(
            v["tool"] == self.new_tool,
            f"version.txt tool = {v['tool']!r} (expected {self.new_tool!r})",
        )
        self.expect(
            v["updater"] == target_updater,
            f"version.txt updater = {v['updater']!r} (expected {target_updater!r})",
        )
        self.expect(
            (install / "core" / f"app{SUFFIX}").read_text(encoding="utf-8")
            == "new app",
            "core/app.exe was not updated",
        )
        self.expect(
            (install / "core" / "marker.txt").read_text(encoding="utf-8") == "NEW",
            "core/marker.txt was not updated",
        )
        self.expect(
            (install / "plugins" / "wincounter" / "main.py").read_text(encoding="utf-8")
            == "new wincounter",
            "plugin file was not updated",
        )
        self.expect(
            (install / "README.md").read_text(encoding="utf-8") == "new readme",
            "README.md was not updated",
        )
        self.expect(
            (install / f"start{SUFFIX}").read_text(encoding="utf-8") == "new start",
            "start was not updated",
        )
        self.expect(
            (install / "config" / "config.yaml").read_text(encoding="utf-8")
            != "must_not_be_copied\n",
            "config.yaml must never be overwritten by the release file",
        )
        cfg = self.read_config(install)
        self.expect(
            str(cfg.get("config_version")) == "1.0",
            f"config_version = {cfg.get('config_version')!r} (expected '1.0')",
        )
        self.expect(
            cfg.get("server_host") == "192.168.1.100",
            f"user config value server_host was not preserved: {cfg.get('server_host')!r}",
        )
        self.expect(
            cfg.get("java", {}).get("xms") == "1G",
            f"user config value java.xms was not preserved: {cfg.get('java', {}).get('xms')!r}",
        )
        self.expect(
            not (install / "_update_tmp").exists(),
            "_update_tmp was not cleaned up",
        )

    def assert_unchanged(self, install: Path) -> None:
        v = self.read_versions(install)
        self.expect(
            v["tool"] == self.old_tool,
            f"version.txt tool = {v['tool']!r} (expected {self.old_tool!r})",
        )
        self.expect(
            v["updater"] == self.old_updater,
            f"version.txt updater = {v['updater']!r} (expected {self.old_updater!r})",
        )
        self.expect(
            (install / "core" / f"app{SUFFIX}").read_text(encoding="utf-8")
            == "old app",
            "core/app.exe was modified although nothing should have been installed",
        )
        self.expect(
            (install / "core" / "marker.txt").read_text(encoding="utf-8") == "OLD",
            "core/marker.txt was modified although nothing should have been installed",
        )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_success(h: Harness) -> bool:
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
    print(f"{G}  OK: files updated, config migrated, exit 0{X}")
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
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
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


def scenario_missing_checksum(h: Harness) -> bool:
    install = h.prepare_install()
    release = h.prepare_release()
    _, name = h.make_archive(release)
    server = h.start_server(
        tag_name=f"v{h.new_tool}", archive_name=name, include_checksum=False
    )
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("missing_checksum", r.output)
    h.expect(r.returncode == 12, f"exit {r.returncode} (expected 12)\n{r.output}")
    h.expect("checksum" in r.output.lower(), "expected checksum message")
    h.assert_unchanged(install)
    print(f"{G}  OK: missing checksum aborts update, exit 12{X}")
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
        r = h.run_updater(install, server.api_url)
    finally:
        server.stop()
    h.save_output("api_error", r.output)
    h.expect(r.returncode == 10, f"exit {r.returncode} (expected 10)\n{r.output}")
    h.expect("API error" in r.output, "expected API error message")
    h.assert_unchanged(install)
    print(f"{G}  OK: API error handled, exit 10{X}")
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
        h.wait_for_self_update(install)
    finally:
        server.stop()
    h.expect(r.returncode == 0, f"exit {r.returncode} (expected 0)\n{r.output}")
    h.expect(
        (install / f"update_new{SUFFIX}").exists(),
        f"update_new{SUFFIX} was not created",
    )
    h.assert_updated(install, expected_updater="9.9.9")
    print(f"{G}  OK: updater self-update + resume completed{X}")
    return True


def scenario_locked_file(h: Harness) -> bool:
    if sys.platform != "win32":
        print(f"{Y}  (skipped — Windows-only scenario){X}")
        return True
    install = h.prepare_install()
    release = h.prepare_release()
    archive, name = h.make_archive(release)
    h.write_checksum(archive, name)
    server = h.start_server(tag_name=f"v{h.new_tool}", archive_name=name)
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
    dst = install / "core" / f"app{SUFFIX}"
    handle = kernel32.CreateFileW(
        str(dst), 0x80000000, 0, None, 3, 0, None
    )  # no shared access
    if not handle or handle == ctypes.c_void_p(-1).value:
        server.stop()
        print(f"{Y}  (skipped — could not lock {dst.name}){X}")
        return True
    try:
        r = h.run_updater(install, server.api_url)
    finally:
        kernel32.CloseHandle(handle)
        server.stop()
    h.expect(r.returncode == 15, f"exit {r.returncode} (expected 15)\n{r.output}")
    h.expect(
        (install / "core" / f"app{SUFFIX}").read_text(encoding="utf-8") == "old app",
        "locked app.exe was overwritten despite the lock",
    )
    print(f"{G}  OK: locked file aborts update, locked file untouched{X}")
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


SCENARIOS: list[tuple[str, str, Callable[[Harness], bool]]] = [
    ("success", "older -> newer version, full update", scenario_success),
    ("up_to_date", "installed version == latest -> no update", scenario_up_to_date),
    ("missing_asset", "release has no platform archive", scenario_missing_asset),
    ("missing_checksum", "release has no .sha256 asset", scenario_missing_checksum),
    ("bad_checksum", "archive checksum does not match", scenario_bad_checksum),
    ("invalid_version", "malformed release tag", scenario_invalid_version),
    ("api_error", "GitHub API returns HTTP 500", scenario_api_error),
    ("download_error", "archive download fails (404)", scenario_download_error),
    ("abort_download", "updater killed mid-download", scenario_abort_download),
    ("self_update", "new updater version in release", scenario_self_update),
    ("locked_file", "in-use destination file (Windows)", scenario_locked_file),
    (
        "retry_after_failure",
        "failed update then successful retry",
        scenario_retry_after_failure,
    ),
    ("beta_prompt", "beta release prompt (decline + accept)", scenario_beta_prompt),
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
            print(f"  {name:<20} {desc}")
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
            print(f"  {name:<20} {desc}")
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
