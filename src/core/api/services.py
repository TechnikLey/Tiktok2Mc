from pathlib import Path
import yaml
import shutil
import logging
from datetime import datetime
from typing import Any

from core.paths import get_root_dir, get_config_file

log = logging.getLogger(__name__)


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


