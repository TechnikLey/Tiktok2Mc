from pathlib import Path
import sys
import yaml

def load_config(config: str | Path) -> dict:
    path = Path(config)

    if not path.exists():
        print(f"Config file not found: {path}")
        input("Press Enter zum Beenden...")
        sys.exit(1)

    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"YAML error in {path}: {e}")
    except Exception as e:
        print(f"General error in {path}: {e}")

    input("Press Enter zum Beenden...")
    sys.exit(1)