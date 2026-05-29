#!/usr/bin/env python3
from pathlib import Path
import sys
import logging
from typing import Any

from core.yaml_utils import load_yaml

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
    ``float 1.0``  ``"1.0"``
    ``"7"``         ``"0.7"``
    ``"0.7"``       ``"0.7"``
    ``"v1.0.0"``    ``"1.0"``
    ``"1.0"``       ``"1.0"``
    ``"1.0.0"``     ``"1.0"``
    ============== ===========
    """
    if isinstance(value, int):
        return f"0.{value}"

    if isinstance(value, float):
        # YAML parses "1.0" as float 1.0 — convert back to string safely
        s = str(value)
        if "." not in s:
            s += ".0"
        parts = s.split(".")
        if parts[0].isdigit() and (len(parts) < 2 or parts[1].isdigit()):
            return f"{int(parts[0])}.{int(parts[1]) if len(parts) > 1 else 0}"
        raise ValueError(f"Unrecognised config version float: {value!r}")

    if isinstance(value, str):
        s = value.strip().lstrip("v")
        parts = s.split(".")
        n = len(parts)
        if n >= 2 and parts[0].isdigit() and parts[1].isdigit():
            major = int(parts[0])
            minor = int(parts[1])
            return f"{major}.{minor}"
        if n == 1 and parts[0].isdigit():
            return f"0.{parts[0]}"
        raise ValueError(
            f"Unrecognised config version string: {value!r}"
        )

    raise ValueError(
        f"config_version must be int, float or str, "
        f"got {type(value).__name__}: {value!r}"
    )


# ── Generic config loader ────────────────────────────────────────────


def load_config(config: str | Path) -> dict:
    path = Path(config)
    try:
        return load_yaml(path)
    except FileNotFoundError:
        raise
    except ValueError as e:
        raise ValueError(f"YAML error in {path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error loading {path}: {e}")