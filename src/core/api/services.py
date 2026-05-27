from pathlib import Path
import json
import yaml
import shutil
import logging
from datetime import datetime
from typing import Any

from core.paths import get_root_dir, get_config_file

log = logging.getLogger(__name__)


class ApiService:
    """Central business logic layer for the API server.

    Encapsulates all filesystem operations (config read/write, plugin
    registry access) so route handlers stay thin.  This is a stateless
    singleton — safe to share across requests as long as file operations
    are not interleaved (the GUI calls them sequentially).
    """

    def __init__(self) -> None:
        self.root_dir: Path = get_root_dir()
        self.config_path: Path = get_config_file()
        self.registry_path: Path = (
            self.root_dir / "plugins" / "PLUGIN_REGISTRY.json"
        )
        self._start_time: datetime = datetime.now()

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    def get_uptime(self) -> float:
        return (datetime.now() - self._start_time).total_seconds()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def read_config(self) -> dict[str, Any]:
        """Load the YAML config file and return it as a dict."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}"
            )
        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def write_config(
        self, data: dict[str, Any], backup: bool = True
    ) -> None:
        """Write a config dict back to the YAML file atomically.

        If *backup* is ``True`` the previous file is copied to
        ``config.yaml.bak`` first.
        """
        if backup and self.config_path.exists():
            bak_path = self.config_path.with_suffix(".yaml.bak")
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

    # ------------------------------------------------------------------
    # Plugin registry
    # ------------------------------------------------------------------

    def read_plugin_registry(self) -> list[dict[str, Any]]:
        """Return the list of registered plugins from the JSON registry."""
        if not self.registry_path.exists():
            return []
        with self.registry_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
