#!/usr/bin/env python3
# ==================================================
# hook_loader.py - Event Hook script loader
# ==================================================
# Scans event_hooks/*.py and dynamically imports
# each module into the running process. Each module
# must expose a register(api) function that registers
# its handlers via api.register_action().
# ==================================================

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from core.hook_api import HookAPI
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed top-level module names for event hook scripts.
# Any import whose top-level module is NOT in this set will be rejected and
# the hook will be skipped with an [ERROR] message.
# ---------------------------------------------------------------------------
ALLOWED_IMPORTS: frozenset[str] = frozenset({
    # standard library — safe utilities
    "time", "random", "logging",
    # third-party — used by Spotify hook
    "requests",
})

# Modules explicitly allowed for IntelliSense/type-checking only.
ALLOWED_HOOK_MODULES: frozenset[str] = frozenset({"core.hook_api"})

def _check_imports(path: Path) -> list[str]:
    """
    Parse the hook file with the AST and return a list of disallowed
    top-level module names. An empty list means all imports are allowed.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return []

    disallowed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                full_name = alias.name
                if full_name in ALLOWED_HOOK_MODULES:
                    continue
                top = full_name.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    disallowed.append(full_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                full_module = node.module
                if full_module in ALLOWED_HOOK_MODULES:
                    continue
                top = full_module.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    disallowed.append(full_module)
    return disallowed

def load_event_hooks(api: HookAPI, hooks_dir: Path) -> None:
    """
    Scan hooks_dir for *.py files and load each one.

    Each module must define:
        def register(api: HookAPI) -> None: ...

    Files without a register() function are skipped with an error message.
    """
    if not hooks_dir.exists():
        hooks_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"[HOOK] Created event_hooks folder: {hooks_dir}")
        return

    hook_files = sorted(hooks_dir.glob("*.py"))
    if not hook_files:
        log.info("[HOOK] No event hooks found.")
        return

    log.info(f"[HOOK] Loading {len(hook_files)} hook(s) from: {hooks_dir}")

    for path in hook_files:
        _load_single_hook(api, path)

def _load_single_hook(api: HookAPI, path: Path) -> None:
    disallowed = _check_imports(path)
    if disallowed:
        for name in disallowed:
            log.error(
                f"[HOOK] {path.name} uses disallowed import: "
                f"'{name}' — hook skipped. "
            )
        return

    module_name = f"event_hooks.{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            log.warning(f"[HOOK] Could not create spec for: {path.name}")
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

    except SyntaxError as e:
        log.warning(f"[HOOK] Syntax error in {path.name}: {e}")
        return
    except Exception as e:
        log.warning(f"[HOOK] Failed to load {path.name}: {e}")
        return

    if hasattr(module, "register") and callable(module.register):
        try:
            module.register(api)
        except Exception as e:
            log.warning(f"[HOOK] register() failed in {path.name}: {e}")
    else:
        log.error(f"[HOOK] {path.name} has no register() function — skipped.")