#!/usr/bin/env python3
import logging
import sys

from core import (
    get_base_file,
    get_plugin_config_file,
    get_plugin_dir,
    load_config,
    parse_args,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)
log = logging.getLogger(__name__)

PLUGIN_DIR = get_plugin_dir()
CONFIG_FILE = get_plugin_config_file()
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
