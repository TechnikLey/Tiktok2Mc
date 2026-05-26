#!/usr/bin/env python3
from core import load_config, parse_args, get_plugin_dir, get_plugin_config_file, get_base_file, AppConfig
from python.registry import register_plugin
import sys
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)

PLUGIN_DIR = get_plugin_dir()
CONFIG_FILE = get_plugin_config_file()
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=cfg.get("enabled", True),
        level=4,
        ics=False
    ))
    sys.exit(0)