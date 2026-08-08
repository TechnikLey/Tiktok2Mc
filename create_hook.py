#!/usr/bin/env python3
# ==========================================
# create_hook.py - Event Hook Scaffolding (Cross-Platform)
# ==========================================

import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)

log = logging.getLogger(__name__)

_src = Path(__file__).resolve().parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


MAIN_HOOKS_DIR = Path("src/hooks")
PLUGINS_DIR = Path("src/plugins")

MAIN_PY_TEMPLATE = '''\
from core.hook_api import HookAPI
import logging
log = logging.getLogger(__name__)


def register(api: HookAPI):
    def my_handler(user, trigger, context):
        """Handle a $-command triggered from actions.mca."""
        api.log(f"{name} triggered by {{user}}")
        api.rcon_enqueue([
            f"say {{user}} triggered {name}!",
        ])

    api.register_action("{action_name}", my_handler)
    log.info("[{display_name}] Registered action: {action_name}")
'''

HOOK_JSON_TEMPLATE = '''\
{{
  "name": "{name}",
  "version": "1.0.0",
  "display_name": "{display_name}",
  "description": "",
  "author": "",
  "min_api_version": "1.0.0",
  "capabilities": [],
  "plugin": "{plugin}",
  "update_url": "{update_url}",
  "config_schema": {{
    "version": 1,
    "fields": [
      {{
        "key": "enabled",
        "type": "boolean",
        "default": true,
        "label": "Enable Hook",
        "help": "Turn this hook on or off",
        "category": "General"
      }}
    ]
  }}
}}
'''

CONFIG_YAML_TEMPLATE = '''\
# ==========================================
# Hook configuration
# ==========================================
# This is the local configuration file for this hook.
# Settings defined here are accessible via api.get_hook_config("{name}").

enabled: true
'''


def get_valid_hook_name():
    while True:
        name = input("Please enter hook name (a-z, 0-9, hyphens, underscores): ").strip()

        if not re.match(r'^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$|^[a-z0-9]$', name):
            log.info("\033[91mInvalid name! Only a-z, 0-9, hyphens, and underscores allowed (must start/end with letter/digit).\033[0m")
        else:
            return name


def check_name_unique(name: str, target_dir: Path) -> bool:
    """Check that no hook with this name exists in target location."""
    hook_json_path = target_dir / name / "hook.json"
    if hook_json_path.exists():
        log.info(f"\033[93mA hook named '{name}' already exists in {target_dir / name}\033[0m")
        return False

    # Also scan existing hooks via their manifests
    from core.hook_manifest import discover_hooks_dirs, load_hook_manifest

    for parent_dir in discover_hooks_dirs():
        for child in sorted(parent_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = load_hook_manifest(child)
            if manifest and manifest.name == name:
                log.info(f"\033[93mHook name '{name}' is already used by {child}\033[0m")
                return False
    return True


def get_action_name(hook_name: str):
    """Default action name based on hook name, but let user override."""
    default_action = hook_name
    user_input = input(f"Action name for actions.mca (default: ${default_action}): ").strip()
    if not user_input:
        return default_action
    return user_input


def get_update_url():
    url = input("GitHub API update URL (optional, Enter to skip):\nhttps://api.github.com/repos/").strip()
    if not url:
        return ""
    full_url = f"https://api.github.com/repos/{url}"
    if not full_url.endswith("/releases/latest"):
        if full_url.endswith("/"):
            full_url += "releases/latest"
        else:
            full_url += "/releases/latest"
    return full_url


def main():
    hook_name = get_valid_hook_name()

    # Choose location: main hooks dir or plugin-bundled
    log.info("\nWhere should this hook be placed?")
    log.info("  1) Main hooks directory (hooks/)")
    log.info("  2) Plugin-bundled (plugins/<plugin>/hooks/)")
    choice = input("Choice (1 or 2, default: 1): ").strip()

    plugin_name = ""
    if choice == "2":
        # List available plugins
        plugins = [d.name for d in sorted(PLUGINS_DIR.iterdir()) if d.is_dir() and (d / "plugin.json").exists()]
        if not plugins:
            log.info("\033[93mNo plugins found in src/plugins/.\033[0m")
            log.info("Falling back to main hooks directory.")
            choice = "1"
        else:
            log.info("Available plugins:")
            for p in plugins:
                log.info(f"  - {p}")
            plugin_name = input("Enter plugin name: ").strip()
            plugin_hooks_dir = PLUGINS_DIR / plugin_name / "hooks"
            if not plugin_hooks_dir.exists():
                create = input(f"Plugin hooks dir {plugin_hooks_dir} doesn't exist. Create it? (y/n, default: y): ").strip().lower()
                if create == "n":
                    log.info("Cancelled.")
                    return
                plugin_hooks_dir.mkdir(parents=True, exist_ok=True)
                log.info(f"Created: {plugin_hooks_dir}")
            target_dir = plugin_hooks_dir
    else:
        target_dir = MAIN_HOOKS_DIR

    # Check uniqueness
    if not check_name_unique(hook_name, target_dir):
        retry = input("Try a different name? (y/n): ").strip().lower()
        if retry == "y":
            return main()
        return

    hook_path = target_dir / hook_name
    if hook_path.exists():
        log.info(f"\033[91mFolder {hook_path} already exists!\033[0m")
        return

    hook_path.mkdir(parents=True, exist_ok=True)
    log.info(f"Folder '{hook_name}' created at {hook_path}.")

    # Ask for action name
    action_name = get_action_name(hook_name)

    # Ask for update URL
    update_url = get_update_url()

    # Create main.py
    display_name = hook_name.replace("-", " ").replace("_", " ").title()
    main_py = MAIN_PY_TEMPLATE.format(
        name=hook_name,
        display_name=display_name,
        action_name=action_name,
    )
    (hook_path / "main.py").write_text(main_py, encoding="utf-8")
    log.info("File 'main.py' created.")

    # Create hook.json
    hook_json = HOOK_JSON_TEMPLATE.format(
        name=hook_name,
        display_name=display_name,
        plugin=plugin_name,
        update_url=update_url,
    )
    (hook_path / "hook.json").write_text(hook_json, encoding="utf-8")
    log.info("File 'hook.json' created (with config_schema).")

    # Create config.yaml
    config_yaml = CONFIG_YAML_TEMPLATE.format(name=hook_name)
    (hook_path / "config.yaml").write_text(config_yaml, encoding="utf-8")
    log.info("File 'config.yaml' created.")

    log.info(f"\n\033[92mHook '{hook_name}' created successfully!\033[0m")
    log.info(f"  Location: {hook_path}")
    log.info(f"  Action: ${action_name} (use in actions.mca)")
    log.info("  Register function: register(api) in main.py")
    log.info(f"  Config: api.get_hook_config(\"{hook_name}\")")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
