"""Registry for built-in script actions ($-commands provided by the tool)."""

from __future__ import annotations

from typing import Any, Callable

from core.builtin_random import register_random_action

# name -> dict with metadata + config accessor hooks
_REGISTRY: dict[str, dict[str, Any]] = {}


def _random_schema() -> dict[str, Any]:
    return {
        "version": 1,
        "fields": [
            {
                "key": "mode",
                "type": "select",
                "default": "deny-all",
                "label": "Filter Mode",
                "help": "deny-all: triggers in the list are excluded. allow-only: only listed triggers are eligible.",
                "category": "General",
                "options": ["deny-all", "allow-only"],
            },
            {
                "key": "triggers",
                "type": "array",
                "default": [],
                "label": "Triggers",
                "help": "List of trigger names to deny or allow (depending on mode).",
                "category": "General",
                "item_schema": {"type": "string"},
            },
        ],
    }


def _random_description() -> str:
    return "Picks a random eligible trigger and executes it when a $random action is triggered."


def register_all(api, config: dict | None = None) -> None:
    """Register every built-in action handler."""
    register_random_action(api, config)


def list_builtins() -> list[dict[str, Any]]:
    return [
        {
            "name": "random",
            "display_name": "Random Trigger",
            "description": _random_description(),
            "config_schema": _random_schema(),
        }
    ]


def get_config(config: dict | None, name: str) -> dict[str, Any]:
    if not isinstance(config, dict):
        config = {}
    builtins = config.get("builtins", {})
    if not isinstance(builtins, dict):
        builtins = {}
    cfg = builtins.get(name, {})
    return cfg if isinstance(cfg, dict) else {}


def set_config(config: dict, name: str, values: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        return
    builtins = config.setdefault("builtins", {})
    if not isinstance(builtins, dict):
        config["builtins"] = {}
        builtins = config["builtins"]
    builtins[name] = values
