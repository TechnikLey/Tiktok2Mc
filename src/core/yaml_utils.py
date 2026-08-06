from __future__ import annotations

import logging
from pathlib import Path
from time import time
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from core.backup import get_backup_manager

log = logging.getLogger(__name__)


def create_yaml_rt() -> YAML:
    """Create a ruamel.yaml round-trip parser with project conventions."""
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 120
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def load_yaml(path: Path) -> Any:
    """Load a YAML file with round-trip preservation (comments, ordering, formatting).

    Returns a ``CommentedMap`` / ``CommentedSeq`` for mapping / sequence documents.
    An empty file returns an empty ``CommentedMap``.

    Raises ``ValueError`` if the file contains obviously malformed YAML
    (e.g. mapping keys that are ``None``).
    """
    yaml = create_yaml_rt()
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.load(f)
    if data is None:
        return CommentedMap()
    # Reject obviously malformed mappings (e.g. from corrupt YAML like ": broken yaml [")
    if isinstance(data, CommentedMap) and None in data:
        raise ValueError(f"YAML file {path} appears malformed")
    return data


def save_yaml(path: Path, data: Any, backup: bool = False) -> None:
    """Write *data* to *path* atomically, preserving ruamel.yaml metadata.

    Delegates backup creation to the centralized ``BackupManager`` when
    *backup* is ``True`` and the file already exists.
    """
    yaml = create_yaml_rt()
    if backup and path.exists():
        bm = get_backup_manager()
        try:
            bm.create_backup(path)
        except Exception as exc:
            log.warning("Failed to create backup for %s: %s", path, exc)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    for attempt in range(5):
        try:
            tmp_path.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1)

def deep_update_rt(base: Any, overlay: Any) -> None:
    """Recursively merge *overlay* into *base* in-place.

    Works on ``CommentedMap`` / ``CommentedSeq`` (and plain dict/list as
    fallbacks).  Existing keys/items not present in *overlay* are left
    untouched so their YAML comments and formatting survive.
    """
    if isinstance(base, CommentedMap) and isinstance(overlay, dict):
        for key, value in overlay.items():
            if (
                key in base
                and isinstance(base[key], (CommentedMap, dict))
                and isinstance(value, dict)
            ):
                deep_update_rt(base[key], value)
            else:
                base[key] = value
    elif isinstance(base, CommentedSeq) and isinstance(overlay, list):
        # Truncate or extend base to match overlay length
        while len(base) > len(overlay):
            del base[-1]
        for i, value in enumerate(overlay):
            if i < len(base):
                if (
                    isinstance(base[i], (CommentedMap, dict))
                    and isinstance(value, dict)
                ):
                    deep_update_rt(base[i], value)
                else:
                    base[i] = value
            else:
                base.append(value)
