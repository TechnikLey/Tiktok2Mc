import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

import core.paths
from core.config_lock import config_transaction
from core.utils import normalize_config_version
from core.validation_framework import validate_config_schema
from core.version import EXPECTED_CONFIG_VERSION
from core.yaml_utils import deep_update_rt, load_yaml

log = logging.getLogger(__name__)


class ApiService:
    """Central business logic for the API server.

    Handles config read/write and uptime tracking.  Plugin registry
    access is now delegated entirely to ``PluginRegistry``.
    """

    def __init__(self) -> None:
        self._start_time: datetime = datetime.now(tz=UTC)

        # Config path with fallback:
        # 1. Standard location (used in builds):   root/config/config.yaml
        # 2. Fallback (dev mode):                   root/defaults/config.yaml
        self.config_path: Path = core.paths.get_config_file()
        if not self.config_path.exists():
            fallback = core.paths.get_root_dir() / "defaults" / "config.yaml"
            if fallback.exists():
                self.config_path = fallback

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    def get_uptime(self) -> float:
        return (datetime.now(tz=UTC) - self._start_time).total_seconds()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def read_config(self) -> dict[str, Any]:
        """Load the YAML config file and normalise its version."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        data = load_yaml(self.config_path)

        # Normalise legacy integer / string config_version on load
        if "config_version" in data:
            try:
                data["config_version"] = normalize_config_version(
                    data["config_version"]
                )
            except ValueError:
                log.warning(
                    "Unrecognised config_version %r — treating as legacy",
                    data["config_version"],
                )
                data["config_version"] = "0.0"

        return data

    def write_config(
        self,
        data: dict[str, Any],
        backup: bool = True,
        replace_keys: list[str] | None = None,
    ) -> None:
        """Validate and write a config dict back to the YAML file atomically.

        Uses a cross-process file lock to prevent concurrent writes from
        corrupting the config.  The entire read-modify-write cycle runs
        inside the lock so that no changes are lost between reading the
        existing file and writing the merged result.

        The ``config_version`` is normalised and upgraded to the current
        baseline (*e.g.* legacy ``"0.7"`` → ``"1.0"``).

        If *backup* is ``True`` the previous file is copied to a versioned
        backup (``config.yaml.v1.bak``, ``config.yaml.v2.bak``, …).

        *replace_keys* allows callers to specify top-level keys whose nested
        dicts should be fully replaced rather than merged.  This ensures
        deleted sub-keys are removed on disk (``deep_update_rt`` preserves
        old keys by default to keep YAML comments).
        """
        data["config_version"] = EXPECTED_CONFIG_VERSION

        with config_transaction(self.config_path, backup=backup) as existing:
            if not isinstance(existing, CommentedMap):
                existing = (
                    CommentedMap(existing)
                    if isinstance(existing, dict)
                    else CommentedMap()
                )

            # For keys marked as replace, remove nested keys in existing
            # that are not in data.
            if replace_keys:
                for key in replace_keys:
                    if key in data and key in existing:
                        old_val = existing[key]
                        new_val = data[key]
                        if isinstance(old_val, (CommentedMap, dict)) and isinstance(
                            new_val, dict
                        ):
                            for old_nested_key in list(old_val.keys()):
                                if old_nested_key not in new_val:
                                    del old_val[old_nested_key]

            deep_update_rt(existing, data)
            validate_config_schema(existing)

        log.info("Config written: %s", self.config_path)

    def get_config_status(self) -> bool:
        return self.config_path.exists()
