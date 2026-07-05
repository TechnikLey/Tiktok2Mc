#!/usr/bin/env python3
# ==========================================
# create_plugin.py - Plugin Scaffolding (Cross-Platform)
#
# Generates a modern BasePlugin-based plugin skeleton with:
#   - main.py (BasePlugin subclass)
#   - plugin.json (manifest with config_schema)
#   - config.yaml (local configuration overrides)
#   - version.txt (version + update URL)
#   - README.md (documentation)
# ==========================================

import sys
import re
from pathlib import Path
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)

log = logging.getLogger(__name__)

_src = Path(__file__).resolve().parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from core.version import TOOL_VERSION as VERSION

PLUGINS_DIR = Path("src/plugins")

CONFIG_YAML_TEMPLATE = '''\
# Plugin configuration
# All values here override the defaults defined in plugin.json → config_schema.

enabled: true
'''

MAIN_PY_TEMPLATE = '''\
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class {class_name}(BasePlugin):
    PLUGIN_NAME = "{name}"

    def __init__(self):
        super().__init__()
        cfg = self.config
        # Read config values here:
        # self._some_setting = cfg.get("some_setting", "default")
        self.register_handler("example", self._on_example)

    def _on_example(self, args: dict):
        log.info("[%s] Example command received: %s", self.PLUGIN_NAME, args)

    def on_tick(self):
        pass

    def get_overlay_html(self) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{self.theme_style}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: transparent;
        font-family: 'Inter', 'Segoe UI', sans-serif;
        overflow: hidden;
        width: 100vw; height: 100vh;
        display: flex; justify-content: center; align-items: center;
        color: var(--text);
        font-size: 5vh;
    }}
</style>
</head>
<body>
    <div>Hello from {display_name}!</div>
    <script>
        const es = new EventSource('/api/v1/plugins/{name}/stream');
        es.onmessage = e => {{ /* handle live updates */ }};
    </script>
</body>
</html>"""


if __name__ == "__main__":
    {class_name}().run()
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
  "min_api_version": "1.0.0",
  "capabilities": [],
  "depends_on": [],
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
        name = input("Please enter module name (a-z, 0-9, hyphens): ").strip()

        if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', name):
            log.info("\033[91mInvalid name! Only a-z, 0-9, and hyphens allowed (must start/end with letter/digit).\033[0m")
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

    # Derive class name from plugin name (kebab-case → PascalCase)
    class_name = "".join(part.capitalize() for part in plugin_name.replace("-", "_").split("_"))

    display_name = plugin_name.replace("-", " ").replace("_", " ").title()

    # Ask for update URL
    update_url = get_update_url()

    # Create main.py (BasePlugin-based)
    main_py = MAIN_PY_TEMPLATE.format(
        name=plugin_name,
        class_name=class_name,
        display_name=display_name,
    )
    (plugin_path / "main.py").write_text(main_py, encoding="utf-8")
    log.info("File 'main.py' created (BasePlugin subclass).")

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
    plugin_json = PLUGIN_JSON_TEMPLATE.format(
        name=plugin_name,
        display_name=display_name,
        update_url=update_url,
    )
    (plugin_path / "plugin.json").write_text(plugin_json, encoding="utf-8")
    log.info("File 'plugin.json' created (with config_schema and ports).")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
