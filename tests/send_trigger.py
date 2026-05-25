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
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

log = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    CONFIG_FILE = BASE_DIR.parent / "config" / "config.yaml"
else:
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_FILE = BASE_DIR.parent / "defaults" / "config.yaml"

if not CONFIG_FILE.exists():
    log.error(f"Configuration file not found at {CONFIG_FILE}")
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
                log.info("TikTok connection is now DISABLED.")
            else:
                log.info("TikTok connection is now ENABLED.")
            return
        if data.get("status") == "ok":
            log.info(f"Trigger '{data['trigger']}' for user '{data['user']}' sent successfully.")
        else:
            log.error(f"{data.get('message', 'Unknown error.')}")
    except requests.exceptions.ConnectionError:
        log.error(f"Connection to {TRIGGER_URL} failed. Is the bot running?")
    except requests.exceptions.Timeout:
        log.error("Timeout - Bot did not respond.")
    except Exception as e:
        log.error(f"{e}")


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
            log.info(f"Comment '{text}' from '{user}' processed.")
        else:
            log.error(f"{data.get('message', 'Unknown error.')}")
    except requests.exceptions.ConnectionError:
        log.error(f"Connection to {COMMENT_URL} failed. Is the bot running?")
    except requests.exceptions.Timeout:
        log.error("Timeout - Bot did not respond.")
    except Exception as e:
        log.error(f"{e}")


def main():
    log.info("=" * 50)
    log.info("  Custom Trigger & Comment Simulator")
    log.info(f"  Bot address: {TRIGGER_URL}")
    log.info("  Ctrl+C to exit")
    log.info("=" * 50)

    while True:
        try:
            trigger = input("Trigger (or 'comment'): ").strip()
            if not trigger:
                log.info("No trigger entered, please try again.")
                continue

            if trigger.lower() == "comment":
                user_input = input("User (optional, Enter = TestUser): ").strip()
                user = user_input if user_input else "TestUser"
                text = input("Comment text: ").strip()
                if not text:
                    log.info("No comment text entered.")
                    continue
                mod = input("Moderator (y/n): ").strip().lower() == "y"
                sf = input("Superfan (y/n): ").strip().lower() == "y"
                fc = input("Fanclub (y/n): ").strip().lower() == "y"
                send_comment(user, text, mod, sf, fc)
            elif trigger.lower() == "tiktok":
                send_trigger(trigger, "System")
            else:
                user_input = input("User (optional, Enter = System): ").strip()
                user = user_input if user_input else "System"
                send_trigger(trigger, user)

        except KeyboardInterrupt:
            log.info("\n[STOP] Script exited.")
            sys.exit(0)


if __name__ == "__main__":
    main()
