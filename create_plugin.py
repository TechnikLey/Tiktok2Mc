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
# All plugin-specific settings live here.

enabled: true
'''

MAIN_PY_TEMPLATE = '''\
import logging
import sys
import os
from pathlib import Path
from core import parse_args, get_base_file
from core.plugin_config import load_plugin_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).resolve().parent
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_plugin_config(PLUGIN_DIR)

gui_hidden = args.gui_hidden

# Your plugin code goes here...
'''

PLUGIN_JSON_TEMPLATE = '''\
{{
  "name": "{name}",
  "version": "1.0.0",
  "entry_point": "src/plugins/{name}/main.py",
  "display_name": "{display_name}",
  "description": "",
  "author": "",
  "homepage": "",
  "ports": {{
    "declared": [],
    "protocol": "tcp"
  }},
  "min_api_version": "1.0.0",
  "capabilities": [],
  "depends_on": [],
  "auto_enable": false,
  "update_url": "{update_url}",
  "config_schema": {{
    "version": 1,
    "fields": [
      {{
        "key": "enabled",
        "type": "boolean",
        "default": true,
        "label": "Enable Plugin",
        "help": "Turn this plugin on or off",
        "category": "General"
      }}
    ]
  }}
}}
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
    (plugin_path / "main.py").write_text(MAIN_PY_TEMPLATE, encoding="utf-8")
    log.info("File 'main.py' created.")

    # Ask for update URL
    update_url = get_update_url()

    # Create version.txt
    version_content = f"version: {VERSION}\nupdate_url: {update_url}\n"
    (plugin_path / "version.txt").write_text(version_content, encoding="utf-8")
    log.info("File 'version.txt' created.")

    # Create README.md
    readme = f"# {plugin_name}\n\nVersion: {VERSION}\n\nDescription: \n"
    (plugin_path / "README.md").write_text(readme, encoding="utf-8")
    log.info("File 'README.md' created.")

    # Create config.yaml
    (plugin_path / "config.yaml").write_text(CONFIG_YAML_TEMPLATE, encoding="utf-8")
    log.info("File 'config.yaml' created.")

    # Create plugin.json with embedded schema
    display_name = plugin_name.replace("-", " ").replace("_", " ").title()
    plugin_json = PLUGIN_JSON_TEMPLATE.format(
        name=plugin_name,
        display_name=display_name,
        update_url=update_url,
    )
    (plugin_path / "plugin.json").write_text(plugin_json, encoding="utf-8")
    log.info("File 'plugin.json' created (with config_schema).")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
