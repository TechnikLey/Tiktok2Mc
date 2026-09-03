"""Tests for core.mcrcon_compat — the thread-safe mcrcon timeout patch.

The upstream ``mcrcon`` library uses ``signal.signal``/``signal.alarm`` for
read timeouts on POSIX, which is illegal in worker threads.  ``core.mcrcon_compat``
patches ``MCRcon`` to use per-socket timeouts instead.  Because the global
``tests/conftest.py`` replaces ``mcrcon`` with a MagicMock, these tests install a
small real class into ``sys.modules`` so the (re)imported) compat module patches a
genuine ``MCRcon``-like object.
"""

import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest


class _FakeMCRcon:
    """Minimal stand-in for upstream ``mcrcon.MCRcon``."""

    def __init__(self, host, password, port=25575, tlsmode=0, timeout=5):
        self.host = host
        self.password = password
        self.port = port
        self.tlsmode = tlsmode
        self.timeout = timeout

    def connect(self) -> None:
        self.socket = None

    def _read(self, length: int) -> bytes:  # upstream: uses signal.alarm
        return b""


def _install_fake_mcrcon() -> None:
    mod = types.ModuleType("mcrcon")
    mod.MCRcon = _FakeMCRcon
    mod.MCRconException = type("MCRconException", (Exception,), {})
    sys.modules["mcrcon"] = mod


def _load_compat_fresh():
    sys.modules.pop("core.mcrcon_compat", None)
    return importlib.import_module("core.mcrcon_compat")


def test_patch_applied_to_real_class():
    _install_fake_mcrcon()
    compat = _load_compat_fresh()
    compat._patched = False
    compat._patch()

    from mcrcon import MCRcon, MCRconException

    # The patched _read must translate a socket timeout to MCRconException
    # (the original _FakeMCRcon._read does not).
    m = MCRcon("h", "p", port=1)
    m.socket = MagicMock()
    m.socket.recv.side_effect = TimeoutError("timed out")
    with pytest.raises(MCRconException):
        m._read(4)
    # The patched __init__ stores the timeout (a signal handler is not set).
    assert m.timeout == 5


def test_patch_is_idempotent():
    _install_fake_mcrcon()
    compat = _load_compat_fresh()
    compat._patched = False
    compat._patch()
    compat._patch()  # second call must not fail or double-patch
    from mcrcon import MCRcon

    assert MCRcon._read.__code__.co_name == "_read"


def test_patch_skipped_for_magic_mock():
    # Simulate tests/conftest.py: mcrcon is a MagicMock, MCRcon is not a class.
    mock = MagicMock()
    mock.MCRconException = type("MCRconException", (Exception,), {})
    sys.modules["mcrcon"] = mock

    # Importing must not raise (patch is skipped, not fatal).
    compat = _load_compat_fresh()
    assert compat._patch() is None


def test_patched_read_raises_on_timeout():
    _install_fake_mcrcon()
    compat = _load_compat_fresh()
    compat._patched = False
    compat._patch()

    from mcrcon import MCRcon, MCRconException

    m = MCRcon("localhost", "pw", port=1)
    m.socket = MagicMock()
    m.socket.recv.side_effect = TimeoutError("timed out")

    with pytest.raises(MCRconException):
        m._read(4)
