#!/usr/bin/env python3
"""Local GitHub-compatible mock server for end-to-end updater tests.

The compiled updater (``update.exe`` / ``update.bin``) talks to exactly
three HTTP endpoints:

* ``GET <source>/repos/TechnikLey/Tiktok2Mc/releases/latest`` — returns
  a GitHub-shaped release JSON (``tag_name`` + ``assets`` with ``name``
  and ``url``).
* ``GET <asset url>`` — the platform archive (``.zip`` / ``.tar.gz``).
* ``GET <sha256 asset url>`` — the checksum file.

This module serves those endpoints over localhost so the real updater
runs its full production code path (JSON parsing, asset selection,
download, checksum verification, extraction, file copy, config
migration, exit codes) without any network access to GitHub.

Only the standard library is used — no new dependencies.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

RELEASE_PATH = "/repos/TechnikLey/Tiktok2Mc/releases/latest"


@dataclass
class MockGitHubState:
    """Mutable state the mock server serves per test scenario."""

    release_dir: Path
    release_json: dict[str, Any]
    # Overrides for error scenarios:
    release_status: int = 200
    release_body: bytes = b""
    # Seconds to sleep before answering (used for abort/timeout scenarios).
    release_delay: float = 0.0
    asset_delay: float = 0.0
    # Asset names that should 404 (simulates missing/broken downloads).
    asset_fail: set[str] = field(default_factory=set)


class _Handler(BaseHTTPRequestHandler):
    server_version = "MockGitHub/1.0"

    # ------------------------------------------------------------------
    # BaseHTTPRequestHandler API
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        state: MockGitHubState = self.server.state  # type: ignore[attr-defined]
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == RELEASE_PATH:
                self._send_release(state)
            elif path.startswith("/assets/"):
                self._send_asset(state, urllib.parse.unquote(path[len("/assets/") :]))
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away mid-response (e.g. aborted download)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # keep per-request noise out of the console

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def _send_release(self, state: MockGitHubState) -> None:
        if state.release_delay:
            time.sleep(state.release_delay)
        if state.release_status != 200:
            self._reply(state.release_status, state.release_body, "text/plain")
            return
        body = json.dumps(state.release_json).encode("utf-8")
        self._reply(200, body, "application/json")

    def _send_asset(self, state: MockGitHubState, name: str) -> None:
        if state.asset_delay:
            time.sleep(state.asset_delay)
        if name in state.asset_fail or not (state.release_dir / name).exists():
            self.send_error(404)
            return
        data = (state.release_dir / name).read_bytes()
        self._reply(200, data, "application/octet-stream")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MockGitHubServer:
    """A ``ThreadingHTTPServer`` that serves a ``MockGitHubState``.

    Call :meth:`start`, read :attr:`api_url`, and :meth:`stop` when done.
    """

    def __init__(self, state: MockGitHubState) -> None:
        self._state = state
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.state = state  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="mock-github",
        )

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def api_url(self) -> str:
        """Full URL the updater should be pointed at via the env var."""
        return f"{self.base_url}{RELEASE_PATH}"

    def start(self) -> MockGitHubServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)


def build_release_json(
    tag_name: str,
    archive_url: str,
    archive_name: str,
    include_checksum: bool = True,
) -> dict[str, Any]:
    """Build a GitHub-shaped release JSON for the mock server.

    ``archive_url`` is the absolute asset URL the server will serve.
    The companion ``.sha256`` asset is added when *include_checksum* is
    set, pointing at ``<archive_url>.sha256``.
    """
    assets: list[dict[str, str]] = [
        {"name": archive_name, "url": archive_url},
    ]
    if include_checksum:
        assets.append(
            {
                "name": f"{archive_name}.sha256",
                "url": f"{archive_url}.sha256",
            }
        )
    return {"tag_name": tag_name, "assets": assets}
