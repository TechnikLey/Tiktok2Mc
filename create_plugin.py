#!/usr/bin/env python3
# ==========================================
# create_plugin.py - Plugin Scaffolding (Cross-Platform)
# ==========================================

import sys
import re
from pathlib import Path
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)

log = logging.getLogger(__name__)

PLUGINS_DIR = Path("src/plugins")
VERSION = "v1.0.0"

CONFIG_YAML_TEMPLATE = '''\
# ==========================================
# Plugin configuration
# ==========================================
# This is the local configuration file for this plugin.
# Settings here override the global config.yaml when applicable.

enabled: true
'''

MAIN_PY_TEMPLATE = '''\
from core import load_config, parse_args, get_plugin_dir, get_plugin_config_file, get_base_file, AppConfig
from python.registry import register_plugin
import sys

PLUGIN_DIR = get_plugin_dir()
CONFIG_FILE = get_plugin_config_file()
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="{name}",
        path=MAIN_FILE,
        enable=cfg.get("enabled", True),
        level=4,
        ics=False,
        port=0
    ))
    sys.exit(0)
'''

def get_valid_plugin_name():
    while True:
        name = input("Please enter module name (only a-z and 0-9): ").strip()

        if not re.match(r'^[a-z0-9]+$', name):
            log.info("\033[91mInvalid name! Only a-z and 0-9 allowed.\033[0m")
        elif (PLUGINS_DIR / name).exists():
            log.info("\033[91mFolder already exists! Please choose another name.\033[0m")
        else:
            return name

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
    plugin_name = get_valid_plugin_name()

    plugin_path = PLUGINS_DIR / plugin_name
    plugin_path.mkdir(parents=True, exist_ok=True)
    log.info(f"Folder '{plugin_name}' created.")

    # Create main.py
    (plugin_path / "main.py").write_text(MAIN_PY_TEMPLATE.format(name=plugin_name), encoding="utf-8")
    log.info("File 'main.py' created.")

    # Ask for update URL
    update_url = get_update_url()

    # Create version.txt
    version_content = f"version: {VERSION}\nupdate_url: {update_url}\n"
    (plugin_path / "version.txt").write_text(version_content, encoding="utf-8")
    log.info(f"File 'version.txt' created.")

    # Create README.md
    readme = f"# {plugin_name}\n\nVersion: {VERSION}\n\nDescription: \n"
    (plugin_path / "README.md").write_text(readme, encoding="utf-8")
    log.info("File 'README.md' created.")

    # Create config.yaml
    (plugin_path / "config.yaml").write_text(CONFIG_YAML_TEMPLATE, encoding="utf-8")
    log.info("File 'config.yaml' created.")

    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()