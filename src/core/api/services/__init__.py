import re
from pathlib import Path
import yaml
import shutil
import logging
from datetime import datetime
from typing import Any

from core.paths import get_root_dir, get_config_file
from core.utils import normalize_config_version

log = logging.getLogger(__name__)

# ── v1.0 schema ──────────────────────────────────────────────────────

EXPECTED_CONFIG_VERSION = "1.0"

_CONFIG_SCHEMA: dict[str, type] = {
    "config_version": str,
    "auto_update_config": bool,
    "show_sudo_warning": bool,
    "server_host": str,
    "control_method": str,
    "shutdown": dict,
    "java": dict,
    "rcon": dict,
    "tiktok": dict,
    "comment_commands": dict,
    "random_triggers": dict,
    "console": dict,
    "minecraft_server_api": dict,
    "gui": dict,
    "update": dict,
}


def _validate_config_schema(data: Any, path: str = "") -> None:
    """Validate *data* against the frozen v1.0 config schema.

    Raises ``ValueError`` on the first violation.
    ``config_version`` must be a recognised semantic version.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a dict, got {type(data).__name__}")

    for key, expected_type in _CONFIG_SCHEMA.items():
        full_key = f"{path}.{key}" if path else key
        if key not in data:
            raise ValueError(f"Missing required key: {full_key!r}")
        value = data[key]
        if not isinstance(value, expected_type):
            raise ValueError(
                f"{full_key!r} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

    # Version must be a recognised semantic version (already normalised)
    raw_ver = data.get("config_version", "")
    try:
        norm_ver = normalize_config_version(raw_ver)
    except ValueError as e:
        raise ValueError(
            f"config_version is not a recognised version format: {e}"
        )

    # Warn when writing a pre-1.0 config (will be upgraded on write)
    major = int(norm_ver.split(".")[0])
    if major < 1:
        log.info(
            "Config version %s is legacy — will be normalised to %s on write",
            norm_ver, EXPECTED_CONFIG_VERSION,
        )

    # Warn about unknown keys (typo protection)
    known = set(_CONFIG_SCHEMA)
    unknown = set(data) - known
    if unknown:
        log.warning("Unknown config keys (possible typo): %s", sorted(unknown))


class ApiService:
    """Central business logic for the API server.

    Handles config read/write and uptime tracking.  Plugin registry
    access is now delegated entirely to ``PluginRegistry``.
    """

    def __init__(self) -> None:
        self._start_time: datetime = datetime.now()

        # Config path with fallback:
        # 1. Standard location (used in builds):   root/config/config.yaml
        # 2. Fallback (dev mode):                   root/defaults/config.yaml
        self.config_path: Path = get_config_file()
        if not self.config_path.exists():
            fallback = get_root_dir() / "defaults" / "config.yaml"
            if fallback.exists():
                self.config_path = fallback

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    def get_uptime(self) -> float:
        return (datetime.now() - self._start_time).total_seconds()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def read_config(self) -> dict[str, Any]:
        """Load the YAML config file and normalise its version."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}"
            )
        with self.config_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

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
        self, data: dict[str, Any], backup: bool = True
    ) -> None:
        """Validate and write a config dict back to the YAML file atomically.

        The ``config_version`` is normalised and upgraded to the current
        baseline (*e.g.* legacy ``"0.7"`` → ``"1.0"``).

        If *backup* is ``True`` the previous file is copied to a versioned
        backup (``config.yaml.v1.bak``, ``config.yaml.v2.bak``, …).
        """
        # Upgrade to current baseline version before validation
        if "config_version" in data:
            data["config_version"] = EXPECTED_CONFIG_VERSION

        _validate_config_schema(data)

        if backup and self.config_path.exists():
            stem = self.config_path.stem  # "config"
            parent = self.config_path.parent
            bak_num = 0
            for p in parent.glob(f"{stem}.yaml.v*.bak"):
                m = re.search(r"\.v(\d+)\.bak$", p.name)
                if m:
                    bak_num = max(bak_num, int(m.group(1)))
            bak_path = parent / f"{stem}.yaml.v{bak_num + 1}.bak"
            shutil.copy2(self.config_path, bak_path)
            log.info("Config backup created: %s", bak_path)

        tmp_path = self.config_path.with_name(
            self.config_path.name + ".tmp"
        )
        with tmp_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        tmp_path.replace(self.config_path)
        log.info("Config written: %s", self.config_path)

    def get_config_status(self) -> bool:
        return self.config_path.exists()


