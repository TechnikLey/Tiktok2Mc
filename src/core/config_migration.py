"""User config migration to the current template (P3a §7).

Historically this logic lived inside the updater binary; with the P3a
pointer architecture the updater no longer touches user data — the
**launcher** runs the migration as a first-start hook (see
``src/python/start.py``), after the install layout is migrated and the
active app directory is resolved.

Key properties (unchanged from the original implementation):

- Comments, quoting and indentation of the user config are preserved
  (``ruamel`` round-trip mode).
- Only keys **present in the template** are migrated (_inject_values_strictly);
  unknown user keys are dropped.
- ``None``/empty user values keep their template defaults.
- A backup is created through the centralized :class:`~core.backup.BackupManager`
  before anything is written.
"""

from __future__ import annotations

from logging import Logger, getLogger
from pathlib import Path

from packaging import version
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

from core.backup import get_backup_manager
from core.utils import normalize_config_version

log: Logger = getLogger(__name__)


def load_yaml_with_debug(path: Path, yaml_obj: YAML, label: str):
    """Load a YAML file, logging a precise error on malformed input."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml_obj.load(f)
            if data is None:
                return CommentedMap()
            return data
    except YAMLError as e:
        log.error("[FAIL] YAML error in %s: %s", label, path)

        if hasattr(e, "problem_mark") and e.problem_mark is not None:
            mark = e.problem_mark
            log.error("[FAIL] Line: %s, Column: %s", mark.line + 1, mark.column + 1)

        log.error("[FAIL] Details: %s", e)
        return None
    except Exception as e:  # noqa: BLE001 - boundary: any YAML/parsing failure must log only
        log.error("[FAIL] Unexpected error while loading %s: %s", label, path)
        log.error("[FAIL] Details: %s", e)
        return None


def _inject_values_strictly(template, user_source, path="") -> None:
    """Recursively copy user values into the template where keys match."""
    # 1. BASE GUARD: If user_source is None or not a dictionary-like object
    if user_source is None:
        if path:
            log.warning(
                f"Configuration path '{path}' is empty in user config. Skipping."
            )
        return
    if not isinstance(user_source, (dict, CommentedMap)):
        if path:
            log.warning(
                f"Expected a section at '{path}', but found "
                f"{type(user_source).__name__}. Skipping."
            )
        return
    # 2. ITERATE: Only keys that exist in the template are migrated.
    for key in template:
        current_path = f"{path}.{key}" if path else key
        if key in user_source:
            user_value = user_source[key]
            template_value = template[key]
            # CASE A: Both are nested structures -> Recurse
            if isinstance(template_value, (dict, CommentedMap)):
                if isinstance(user_value, (dict, CommentedMap)):
                    _inject_values_strictly(template_value, user_value, current_path)
                elif user_value is None:
                    # User left a whole category empty (e.g., 'Java: ')
                    log.warning(
                        f"Section '{current_path}' is empty in user config. "
                        "Keeping defaults."
                    )
                else:
                    log.warning(
                        f"Type mismatch at '{current_path}': Expected a section, "
                        "got a value. Skipping."
                    )
            # CASE B: Template expects a simple value (String, Int, Bool, List)
            else:
                if user_value is not None:
                    template[key] = user_value
                    log.debug("Migrated: %s", current_path)
                else:
                    log.debug(
                        f"Value for '{current_path}' is null/empty. Using default."
                    )
        else:
            log.debug("Key '%s' missing in user config. Using default.", current_path)


def migrate_config(
    config_file: Path,
    default_config_file: Path,
    *,
    yaml_obj: YAML | None = None,
) -> bool:
    """Merge *default_config_file* template values into *config_file*.

    Returns ``True`` when the config was (re)written. Idempotent: a config
    already at the template's ``config_version`` is left untouched.
    """
    if yaml_obj is None:
        yaml_obj = YAML(typ="rt")
        yaml_obj.preserve_quotes = True
        yaml_obj.indent(mapping=2, sequence=4, offset=2)
        yaml_obj.width = 120

    if not default_config_file.exists():
        log.error("Master template missing: %s", default_config_file)
        return False

    # Case 1: No user config exists
    if not config_file.exists():
        try:
            template_bytes = default_config_file.read_bytes()
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_bytes(template_bytes)
            log.info("No config found. Created new config from template.")
            return True
        except OSError as e:
            log.error("Failed to copy template: %s", e)
            return False

    # Load Template
    template_data = load_yaml_with_debug(default_config_file, yaml_obj, "Template")
    if template_data is None:
        return False

    template_data.yaml_set_start_comment("DO NOT EDIT the config_version")

    # Load User Config
    user_data = load_yaml_with_debug(config_file, yaml_obj, "User Config")
    if user_data is None:
        return False

    # Version Check (supports "1.0", "0.7", legacy int 7, "v1.0.0")
    try:
        raw_default_val = template_data.get("config_version", "0.0")
        raw_user_val = user_data.get("config_version", "0.0")
        raw_default = normalize_config_version(raw_default_val)
        raw_user = normalize_config_version(raw_user_val)
        default_ver = version.parse(raw_default)
        user_ver = version.parse(raw_user)
    except (ValueError, TypeError) as e:
        log.warning("Version keys are invalid (%s). Forcing migration...", e)
        default_ver, user_ver = version.parse("1.0"), version.parse("0.0")
        raw_default, raw_user = "1.0", "0.0"

    if user_ver >= default_ver:
        log.info("Config is up to date (%s).", raw_user)
        return False

    log.info("Migrating config: %s -> %s", raw_user, raw_default)

    # Backup (via centralized BackupManager)
    try:
        bm = get_backup_manager()
        if bm is None:
            log.warning("No backup manager available; skipping config backup")
        else:
            bak = bm.create_backup(config_file, category="migration")
            if bak:
                log.info("Backup created at: %s", bak)
            else:
                log.info("Backup skipped (identical content or too recent)")
    except OSError as e:
        log.error("Migration aborted. Could not create backup: %s", e)
        return False

    # Perform strict injection
    _inject_values_strictly(template_data, user_data)

    # Force the new version number
    template_data["config_version"] = raw_default

    try:
        with config_file.open("w", encoding="utf-8") as f:
            yaml_obj.dump(template_data, f)
        log.info("[SUCCESS] Config migrated successfully to %s.", raw_default)
        return True
    except (OSError, YAMLError) as e:
        log.error("[FAIL] Error writing migrated config: %s", e)
        return False
