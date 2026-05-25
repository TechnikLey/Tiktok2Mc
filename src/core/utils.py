#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml
import logging

log = logging.getLogger(__name__)

def load_config(config: str | Path) -> dict:
    path = Path(config)

    if not path.exists():
        log.info(f"Config file not found: {path}")
        input("Press Enter to exit...")
        sys.exit(1)

    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.info(f"YAML error in {path}: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
    except Exception as e:
        log.info(f"General error in {path}: {e}")
        input("Press Enter to exit...")
        sys.exit(1)