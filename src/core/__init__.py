#!/usr/bin/env python3
from core.cli import parse_args
from core.utils import load_config
from core.paths import (
    get_base_dir,
    get_root_dir,
    get_base_file,
    get_config_file,
    get_plugin_dir,
    get_plugin_config_file,
    get_plugins_dir,
)
from core.models import AppConfig
from core.plugin_config import load_plugin_config, save_plugin_config, load_all_plugin_configs
from core.overlay import (
    OverlayConfig,
    OverlayClient,
    OverlayManager,
    get_overlay_manager,
    send_overlay_text,
)