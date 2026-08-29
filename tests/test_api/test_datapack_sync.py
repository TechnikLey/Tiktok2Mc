import os
import time
from pathlib import Path

from core.api.services.datapack import (
    DATAPACK_NAME,
    sync_datapack,
    wait_for_datapack,
)


def _make_vanilla_function(source: Path) -> Path:
    """Create the skeleton of a freshly generated datapack and return its function file."""
    fn_dir = source / DATAPACK_NAME / "data" / "streamingtool" / "function"
    fn_dir.mkdir(parents=True)
    func = fn_dir / "likes.mcfunction"
    func.write_text("summon minecraft:creeper ~ ~ ~\n", encoding="utf-8")
    return func


class TestSyncDatapack:
    def test_copies_folder_and_zip_into_world_datapacks(self, tmp_path):
        source = tmp_path / "store"
        _make_vanilla_function(source)
        (source / f"{DATAPACK_NAME}.zip").write_bytes(b"zip")
        instance = tmp_path / "server" / "default"
        (instance / "world" / "datapacks" / "bukkit").mkdir(parents=True)

        result = sync_datapack(instance, source)

        assert result is not None
        assert result == instance / "world" / "datapacks"
        assert (result / "bukkit").is_dir()
        assert (
            result
            / DATAPACK_NAME
            / "data"
            / "streamingtool"
            / "function"
            / "likes.mcfunction"
        ).is_file()
        assert (result / f"{DATAPACK_NAME}.zip").read_bytes() == b"zip"

    def test_replaces_previous_copy(self, tmp_path):
        source = tmp_path / "store"
        _make_vanilla_function(source)
        (source / f"{DATAPACK_NAME}.zip").write_bytes(b"fresh")
        instance = tmp_path / "instance"
        old = instance / "world" / "datapacks" / DATAPACK_NAME
        old.mkdir(parents=True)
        (old / "stale.mcfunction").write_text("old", encoding="utf-8")
        (instance / "world" / "datapacks" / f"{DATAPACK_NAME}.zip").write_bytes(b"old")

        sync_datapack(instance, source)

        target = instance / "world" / "datapacks"
        assert not (target / DATAPACK_NAME / "stale.mcfunction").exists()
        assert (target / f"{DATAPACK_NAME}.zip").read_bytes() == b"fresh"
        assert (target / DATAPACK_NAME / "data" / "streamingtool" / "function").is_dir()

    def test_missing_source_returns_none_without_creating_world(self, tmp_path):
        instance = tmp_path / "instance"
        assert sync_datapack(instance, tmp_path / "nope") is None
        assert not (instance / "world").exists()

    def test_empty_source_dir_returns_none(self, tmp_path):
        source = tmp_path / "store"
        source.mkdir()
        instance = tmp_path / "instance"
        assert sync_datapack(instance, source) is None


class TestWaitForDatapack:
    def test_returns_true_when_zip_newer_than_folder_content(self, tmp_path):
        source = tmp_path / "store"
        _make_vanilla_function(source)
        (source / f"{DATAPACK_NAME}.zip").write_bytes(b"z")

        assert wait_for_datapack(source, timeout=1.0) is True

    def test_returns_false_when_zip_missing(self, tmp_path):
        source = tmp_path / "store"
        _make_vanilla_function(source)

        assert wait_for_datapack(source, timeout=0.1, poll=0.01) is False

    def test_returns_false_when_zip_stale_during_rebuild(self, tmp_path):
        source = tmp_path / "store"
        func = _make_vanilla_function(source)
        zip_path = source / f"{DATAPACK_NAME}.zip"
        zip_path.write_bytes(b"stale")
        # Old zip from a previous generation, folder currently being rebuilt:
        # the newest file is newer than the archive → not complete yet.
        os.utime(zip_path, (0, 0))
        assert func.stat().st_mtime > 0
        assert wait_for_datapack(source, timeout=0.1, poll=0.01) is False

    def test_becomes_true_once_archive_arrives(self, tmp_path):
        source = tmp_path / "store"
        _make_vanilla_function(source)
        zip_path = source / f"{DATAPACK_NAME}.zip"
        assert wait_for_datapack(source, timeout=2.0, poll=0.01) is False
        time.sleep(0.05)
        zip_path.write_bytes(b"z")
        assert wait_for_datapack(source, timeout=2.0, poll=0.01) is True
