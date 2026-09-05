"""PaperMC server.jar download and copy helpers.

Shared by the API routes (``servers.py`` / ``server_lifecycle.py``) and the
Minecraft launcher (``server.py``) so the required server version is always
present exactly where it is needed:

- ``versions/<version>/server.jar`` — the version template library
- ``server/<instance_id>/server.jar`` — each server instance

The GUI-facing ``POST /servers/download`` route keeps its own detailed
download implementation (retries, API-shaped errors); these helpers are the
minimal building blocks that let *any* start/download path obtain a jar
without duplicating the PaperMC API logic, and they are what enables the
"download the missing version automatically and place it in the instance
folder" behavior.
"""

import json
import logging
import shutil
import urllib.request
from pathlib import Path

from core.paths import get_servers_dir, get_versions_dir

log = logging.getLogger(__name__)

PAPER_API = "https://fill.papermc.io/v3/projects/paper"

_MIN_SUPPORTED_MAJOR = 1
_MIN_SUPPORTED_MINOR = 13


class ServerJarError(RuntimeError):
    """Raised when a server.jar cannot be obtained (download/copy/network)."""


def is_supported_version(version: str) -> bool:
    """Whether *version* is accepted by the PaperMC auto-download (stable, >=1.13)."""
    if "-" in version:
        return False
    parts = version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return False
    return major > _MIN_SUPPORTED_MAJOR or (
        major == _MIN_SUPPORTED_MAJOR and minor >= _MIN_SUPPORTED_MINOR
    )


def _fetch_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "TikTok2Mc/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_download_url(version: str) -> str:
    """Return the best stable build's download URL for *version*.

    Prefers the most recent STABLE build, falling back to BETA/ALPHA. Raises
    :class:`ServerJarError` when the version is not supported or PaperMC has
    no downloadable build.
    """
    if not is_supported_version(version):
        raise ServerJarError(
            f"Version '{version}' is not supported (minimum supported is "
            f"{_MIN_SUPPORTED_MAJOR}.{_MIN_SUPPORTED_MINOR})."
        )
    builds = _fetch_json(f"{PAPER_API}/versions/{version}/builds")
    if not isinstance(builds, list) or not builds:
        raise ServerJarError(f"No builds found for version '{version}'")

    _channel_priority = {"STABLE": 0, "BETA": 1, "ALPHA": 2}
    candidates = [
        b
        for b in builds
        if b.get("channel") in _channel_priority
        and b.get("downloads", {}).get("server:default")
    ]
    if not candidates:
        raise ServerJarError(f"No successful builds found for version '{version}'")

    candidates.sort(
        key=lambda b: (_channel_priority.get(b.get("channel"), 99), -b.get("id", 0))
    )
    latest = candidates[0]
    try:
        build_num = latest["id"]
        download_obj = latest["downloads"]["server:default"]
        url = download_obj["url"]
    except (KeyError, TypeError) as exc:
        raise ServerJarError(
            f"Unexpected PaperMC API format for version '{version}': {exc}"
        ) from exc
    if not url:
        raise ServerJarError(
            f"PaperMC returned no download URL for version '{version}' build {build_num}"
        )
    return url


def ensure_version_jar(version: str) -> Path:
    """Ensure ``versions/<version>/server.jar`` exists, downloading it if needed.

    Returns the path to the jar. Raises :class:`ServerJarError` when the
    download fails (after up to 3 attempts).
    """
    target = get_versions_dir() / version / "server.jar"
    if target.exists() and target.stat().st_size > 0:
        return target

    url = resolve_download_url(version)
    target.parent.mkdir(parents=True, exist_ok=True)

    last_error: Exception | None = None
    for attempt in range(3):
        part = target.with_suffix(".part")
        try:
            log.info(
                "Downloading PaperMC %s -> %s (attempt %d/3)",
                version,
                target,
                attempt + 1,
            )
            req = urllib.request.Request(url, headers={"User-Agent": "TikTok2Mc/1.0"})
            with (
                urllib.request.urlopen(req, timeout=120) as resp,
                part.open("wb") as out,
            ):
                shutil.copyfileobj(resp, out, length=1024 * 256)
            if part.stat().st_size == 0:
                part.unlink(missing_ok=True)
                raise ServerJarError("Downloaded file is empty")
            part.replace(target)
            log.info(
                "Downloaded server.jar for version %s (%s bytes)",
                version,
                target.stat().st_size,
            )
            return target
        except (OSError, ValueError) as exc:
            last_error = exc
            log.warning(
                "Download attempt %d/3 failed for %s: %s", attempt + 1, version, exc
            )
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
    raise ServerJarError(f"Could not download PaperMC {version}: {last_error}")


def ensure_instance_jar(instance_id: str, version: str) -> Path:
    """Ensure ``server/<instance_id>/server.jar`` exists for *version*.

    Copies the version jar from the template library (downloading it first
    when missing) and places it in the instance directory. Returns the
    instance jar path. Raises :class:`ServerJarError` on failure.
    """
    instance_dir = get_servers_dir() / instance_id
    target = instance_dir / "server.jar"
    if target.exists() and target.stat().st_size > 0:
        return target

    version_jar = ensure_version_jar(version)
    instance_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(version_jar, target)
    log.info("Copied server.jar (%s) into instance '%s'", version, instance_id)
    return target


def copy_version_jar_to_instances(version: str) -> int:
    """Copy ``versions/<version>/server.jar`` into every instance that is
    missing it (but expects that version). Returns the number of copies made.

    Used right after a version download so instances pick the jar up
    automatically instead of requiring a manual move.
    """
    version_jar = get_versions_dir() / version / "server.jar"
    if not version_jar.exists():
        return 0
    copied = 0
    servers_dir = get_servers_dir()
    if not servers_dir.is_dir():
        return 0
    for instance_dir in servers_dir.iterdir():
        if not instance_dir.is_dir():
            continue
        target = instance_dir / "server.jar"
        if target.exists() and target.stat().st_size > 0:
            continue
        try:
            shutil.copy2(version_jar, target)
            log.info(
                "Copied server.jar (%s) into instance '%s'", version, instance_dir.name
            )
            copied += 1
        except OSError as exc:
            log.warning(
                "Failed to copy server.jar into instance '%s': %s",
                instance_dir.name,
                exc,
            )
    return copied
