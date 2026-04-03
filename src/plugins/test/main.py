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