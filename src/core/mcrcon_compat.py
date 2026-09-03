"""Thread-safe compatibility shim for the third-party ``mcrcon`` library.

The upstream ``MCRcon`` uses ``signal.signal``/``signal.alarm`` for read
timeouts on POSIX (Linux/macOS).  ``signal`` calls are only allowed from the
main thread, but this application runs mcrcon inside worker threads (the API
server's ``RconService.connect`` and the bridge's RCON worker both use
``asyncio.to_thread``).  On Linux that raises::

    ValueError: signal only works in main thread of the main interpreter

so the console "Connect" fails even though the Minecraft server is reachable.
This module monkeypatches ``MCRcon`` to use per-socket timeouts instead of
``SIGALRM``.  Per-socket timeouts are safe in any thread and behave the same
at the application level: a read that exceeds ``timeout`` raises an exception
instead of blocking forever.

Import this module once (it patches in place and the patch is idempotent)
from any code that constructs an ``MCRcon``.
"""

from __future__ import annotations

import inspect
import socket

from mcrcon import MCRcon, MCRconException

_patched = False


def _patch() -> None:
    """Apply the socket-timeout patch to ``MCRcon`` exactly once."""
    global _patched
    if _patched:
        return
    # In tests the ``mcrcon`` module is replaced by a MagicMock (see
    # tests/conftest.py).  ``MCRcon`` is then not a real class, and there is
    # nothing to patch — skip so importing this module does not break tests.
    if not inspect.isclass(MCRcon):
        return
    _patched = True

    def _init(self, host, password, port=25575, tlsmode=0, timeout=5):
        self.host = host
        self.password = password
        self.port = port
        self.tlsmode = tlsmode
        self.timeout = timeout

    def _connect(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Per-socket timeout works in any thread (signal.alarm does not).
        self.socket.settimeout(self.timeout)
        if self.tlsmode > 0:
            import ssl

            ctx = ssl.create_default_context()
            if self.tlsmode > 1:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self.socket = ctx.wrap_socket(self.socket, server_hostname=self.host)
        self.socket.connect((self.host, self.port))
        self._send(3, self.password)

    def _read(self, length: int) -> bytes:
        data = b""
        while len(data) < length:
            try:
                data += self.socket.recv(length - len(data))
            except TimeoutError:
                raise MCRconException("Connection timeout error") from None
        return data

    MCRcon.__init__ = _init  # type: ignore[assignment]
    MCRcon.connect = _connect  # type: ignore[assignment]
    MCRcon._read = _read  # type: ignore[assignment]


_patch()
