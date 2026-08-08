#!/usr/bin/env python3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppConfig:
    name: str
    path: Path
    enable: bool
    level: int
    ics: bool
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
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
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            enable=data["enable"],
            level=data["level"],
            ics=data["ics"],
            depends_on=data.get("depends_on", []),
        )
