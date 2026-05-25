#!/usr/bin/env python3
# ==================================================
# plugin_updater.py - Plugin update checker
# ==================================================
# Scans plugin directories for version.txt files,
# checks update_url for newer versions, and
# downloads/installs updates if available.
# Supports GitHub API URLs and custom HTTP URLs.
# ==================================================

import sys
import shutil
import tempfile
import zipfile
import tarfile
import re
import requests
from pathlib import Path
from packaging import version
from core.paths import get_base_dir
import logging

log = logging.getLogger(__name__)

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"
BASE_DIR = get_base_dir()

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "TikTok2Mc-Plugin-Updater",
}


def parse_version_file(path: Path) -> dict:
    result = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                key, val = map(str.strip, line.split(":", 1))
                result[key.lower()] = val
    return result


def extract_version(text: str) -> str:
    if not text:
        return "0.0.0"
    m = re.search(r"(\d+\.\d+(\.\d+)?(-beta|-alpha)?)", str(text))
    return m.group(1) if m else "0.0.0"


def find_plugin_dirs() -> list[Path]:
    result = []
    for item in BASE_DIR.iterdir():
        if not item.is_dir() or item.name.startswith("."):
            continue
        if (item / f"main{SUFFIX}").exists():
            result.append(item)
    return sorted(result)


def _download_and_extract(plugin_dir: Path, download_url: str) -> bool:
    try:
        resp = requests.get(download_url, stream=True, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Download failed: {e}")
        return False

    is_zip = download_url.lower().endswith(".zip") or "application/zip" in resp.headers.get("Content-Type", "")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        archive_path = tmp_path / ("update.zip" if is_zip else "update.tar.gz")

        with archive_path.open("wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        try:
            if is_zip:
                with zipfile.ZipFile(archive_path, "r") as z:
                    z.extractall(extract_dir)
            else:
                with tarfile.open(archive_path, "r:gz") as t:
                    t.extractall(extract_dir)
        except Exception as e:
            log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Extraction failed: {e}")
            return False

        source_root = extract_dir
        for item in extract_dir.iterdir():
            if item.is_dir() and (item / "version.txt").exists():
                source_root = item
                break

        config_backup = None
        config_file = plugin_dir / "config.yaml"
        if config_file.exists():
            try:
                config_backup = config_file.read_text(encoding="utf-8")
            except Exception as e:
                log.info(f"[PLUGIN-UPDATE] Failed to read config backup: {e}")

        for item in source_root.iterdir():
            name = item.name
            if name.lower() == "config.yaml":
                continue
            dst = plugin_dir / name
            try:
                if item.is_file():
                    shutil.copy2(item, dst)
                elif item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
            except Exception as e:
                log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Failed to copy {name}: {e}")

        if config_backup:
            try:
                config_file.write_text(config_backup, encoding="utf-8")
            except Exception as e:
                log.info(f"[PLUGIN-UPDATE] Failed to restore config: {e}")

    return True


def _check_github(plugin_dir: Path, local_ver: str, update_url: str) -> bool:
    try:
        resp = requests.get(update_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        release = resp.json()
    except Exception as e:
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: GitHub API error: {e}")
        return False

    remote_tag = release.get("tag_name", "")
    remote_ver = extract_version(remote_tag)
    if not remote_ver:
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: No valid version in GitHub release")
        return False

    if version.parse(remote_ver) <= version.parse(local_ver):
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Already up to date ({local_ver})")
        return False

    is_win = sys.platform == "win32"
    assets = release.get("assets", [])
    if is_win:
        asset = next((a for a in assets if "Windows" in a["name"] and a["name"].endswith(".zip")), None)
    else:
        asset = next((a for a in assets if "Linux" in a["name"] and a["name"].endswith(".tar.gz")), None)

    if not asset:
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: No matching asset for this platform")
        return False

    log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: {local_ver} -> {remote_ver}")
    if _download_and_extract(plugin_dir, asset["browser_download_url"]):
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Updated to {remote_ver}")
        return True
    return False


def _check_custom_url(plugin_dir: Path, local_ver: str, update_url: str) -> bool:
    remote_url = update_url.rstrip("/") + "/version.txt"
    try:
        resp = requests.get(remote_url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Could not fetch {remote_url}: {e}")
        return False

    remote_info = {}
    for line in resp.text.splitlines():
        if ":" in line:
            key, val = map(str.strip, line.split(":", 1))
            remote_info[key.lower()] = val

    remote_version_str = remote_info.get("version", "")
    download_url = remote_info.get("download_url", "")

    remote_ver = extract_version(remote_version_str)
    if not remote_ver or not download_url:
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Invalid remote version info")
        return False

    if version.parse(remote_ver) <= version.parse(local_ver):
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Already up to date ({local_ver})")
        return False

    log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: {local_ver} -> {remote_ver}")
    log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Downloading...")

    if _download_and_extract(plugin_dir, download_url):
        log.info(f"[PLUGIN-UPDATE] {plugin_dir.name}: Updated to {remote_ver}")
        return True
    return False


def check_and_update_plugin(plugin_dir: Path) -> bool:
    version_file = plugin_dir / "version.txt"
    info = parse_version_file(version_file)

    local_version_str = info.get("version", "")
    update_url = info.get("update_url", "")

    if not local_version_str or not update_url:
        return False

    local_ver = extract_version(local_version_str)

    if re.match(r"https?://api\.github\.com/repos/.+/.+/releases/latest", update_url):
        return _check_github(plugin_dir, local_ver, update_url)
    else:
        return _check_custom_url(plugin_dir, local_ver, update_url)


def run_plugin_update():
    log.info("[PLUGIN-UPDATE] Checking for plugin updates...")

    plugin_dirs = find_plugin_dirs()
    if not plugin_dirs:
        log.info("[PLUGIN-UPDATE] No plugins found")
        return

    updated = 0
    for plugin_dir in plugin_dirs:
        if check_and_update_plugin(plugin_dir):
            updated += 1

    if updated:
        log.info(f"[PLUGIN-UPDATE] {updated} plugin(s) updated")
    else:
        log.info("[PLUGIN-UPDATE] All plugins are up to date")


if __name__ == "__main__":
    run_plugin_update()
