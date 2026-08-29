"""Unit tests for core.java_utils (Java detection & installation helpers)."""

from pathlib import Path
from unittest import mock

import pytest

from core import java_utils


@pytest.fixture
def fake_java(tmp_path):
    java = tmp_path / "java"
    java.write_text("fake", encoding="utf-8")
    return java


class TestVersionParsing:
    def test_major_modern(self, monkeypatch, fake_java):
        monkeypatch.setattr(
            java_utils.subprocess,
            "run",
            lambda *a, **k: mock.Mock(
                stderr='openjdk version "21.0.2" 2024-01-16', stdout="", returncode=0
            ),
        )
        assert java_utils.java_major_version(fake_java) == 21

    def test_major_java8(self, monkeypatch, fake_java):
        monkeypatch.setattr(
            java_utils.subprocess,
            "run",
            lambda *a, **k: mock.Mock(
                stderr='java version "1.8.0_392"', stdout="", returncode=0
            ),
        )
        assert java_utils.java_major_version(fake_java) == 8

    def test_version_string(self, monkeypatch, fake_java):
        monkeypatch.setattr(
            java_utils.subprocess,
            "run",
            lambda *a, **k: mock.Mock(
                stderr='openjdk version "21.0.2"', stdout="", returncode=0
            ),
        )
        assert java_utils.java_version_string(fake_java) == "21.0.2"

    def test_is_usable_missing(self):
        assert java_utils.java_is_usable(Path("does/not/exist/java")) is False

    def test_is_usable_too_old(self, monkeypatch, fake_java):
        monkeypatch.setattr(java_utils, "java_major_version", lambda p: 8)
        assert java_utils.java_is_usable(fake_java) is False

    def test_is_usable_ok(self, monkeypatch, fake_java):
        monkeypatch.setattr(java_utils, "java_major_version", lambda p: 25)
        assert java_utils.java_is_usable(fake_java) is True


def _no_java(monkeypatch):
    monkeypatch.setattr(java_utils, "_system_java_path", lambda: None)
    monkeypatch.setattr(java_utils, "_java_home_path", lambda: None)
    monkeypatch.setattr(java_utils, "java_major_version", lambda p: 25)
    monkeypatch.setattr(java_utils, "java_version_string", lambda p: "21.0.2")


class TestDetect:
    def test_not_found(self, monkeypatch, tmp_path):
        _no_java(monkeypatch)
        status = java_utils.detect_java(tmp_path)
        assert status.ok is False
        assert status.reason
        assert status.hints

    def test_system_java(self, monkeypatch, tmp_path, fake_java):
        _no_java(monkeypatch)
        monkeypatch.setattr(java_utils, "_system_java_path", lambda: fake_java)
        status = java_utils.detect_java(tmp_path)
        assert status.ok is True
        assert status.source == "system"

    def test_system_java_too_old(self, monkeypatch, tmp_path, fake_java):
        monkeypatch.setattr(java_utils, "_system_java_path", lambda: fake_java)
        monkeypatch.setattr(java_utils, "_java_home_path", lambda: None)
        monkeypatch.setattr(java_utils, "java_major_version", lambda p: 8)
        monkeypatch.setattr(java_utils, "java_version_string", lambda p: "1.8.0")
        status = java_utils.detect_java(tmp_path)
        assert status.ok is False
        assert "too old" in status.reason

    def test_java_home_used(self, monkeypatch, tmp_path, fake_java):
        _no_java(monkeypatch)
        monkeypatch.setattr(java_utils, "_java_home_path", lambda: fake_java)
        status = java_utils.detect_java(tmp_path)
        assert status.ok is True
        assert status.source == "system"

    def test_broken_shim_falls_through_to_java_home(
        self, monkeypatch, tmp_path, fake_java
    ):
        """A PATH 'java' that reports no version (Oracle javapath shim after
        an uninstall) must not abort detection - JAVA_HOME is still checked."""
        _no_java(monkeypatch)
        shim = tmp_path / "shim" / "java"
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.write_text("fake", encoding="utf-8")
        monkeypatch.setattr(java_utils, "_system_java_path", lambda: shim)
        monkeypatch.setattr(
            java_utils, "java_major_version", lambda p: None if p == shim else 25
        )
        monkeypatch.setattr(java_utils, "_java_home_path", lambda: fake_java)
        status = java_utils.detect_java(tmp_path)
        assert status.ok is True
        assert status.source == "system"

    def test_all_unusable_reason_lists_every_source(
        self, monkeypatch, tmp_path, fake_java
    ):
        monkeypatch.setattr(java_utils, "_java_home_path", lambda: fake_java)
        monkeypatch.setattr(java_utils, "_system_java_path", lambda: fake_java)
        monkeypatch.setattr(java_utils, "java_major_version", lambda p: 8)
        monkeypatch.setattr(java_utils, "java_version_string", lambda p: "1.8.0")
        status = java_utils.detect_java(tmp_path)
        assert status.ok is False
        assert "JAVA_HOME" in status.reason
        assert "PATH" in status.reason
        assert "too old" in status.reason

    def test_config_custom_path(self, monkeypatch, tmp_path, fake_java):
        _no_java(monkeypatch)
        config = tmp_path / "config.yaml"
        config.write_text("java: {}\n", encoding="utf-8")
        monkeypatch.setattr(
            java_utils, "java_is_usable", lambda p, min_version=17: p == fake_java
        )
        monkeypatch.setattr(
            "core.yaml_utils.load_yaml",
            lambda *a, **k: {"java": {"path": str(fake_java)}},
        )
        status = java_utils.detect_java(tmp_path, config_path=config)
        assert status.ok is True
        assert status.source == "config"

    def test_config_custom_path_not_usable(self, monkeypatch, tmp_path, fake_java):
        monkeypatch.setattr(java_utils, "java_major_version", lambda p: 8)
        monkeypatch.setattr(java_utils, "java_version_string", lambda p: "1.8.0")
        monkeypatch.setattr(java_utils, "_system_java_path", lambda: None)
        config = tmp_path / "config.yaml"
        config.write_text("java: {}\n", encoding="utf-8")
        monkeypatch.setattr(
            "core.yaml_utils.load_yaml",
            lambda *a, **k: {"java": {"path": str(fake_java)}},
        )
        status = java_utils.detect_java(tmp_path, config_path=config)
        assert status.ok is False
        assert "not usable" in status.reason

    def test_bundled_java(self, monkeypatch, tmp_path, fake_java):
        _no_java(monkeypatch)
        bundled = (
            tmp_path
            / "server"
            / "java"
            / "bin"
            / ("java.exe" if __import__("sys").platform == "win32" else "java")
        )
        bundled.parent.mkdir(parents=True, exist_ok=True)
        bundled.write_text("fake", encoding="utf-8")
        monkeypatch.setattr(java_utils, "bundled_java_path", lambda root: bundled)
        status = java_utils.detect_java(tmp_path)
        assert status.ok is True
        assert status.source == "bundled"


