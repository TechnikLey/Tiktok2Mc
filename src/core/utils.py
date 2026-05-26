#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml
import logging

log = logging.getLogger(__name__)

def load_config(config: str | Path) -> dict:
    path = Path(config)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML error in {path}: {e}")
    except Exception as e:
        raise RuntimeError(f"General error in {path}: {e}")