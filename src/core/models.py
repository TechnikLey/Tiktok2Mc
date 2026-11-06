#!/usr/bin/env python3
"""Shared dataclasses for supervisor configuration (``AppConfig``)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppConfig:
    """Description of one supervised application process.

``level`` controls start order and ``depends_on`` lists app names that must be
started first; ``ics`` is the process-creation flag used by the supervisor."""

    name: str
    path: Path
    enable: bool
    level: int
    ics: bool
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Coerce ``path`` to ``Path`` and validate field types and values."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("App name must be a non-empty string.")

        if not isinstance(self.path, Path):
            self.path = Path(self.path)

        if not isinstance(self.enable, bool):
            raise TypeError("enable must be a bool.")
        if not isinstance(self.level, int) or self.level < 0:
            raise ValueError("level must be a non-negative int.")
        if not isinstance(self.ics, bool):
            raise TypeError("ics must be a bool.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary representation."""
        return {
            "name": self.name,
            "path": str(self.path),
            "enable": self.enable,
            "level": self.level,
            "ics": self.ics,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """Build an instance from a dictionary produced by :meth:`to_dict`.

Raises:
    KeyError: If a required key is missing.
    TypeError: If ``path`` cannot be converted to ``Path``."""

        return cls(
            name=data["name"],
            path=Path(data["path"]),
            enable=data["enable"],
            level=data["level"],
            ics=data["ics"],
            depends_on=data.get("depends_on", []),
        )
