#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml
import logging
from typing import Any

log = logging.getLogger(__name__)


# ── Config version normalisation ─────────────────────────────────────
# Internal format:  "MAJOR.MINOR"  (e.g. "1.0", "0.7")
# Legacy integers  →  "0.<int>"
# Legacy "v1.0.0"  →  "1.0"
# ──────────────────────────────────────────────────────────────────────


def normalize_config_version(value: Any) -> str:
    """Normalise *value* to a ``MAJOR.MINOR`` string.

    ============== ===========
    Input          Output
    ============== ===========
    ``int 7``      ``"0.7"``
    ``"7"``         ``"0.7"``
    ``"0.7"``       ``"0.7"``
    ``"v1.0.0"``    ``"1.0"``
    ``"1.0"``       ``"1.0"``
    ``"1.0.0"``     ``"1.0"``
    ============== ===========
    """
    if isinstance(value, int):
        return f"0.{value}"

    if isinstance(value, str):
        s = value.strip().lstrip("v")
        parts = s.split(".")
        n = len(parts)
        if n >= 2 and parts[0].isdigit() and parts[1].isdigit():
            major = int(parts[0])
            minor = int(parts[1])
            return f"{major}.{minor}"
        raise ValueError(
            f"Unrecognised config version string: {value!r}"
        )

    raise ValueError(
        f"config_version must be int or str, "
        f"got {type(value).__name__}: {value!r}"
    )


# ── Generic config loader ────────────────────────────────────────────


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