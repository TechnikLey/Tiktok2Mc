#!/usr/bin/env python3
# ==========================================
# create_plugin.py - Plugin Scaffolding (Cross-Platform)
# ==========================================

import sys
import re
from pathlib import Path

PLUGINS_DIR = Path("src/plugins")
VERSION = "v1.0.0"

MAIN_PY_TEMPLATE = '''\
from core import load_config, parse_args, get_root_dir, get_base_dir, get_base_file, register_plugin, AppConfig
import sys

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
DATA_DIR = (ROOT_DIR / "data").resolve()
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=True,
        level=4,
        ics=False
    ))
    sys.exit(0)
'''


def get_valid_plugin_name():
    while True:
        name = input("Please enter module name (only a-z and 0-9): ").strip()

        if not re.match(r'^[a-z0-9]+$', name):
            print("\033[91mInvalid name! Only a-z and 0-9 allowed.\033[0m")
        elif (PLUGINS_DIR / name).exists():
            print("\033[91mFolder already exists! Please choose another name.\033[0m")
        else:
            return name


def main():
    plugin_name = get_valid_plugin_name()

    plugin_path = PLUGINS_DIR / plugin_name
    plugin_path.mkdir(parents=True, exist_ok=True)
    print(f"Folder '{plugin_name}' created.")

    # Create main.py
    (plugin_path / "main.py").write_text(MAIN_PY_TEMPLATE, encoding="utf-8")
    print("File 'main.py' created.")

    # Create version.txt
    (plugin_path / "version.txt").write_text(VERSION + "\n", encoding="utf-8")
    print(f"File 'version.txt' with content '{VERSION}' created.")

    # Create README.md
    readme = f"# {plugin_name}\n\nVersion: {VERSION}\n\nDescription: \n"
    (plugin_path / "README.md").write_text(readme, encoding="utf-8")
    print("File 'README.md' created.")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
