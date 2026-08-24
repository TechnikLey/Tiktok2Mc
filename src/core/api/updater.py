"""Plugin update checking and installation.

Checks each registered plugin's ``update_url`` for newer versions,
downloads and installs updates, and reports status.

Supports GitHub Releases API (``https://api.github.com/repos/...``)
and direct download URLs with a ``version`` query parameter.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from packaging import version as version_parse

from core.checksum import (
    fetch_checksum,
    find_checksum_asset_url,
    verify_checksum,
)

log = logging.getLogger(__name__)

_TIMEOUT = 10
_USER_AGENT = "Tiktok2Mc-Updater/1.0"


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract *zip_path* into *dest*, rejecting path traversal members.

    Zip slip protection, mirrors src/python/update.py — a crafted archive
    must never be able to write outside the extraction directory.
    """
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zf:
        dest_resolved = str(dest.resolve())
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(dest_resolved):
                raise ValueError(f"Zip slip attempt: {member.filename}")
        zf.extractall(dest)


def _extract_version(text: str) -> str:
    """Extract the first semver-like version from a string."""
    if not text:
        return ""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)", str(text))
    return m.group(1) if m else ""


def _parse_remote_version(url: str) -> str | None:
    """Fetch a URL and extract the remote version string.

    Supports:
    - GitHub Releases API (``api.github.com/repos/``) — reads ``tag_name``
    - Direct JSON with ``version`` key
    - Plain-text version string
    """
    headers = {"User-Agent": _USER_AGENT}
    if "api.github.com" in url:
        headers["Accept"] = "application/vnd.github+json"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode("utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        log.debug("Failed to fetch %s: %s", url, exc)
        return None

    # Try JSON
    if body.startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            pass
        else:
            # GitHub Releases API
            tag = data.get("tag_name")
            if tag:
                return _extract_version(tag)
            # Generic JSON with version field
            ver = data.get("version")
            if ver:
                return _extract_version(str(ver))
            # tag without v prefix
            tag = data.get("tag")
            if tag:
                return _extract_version(str(tag))

    # Plain text — try to extract a version
    extracted = _extract_version(body)
    if extracted:
        return extracted

    return None


def _download_update(url: str, target: Path) -> bool:
    """Download a file from ``url`` to ``target``.

    Returns ``True`` on success.
    """
    headers = {"User-Agent": _USER_AGENT}
    if "api.github.com" in url:
        headers["Accept"] = "application/octet-stream"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT * 3) as resp:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
        return True
    except OSError as exc:
        log.error("Download failed from %s: %s", url, exc)
        return False


# ── Tool update check ─────────────────────────────────────────────────

_GITHUB_REPO = "TechnikLey/Tiktok2Mc"
_TOOL_API_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"


