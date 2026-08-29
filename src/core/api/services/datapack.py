"""Datapack sync helpers for Minecraft server instances.

``generate_datapack`` (in ``src.python.main``) writes the StreamingTool
datapack into a central staging area (``server/datapack/``). The datapack
only has an effect in-game when it also lands in a server instance's
``world/datapacks/`` — this module centralises that copy for every
consumer (API instance start, supervisor boot, runtime actions reload).
"""

import logging
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)

DATAPACK_NAME = "StreamingTool"

_DATAPACK_WAIT_TIMEOUT = 30.0
_DATAPACK_WAIT_POLL = 0.5


def sync_datapack(instance_dir: Path, source_dir: Path) -> Path | None:
    """Copy the StreamingTool datapack (folder + zip) into *instance_dir*.

    Creates ``<instance_dir>/world/datapacks`` when missing and replaces any
    previous StreamingTool copy. Returns the instance datapack root path on
    success, or ``None`` when there is nothing to sync or the copy fails.
    """
    src_dir = source_dir / DATAPACK_NAME
    src_zip = source_dir / f"{DATAPACK_NAME}.zip"
    if not src_dir.exists() and not src_zip.exists():
        log.warning("[DATAPACK] Source datapack missing at %s", source_dir)
        return None

    instance_dp = instance_dir / "world" / "datapacks"
    try:
        instance_dp.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("[DATAPACK] Cannot create '%s': %s", instance_dp, exc)
        return None

    dst_dir = instance_dp / DATAPACK_NAME
    dst_zip = instance_dp / f"{DATAPACK_NAME}.zip"
    try:
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        if dst_zip.exists():
            dst_zip.unlink()
        if src_dir.exists():
            shutil.copytree(src_dir, dst_dir)
        if src_zip.exists():
            shutil.copy2(src_zip, dst_zip)
        log.info(
            "[DATAPACK] Synced '%s' datapack to instance '%s'",
            DATAPACK_NAME,
            instance_dir,
        )
        return instance_dp
    except OSError as exc:
        log.warning("[DATAPACK] Failed to sync datapack to '%s': %s", instance_dir, exc)
        return None


def wait_for_datapack(
    source_dir: Path,
    timeout: float = _DATAPACK_WAIT_TIMEOUT,
    poll: float = _DATAPACK_WAIT_POLL,
) -> bool:
    """Wait until the datapack in *source_dir* is complete.

    ``generate_datapack`` deletes and rebuilds the datapack folder and writes
    the ZIP archive last (``shutil.make_archive``), so a ZIP that is not older
    than every file in the folder is a reliable completeness marker. Returns
    ``True`` when the datapack is ready.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_datapack_complete(source_dir):
            return True
        time.sleep(poll)
    return _is_datapack_complete(source_dir)


def _is_datapack_complete(source_dir: Path) -> bool:
    zip_path = source_dir / f"{DATAPACK_NAME}.zip"
    folder = source_dir / DATAPACK_NAME
    if not zip_path.exists() or not folder.exists():
        return False

    newest_file = 0.0
    for entry in folder.rglob("*"):
        if entry.is_file():
            newest_file = max(newest_file, entry.stat().st_mtime)
    return zip_path.stat().st_mtime >= newest_file
