from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {"name", "path", "enable", "level", "ics"}

@dataclass(slots=True)
class AppConfig:
    name: str
    path: Path
    enable: bool
    level: int
    ics: bool

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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            enable=data["enable"],
            level=data["level"],
            ics=data["ics"],
        )


def validate_config_dict(config: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - set(config.keys())
    if missing:
        raise ValueError(f"Missing required key(s): {', '.join(sorted(missing))}")

    unknown = set(config.keys()) - REQUIRED_KEYS
    if unknown:
        raise ValueError(f"Unknown key(s): {', '.join(sorted(unknown))}")