def check_tool_update(current_version: str) -> dict[str, Any]:
    """Check the main GitHub repo for a newer tool release.

    ``current_version`` is the local tool version, either a plain semver
    string like ``"1.0.0"`` or with a leading ``v`` (``"v1.0.0"``, matching
    ``core.version.TOOL_VERSION``).  GitHub tags (``v1.0.0``) are stripped
    of the leading ``v`` before comparison.

    Returns a dict with keys matching ``ToolUpdateCheckResponse``.
    """
    current = current_version.lstrip("v")

    result: dict[str, Any] = {
        "current_version": current,
        "latest_version": None,
        "update_available": False,
        "release_url": "",
        "published_at": "",
        "error": None,
    }

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    req = urllib.request.Request(_TOOL_API_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            release = json.loads(resp.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
        return result

    tag_name = release.get("tag_name", "")
    latest = _extract_version(tag_name)
    if not latest:
        result["error"] = "Could not extract version from release tag"
        return result

    result["latest_version"] = latest
    result["release_url"] = release.get("html_url", "")
    result["published_at"] = release.get("published_at", "")

    try:
        result["update_available"] = version_parse.parse(latest) > version_parse.parse(
            current_version
        )
    except version_parse.InvalidVersion as exc:
        result["error"] = f"Version comparison failed: {exc}"

    return result


# ── Last tool-update result (in-memory) ──────────────────────────────
# ``start.py`` records how the updater process exited here before the
# API is reachable; the GUI reads it afterwards via ``/updates/result``.


_last_update_result: dict[str, Any] | None = None


def set_last_update_result(
    exit_code: int | None,
    *,
    ok: bool,
    message: str | None = None,
    source: str = "startup",
) -> None:
    """Record the outcome of the most recent tool-update run."""
    global _last_update_result
    _last_update_result = {
        "exit_code": exit_code,
        "ok": ok,
        "message": message,
        "source": source,
        "timestamp": time.time(),
    }


def get_last_update_result() -> dict[str, Any] | None:
    """Return the last recorded tool-update result, or ``None``."""
    return _last_update_result


class PackageUpdateChecker:
    """Check and report package update status for plugins and hooks.

    The checker reads registered packages from a registry, queries each
    package's ``update_url``, and compares versions.  The same class
    serves plugins and hooks — both are plain directories with a
    manifest and an ``update_url``.
    """

    def __init__(self) -> None:
        self._last_check: dict[str, dict[str, Any]] = {}

    def check_updates(self, plugins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Check all plugins that have an ``update_url``.

        ``plugins`` should be a list of ``PluginRegistration`` dicts
        (e.g. from ``registry.list()``).

        Returns a list of dicts suitable for ``PluginUpdateStatus``.
        """
        results: list[dict[str, Any]] = []
        now = time.time()

        for plugin in plugins:
            name = plugin.get("name", "")
            display_name = plugin.get("display_name", name)
            current_version = plugin.get("version", "0.0.0")
            update_url = plugin.get("update_url", "")

            if not update_url:
                continue

            latest_version = _parse_remote_version(update_url)
            update_available = False
            error = None

            if latest_version is None:
                error = "Could not fetch remote version"
            else:
                try:
                    update_available = version_parse.parse(
                        latest_version
                    ) > version_parse.parse(current_version)
                except version_parse.InvalidVersion as exc:
                    error = f"Version comparison failed: {exc}"

            status = {
                "name": name,
                "display_name": display_name,
                "current_version": current_version,
                "latest_version": latest_version,
                "update_available": update_available,
                "update_url": update_url,
                "checked_at": now,
                "error": error,
            }
            self._last_check[name] = dict(status)
            results.append(status)

        return results

    def get_cached_status(self, name: str) -> dict[str, Any] | None:
        """Return the last check result for a package, or ``None``."""
        return self._last_check.get(name)

    def install_update(
        self,
        pkg: dict[str, Any],
        base_dir: Path,
    ) -> bool:
        """Download and install a package (plugin or hook) update.

        Fetches ``update_url``, resolves the download asset, and
        extracts/replaces the package directory under *base_dir*.

        The user's ``config.yaml`` inside the package directory is
        preserved across the update — an archive never overwrites it.
        New/changed schema keys are merged at load time via the
        manifest's ``config_schema`` defaults.

        Returns ``True`` on success.
        """
        name = pkg.get("name", "")
        update_url = pkg.get("update_url", "")

        if not update_url:
            log.warning("No update_url for '%s'", name)
            return False

        # The package lives directly under *base_dir*.
        pkg_dir = base_dir / name

        # Fetch latest release info
        headers = {"User-Agent": _USER_AGENT}
        if "api.github.com" in update_url:
            headers["Accept"] = "application/vnd.github+json"
            try:
                req = urllib.request.Request(update_url, headers=headers)
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    release = json.loads(resp.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                log.error(
                    "Failed to fetch release info for '%s': %s",
                    name,
                    exc,
                )
                return False

            # Find platform-specific asset
            assets = release.get("assets", [])
            target_asset = None
            for asset in assets:
                aname = asset.get("name", "")
                if (
                    "plugin" in aname.lower()
                    and aname.endswith(".zip")
                    and name.lower() in aname.lower()
                ):
                    # Prefer asset that contains the plugin name
                    target_asset = asset
                    break
            if not target_asset and assets:
                # Fallback: first zip asset
                target_asset = next(
                    (a for a in assets if a["name"].endswith(".zip")),
                    None,
                )
            if not target_asset:
                log.error("No downloadable asset found for '%s'", name)
                return False

            download_url = target_asset["url"]
        else:
            download_url = update_url

        # Download to temp directory
        tmp_dir = pkg_dir.parent / f".update_{name}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        archive_path = tmp_dir / f"{name}.zip"
        if not _download_update(download_url, archive_path):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False

        # ── Integrity verification ──────────────────────────────────
        expected_hash = None
        if "api.github.com" in update_url:
            # Try to find a companion .sha256 asset in the release
            checksum_url = find_checksum_asset_url(assets, target_asset["name"])
            if checksum_url:
                try:
                    req = urllib.request.Request(
                        checksum_url,
                        headers={
                            "User-Agent": _USER_AGENT,
                            "Accept": "application/octet-stream",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                        body = resp.read().decode("utf-8").strip()
                        for line in body.splitlines():
                            parts = line.strip().split()
                            if parts:
                                candidate = parts[0].lower()
                                if len(candidate) == 64 and all(
                                    c in "0123456789abcdef" for c in candidate
                                ):
                                    expected_hash = candidate
                                    break
                except (OSError, UnicodeDecodeError) as exc:
                    log.debug("Could not fetch checksum asset for '%s': %s", name, exc)
        else:
            expected_hash = fetch_checksum(download_url)

        if not expected_hash:
            log.error(
                "Aborting update for '%s' — the update source provides no "
                "checksum; refusing to install an unverified archive",
                name,
            )
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False
        if not verify_checksum(archive_path, expected_hash):
            log.error("Aborting update for '%s' — checksum verification failed", name)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False
        # ─────────────────────────────────────────────────────────────

        # Extract into a dedicated subdirectory so the archive itself
        # never mixes with the extracted content.
        import zipfile

        extract_dir = tmp_dir / "extracted"
        try:
            _safe_extract_zip(archive_path, extract_dir)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            log.error("Extraction failed for '%s': %s", name, exc)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False

        # Replace package directory
        backup_dir = pkg_dir.parent / f".bak_{name}"
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        # Preserve the user's config.yaml — an update archive must never
        # overwrite it (mirrors the tool updater, which skips user config).
        preserved_config: bytes | None = None
        config_file = pkg_dir / "config.yaml"
        if config_file.is_file():
            try:
                preserved_config = config_file.read_bytes()
            except OSError as exc:
                log.warning("Could not read current config.yaml of '%s': %s", name, exc)

        try:
            if pkg_dir.exists():
                pkg_dir.rename(backup_dir)
            # Recreate the destination directory — the rename above
            # removed it, and ``shutil.move`` needs its target parent.
            pkg_dir.mkdir(parents=True, exist_ok=True)
            # Move extracted content to the package directory
            extracted_items = list(extract_dir.iterdir())
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                # Single root folder — move contents
                src = extracted_items[0]
                for item in src.iterdir():
                    shutil.move(str(item), str(pkg_dir / item.name))
            else:
                for item in extracted_items:
                    shutil.move(str(item), str(pkg_dir / item.name))

            # Restore the preserved user config over whatever the
            # archive shipped.
            if preserved_config is not None:
                try:
                    (pkg_dir / "config.yaml").write_bytes(preserved_config)
                except OSError as exc:
                    log.warning("Could not restore config.yaml for '%s': %s", name, exc)

            # Cleanup
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)

            log.info("Updated '%s' successfully", name)
            # Update manifest version
            manifest_file = next(
                (
                    pkg_dir / fname
                    for fname in ("plugin.json", "hook.json")
                    if (pkg_dir / fname).is_file()
                ),
                None,
            )
            if manifest_file is not None:
                try:
                    with manifest_file.open("r", encoding="utf-8") as fh:
                        manifest = json.load(fh)
                    latest_version = pkg.get("latest_version", "")
                    if latest_version:
                        manifest["version"] = latest_version
                        with manifest_file.open("w", encoding="utf-8") as fh:
                            json.dump(manifest, fh, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, OSError, TypeError) as exc:
                    log.warning(
                        "Could not update version in manifest: %s",
                        exc,
                    )

            return True

        except OSError as exc:
            log.error("Failed to install update for '%s': %s", name, exc)
            # Restore backup
            if backup_dir.exists():
                if pkg_dir.exists():
                    shutil.rmtree(pkg_dir, ignore_errors=True)
                backup_dir.rename(pkg_dir)
            # Cleanup temp
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            return False


# Backward-compatible alias — the checker serves plugins and hooks alike.
PluginUpdateChecker = PackageUpdateChecker
