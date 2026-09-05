"""Unit tests for the shared PaperMC server.jar helpers.

Covers version support checks, the download-on-missing behavior, and the
auto-copy of a downloaded jar into instances that lack one. Network calls
are mocked — no real downloads.
"""

import pytest

from core import server_jar
from core.server_jar import (
    ServerJarError,
    copy_version_jar_to_instances,
    ensure_instance_jar,
    ensure_version_jar,
    is_supported_version,
)


@pytest.fixture(autouse=True)
def _fake_paths(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    servers = tmp_path / "server"
    monkeypatch.setattr(server_jar, "get_versions_dir", lambda: versions)
    monkeypatch.setattr(server_jar, "get_servers_dir", lambda: servers)
    return {"versions": versions, "servers": servers}


class TestIsSupportedVersion:
    def test_supported_stable(self):
        assert is_supported_version("1.21.11") is True

    def test_minimum_supported(self):
        assert is_supported_version("1.13") is True

    def test_below_minimum_rejected(self):
        assert is_supported_version("1.12") is False

    def test_pre_release_rejected(self):
        assert is_supported_version("1.21.1-pre1") is False

    def test_garbage_rejected(self):
        assert is_supported_version("abc") is False


class TestEnsureVersionJar:
    def test_returns_existing_jar(self, _fake_paths):
        jar = _fake_paths["versions"] / "1.21.11" / "server.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"existing")
        assert ensure_version_jar("1.21.11") == jar

    def test_downloads_when_missing(self, _fake_paths, monkeypatch):
        import io

        monkeypatch.setattr(
            server_jar, "resolve_download_url", lambda v: "https://example.invalid/jar"
        )

        def fake_urlopen(*_a, **_k):
            return io.BytesIO(b"downloaded jar bytes")

        monkeypatch.setattr(server_jar.urllib.request, "urlopen", fake_urlopen)
        jar = ensure_version_jar("1.21.11")
        assert jar.exists()
        assert jar.stat().st_size > 0
        assert jar.parent.name == "1.21.11"

    def test_raises_when_unsupported(self, _fake_paths):
        with pytest.raises(ServerJarError):
            ensure_version_jar("1.12")

    def test_raises_after_download_failures(self, _fake_paths, monkeypatch):
        monkeypatch.setattr(
            server_jar, "resolve_download_url", lambda v: "https://example.invalid/jar"
        )

        def boom(*_a, **_k):
            raise OSError("connection refused")

        monkeypatch.setattr(server_jar.urllib.request, "urlopen", boom)
        with pytest.raises(ServerJarError):
            ensure_version_jar("1.21.11")


class TestEnsureInstanceJar:
    def test_copies_from_version_library(self, _fake_paths):
        version_jar = _fake_paths["versions"] / "1.21.11" / "server.jar"
        version_jar.parent.mkdir(parents=True)
        version_jar.write_bytes(b"version jar")

        instance_jar = ensure_instance_jar("default", "1.21.11")
        assert instance_jar.exists()
        assert instance_jar.read_bytes() == b"version jar"

    def test_downloads_version_then_copies(self, _fake_paths, monkeypatch):
        import io

        calls = []
        monkeypatch.setattr(
            server_jar,
            "resolve_download_url",
            lambda v: calls.append(v) or "https://example.invalid/jar",
        )

        def fake_urlopen(*_a, **_k):
            return io.BytesIO(b"downloaded jar bytes")

        monkeypatch.setattr(server_jar.urllib.request, "urlopen", fake_urlopen)
        instance_jar = ensure_instance_jar("test1", "1.21.11")
        assert instance_jar.exists()
        assert calls == ["1.21.11"]

    def test_returns_existing_instance_jar(self, _fake_paths):
        instance = _fake_paths["servers"] / "default"
        instance.mkdir(parents=True)
        (instance / "server.jar").write_bytes(b"mine")
        jar = ensure_instance_jar("default", "1.21.11")
        assert jar.read_bytes() == b"mine"


class TestCopyVersionJarToInstances:
    def test_copies_into_missing_only(self, _fake_paths):
        version_jar = _fake_paths["versions"] / "1.21.11" / "server.jar"
        version_jar.parent.mkdir(parents=True)
        version_jar.write_bytes(b"vjar")

        missing = _fake_paths["servers"] / "missing"
        missing.mkdir(parents=True)
        present = _fake_paths["servers"] / "present"
        present.mkdir(parents=True)
        (present / "server.jar").write_bytes(b"nope")

        assert copy_version_jar_to_instances("1.21.11") == 1
        assert (missing / "server.jar").read_bytes() == b"vjar"
        assert (present / "server.jar").read_bytes() == b"nope"

    def test_noop_without_version_jar(self, _fake_paths):
        assert copy_version_jar_to_instances("1.21.11") == 0
