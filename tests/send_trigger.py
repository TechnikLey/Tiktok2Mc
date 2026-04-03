#!/usr/bin/env python3
# ==================================================
# send_trigger.py - Custom Trigger Simulator
# ==================================================
# Sends simulated triggers (e.g. "follow", "like", "5655")
# to the running bot as if they were real TikTok events.
# The bot must be running, TikTok connection is NOT required.
#
# Usage:
#   python send_trigger.py
#
# When prompted:
#   Trigger: follow
#   User (optional): TestUser
# ==================================================

import requests
import sys
from pathlib import Path
import yaml

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    CONFIG_FILE = BASE_DIR.parent / "config" / "config.yaml"
else:
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_FILE = BASE_DIR.parent / "defaults" / "config.yaml"

if not CONFIG_FILE.exists():
    print(f"[ERROR] Configuration file not found at {CONFIG_FILE}")
    sys.exit(1)

with open(CONFIG_FILE, "r") as f:
    cfg = yaml.safe_load(f)

BOT_HOST = "http://127.0.0.1"
BOT_PORT = cfg.get("MinecraftServerAPI", {}).get("WebServerPort", 7777)  # Must match WebServerPort in config.yaml

URL = f"{BOT_HOST}:{BOT_PORT}/custom_trigger"

def send_trigger(trigger: str, user: str = "System"):
    payload = {"trigger": trigger, "user": user}
    try:
        response = requests.post(URL, json=payload, timeout=5)
        data = response.json()
        # Special handling for TikTok toggle
        if trigger.strip().lower() == "tiktok" and data.get("status") == "ok":
            state = data.get("message", "").lower()
            if "true" in state:
                print("[INFO] TikTok connection is now DISABLED.")
            else:
                print("[INFO] TikTok connection is now ENABLED.")
            return
        if data.get("status") == "ok":
            print(f"[OK] Trigger '{data['trigger']}' for user '{data['user']}' sent successfully.")
        else:
            print(f"[ERROR] {data.get('message', 'Unknown error.')}")
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Connection to {URL} failed. Is the bot running?")
    except requests.exceptions.Timeout:
        print("[ERROR] Timeout - Bot did not respond.")
    except Exception as e:
        print(f"[ERROR] {e}")

def main():
    print("=" * 50)
    print("  Custom Trigger Simulator")
    print(f"  Bot address: {URL}")
    print("  Ctrl+C to exit")
    print("=" * 50)
    print()

    while True:
        try:
            trigger = input("Trigger: ").strip()
            if not trigger:
                print("[INFO] No trigger entered, please try again.")
                continue

            user_input = input("User (optional, Enter = System): ").strip()
            user = user_input if user_input else "System"

            send_trigger(trigger, user)
            print()

        except KeyboardInterrupt:
            print("\n[STOP] Script exited.")
            sys.exit(0)

if __name__ == "__main__":
    main()