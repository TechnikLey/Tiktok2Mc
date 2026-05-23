#!/usr/bin/env python3
# ==================================================
# send_trigger.py - Custom Trigger Simulator
# ==================================================
# Sends simulated triggers (e.g. "follow", "like", "5655")
# or comments to the running bot as if they were real events.
# The bot must be running, TikTok connection is NOT required.
#
# Usage:
#   python send_trigger.py
#
# Triggers:
#   Trigger: follow
#   User (optional): TestUser
#
# Comments:
#   Trigger: comment
#   User (optional): TestUser
#   Comment text: #say Hello
#   Moderator (y/n): n
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
BOT_PORT = cfg.get("minecraft_server_api", {}).get("web_server_port", 29188)

TRIGGER_URL = f"{BOT_HOST}:{BOT_PORT}/custom_trigger"
COMMENT_URL = f"{BOT_HOST}:{BOT_PORT}/test_comment"


def send_trigger(trigger: str, user: str = "System"):
    payload = {"trigger": trigger, "user": user}
    try:
        response = requests.post(TRIGGER_URL, json=payload, timeout=5)
        data = response.json()
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
        print(f"[ERROR] Connection to {TRIGGER_URL} failed. Is the bot running?")
    except requests.exceptions.Timeout:
        print("[ERROR] Timeout - Bot did not respond.")
    except Exception as e:
        print(f"[ERROR] {e}")


def send_comment(user: str, text: str, moderator: bool = False, superfan: bool = False, fanclub: bool = False):
    payload = {
        "user": user,
        "text": text,
        "moderator": moderator,
        "superfan": superfan,
        "fanclub": fanclub,
    }
    try:
        response = requests.post(COMMENT_URL, json=payload, timeout=5)
        data = response.json()
        if data.get("status") == "ok":
            print(f"[OK] Comment '{text}' from '{user}' processed.")
        else:
            print(f"[ERROR] {data.get('message', 'Unknown error.')}")
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Connection to {COMMENT_URL} failed. Is the bot running?")
    except requests.exceptions.Timeout:
        print("[ERROR] Timeout - Bot did not respond.")
    except Exception as e:
        print(f"[ERROR] {e}")


def main():
    print("=" * 50)
    print("  Custom Trigger & Comment Simulator")
    print(f"  Bot address: {TRIGGER_URL}")
    print("  Ctrl+C to exit")
    print("=" * 50)
    print()

    while True:
        try:
            trigger = input("Trigger (or 'comment'): ").strip()
            if not trigger:
                print("[INFO] No trigger entered, please try again.")
                continue

            if trigger.lower() == "comment":
                user_input = input("User (optional, Enter = TestUser): ").strip()
                user = user_input if user_input else "TestUser"
                text = input("Comment text: ").strip()
                if not text:
                    print("[INFO] No comment text entered.")
                    continue
                mod = input("Moderator (y/n): ").strip().lower() == "y"
                sf = input("Superfan (y/n): ").strip().lower() == "y"
                fc = input("Fanclub (y/n): ").strip().lower() == "y"
                send_comment(user, text, mod, sf, fc)
            else:
                user_input = input("User (optional, Enter = System): ").strip()
                user = user_input if user_input else "System"
                send_trigger(trigger, user)

            print()

        except KeyboardInterrupt:
            print("\n[STOP] Script exited.")
            sys.exit(0)


if __name__ == "__main__":
    main()