class TestHints:
    def test_hints_nonempty(self):
        assert java_utils.install_hints()


class TestInstallSources:
    def test_all_sources_well_formed(self):
        assert java_utils._JDK_SOURCES, "at least one download source required"
        for src in java_utils._JDK_SOURCES:
            assert src["url"].startswith("https://github.com/adoptium/")
            assert src["url"].endswith(".zip")
            # real SHA256: exactly 64 hex chars
            assert len(src["sha256"]) == 64
            int(src["sha256"], 16)  # raises ValueError on non-hex


class TestInstallWindows:
    def test_checksum_mismatch_tries_all_mirrors(self, monkeypatch, tmp_path):
        monkeypatch.setattr(java_utils, "platform", mock.Mock(system=lambda: "Windows"))
        monkeypatch.setattr(
            java_utils, "java_is_usable", lambda p, min_version=21: False
        )
        monkeypatch.setattr(java_utils, "_download_file", lambda *a, **k: None)
        monkeypatch.setattr(java_utils, "_verify_checksum", lambda *a, **k: False)
        ok, message = java_utils.install_java_windows(tmp_path)
        assert ok is False
        assert f"{len(java_utils._JDK_SOURCES)} mirrors" in message

    def test_successful_install(self, monkeypatch, tmp_path):
        java_bin = (tmp_path / "server" / "java" / "bin" / "java.exe").resolve()
        state = {"extracted": False}
        monkeypatch.setattr(java_utils, "platform", mock.Mock(system=lambda: "Windows"))
        monkeypatch.setattr(
            java_utils,
            "java_is_usable",
            lambda p, min_version=21: state["extracted"] and p == java_bin,
        )
        monkeypatch.setattr(java_utils, "_download_file", lambda *a, **k: None)
        monkeypatch.setattr(java_utils, "_verify_checksum", lambda *a, **k: True)

        class FakeZip:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extractall(self, dest):
                top = Path(dest) / "jdk-21.0.12+8-jre"
                (top / "bin").mkdir(parents=True, exist_ok=True)
                (top / "bin" / "java.exe").write_text("fake", encoding="utf-8")
                state["extracted"] = True

        monkeypatch.setattr(java_utils.zipfile, "ZipFile", FakeZip)
        ok, message = java_utils.install_java_windows(tmp_path)
        assert ok is True
        assert "Java 25 downloaded and extracted" in message
        assert java_bin.exists()


class TestEnsure:
    def test_returns_detected_when_ok(self, monkeypatch, tmp_path, fake_java):
        _no_java(monkeypatch)
        monkeypatch.setattr(java_utils, "_system_java_path", lambda: fake_java)
        status = java_utils.ensure_java(tmp_path, install=True)
        assert status.ok is True
        assert status.source == "system"

    def test_no_install_on_unsupported(self, monkeypatch, tmp_path):
        _no_java(monkeypatch)
        monkeypatch.setattr(java_utils, "platform", mock.Mock(system=lambda: "TestOS"))
        status = java_utils.ensure_java(tmp_path, install=True)
        assert status.ok is False
