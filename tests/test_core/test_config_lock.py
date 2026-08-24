"""Tests for core.config_lock (cross-process config transactions)."""

import pytest
from filelock import FileLock

from core import config_lock as cl


class TestConfigTransaction:
    def test_writes_and_bumps_version(self, tmp_path):
        cfg = tmp_path / "config.yaml"

        with cl.config_transaction(cfg) as data:
            data["a"] = 1

        assert cl.load_yaml(cfg) == {"a": 1}
        assert cl.read_config_version(cfg) == 1

    def test_second_transaction_increments_again(self, tmp_path):
        cfg = tmp_path / "config.yaml"

        with cl.config_transaction(cfg) as data:
            data["a"] = 1
        with cl.config_transaction(cfg) as data:
            data["b"] = 2

        assert cl.load_yaml(cfg) == {"a": 1, "b": 2}
        assert cl.read_config_version(cfg) == 2


class TestFailClosed:
    def test_lock_timeout_raises_and_does_not_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cl, "_LOCK_TIMEOUT", 0.2)
        cfg = tmp_path / "config.yaml"
        cl.save_yaml(cfg, {"a": 1})

        lock_path = cfg.with_suffix(cfg.suffix + ".lock")
        blocker = FileLock(lock_path)
        blocker.acquire()
        try:
            with (
                pytest.raises(cl.ConfigLockError),
                cl.config_transaction(cfg) as data,
            ):
                data["b"] = 2
        finally:
            blocker.release()

        # The write must not have happened and the version must be untouched.
        assert cl.load_yaml(cfg) == {"a": 1}
        assert cl.read_config_version(cfg) == 0
