"""Plugin manifest discovery — pure filesystem scan.

Reads ``plugin.json`` files from the plugins directory and returns
structured metadata without interacting with the registry or loading
any plugin code.
"""

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def discover_plugins_from_manifests(base_path: str) -> list[dict[str, Any]]:
    """Scan *base_path* for ``plugin.json`` files.

    Returns a list of dicts, one per valid manifest, sorted by plugin
    name.  Each dict contains: ``name``, ``version``, ``entry_point``,
    and ``enabled_by_registry`` (always ``False`` — this function does
    **not** query the registry).

    Malformed manifests are logged as warnings and skipped.
    """
    plugins_dir = Path(base_path)
    if not plugins_dir.is_dir():
        log.warning("Plugins directory not found: %s", base_path)
        return []

    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest_file = child / "plugin.json"
        if not manifest_file.is_file():
            continue

        error = ""
        try:
            with manifest_file.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            error = str(exc)

        if error:
            name = child.name
            if name in seen_names:
                continue
            seen_names.add(name)
            results.append(
                {
                    "name": name,
                    "version": "0.0.0",
                    "entry_point": "",
                    "enabled_by_registry": False,
                    "error": error,
                }
            )
            log.warning("Discovered plugin '%s' with broken manifest: %s", name, error)
            continue

        name = raw.get("name", "")
        if not name or not isinstance(name, str):
            log.warning(
                "Skipping manifest %s: missing or invalid 'name'", manifest_file
            )
            continue

        if name in seen_names:
            log.warning(
                "Duplicate plugin name '%s' in %s — skipping", name, manifest_file
            )
            continue
        seen_names.add(name)

        results.append(
            {
                "name": name,
                "version": raw.get("version", "0.0.0"),
                "entry_point": raw.get("entry_point", ""),
                "enabled_by_registry": False,
                "error": "",
            }
        )

    # Sort by name for deterministic output
    results.sort(key=lambda p: p["name"])
    return results


def discover_queries_from_manifests(base_path: str) -> list[dict[str, Any]]:
    """Scan *base_path* manifests and collect declared query names.

    Returns one dict per plugin that declares a non-empty ``queries``
    list in its ``plugin.json``: ``{"name": ..., "queries": [...]}``
    (sorted by name, queries sorted). Plugins without a declaration are
    omitted — their queries would be rejected at call time anyway.
    Malformed manifests are logged and skipped.
    """
    plugins_dir = Path(base_path)
    if not plugins_dir.is_dir():
        log.warning("Plugins directory not found: %s", base_path)
        return []

    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest_file = child / "plugin.json"
        if not manifest_file.is_file():
            continue
        try:
            with manifest_file.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Skipping manifest %s: %s", manifest_file, exc)
            continue

        name = raw.get("name", "")
        if not name or not isinstance(name, str):
            log.warning(
                "Skipping manifest %s: missing or invalid 'name'", manifest_file
            )
            continue
        if name in seen_names:
            log.warning(
                "Duplicate plugin name '%s' in %s — skipping", name, manifest_file
            )
            continue
        seen_names.add(name)

        raw_queries = raw.get("queries")
        if not isinstance(raw_queries, list):
            continue
        queries = sorted({str(q) for q in raw_queries if q})
        if queries:
            results.append({"name": name, "queries": queries})

    results.sort(key=lambda p: p["name"])
    return results
