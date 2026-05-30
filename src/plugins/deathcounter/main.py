import json
import sys
import threading
import webview
import os
import time
import urllib.request
from pathlib import Path
from core import parse_args, get_base_dir, get_base_file
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)

args = parse_args()

BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR.parent / "data").resolve()
STATE_FILE = (DATA_DIR / "window_state_death.json").resolve()

cfg = load_plugin_config(PLUGIN_DIR)
WEB_SERVER_PORT = cfg.get("port", 29190)
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")

THEME = load_plugin_theme(cfg, "death_counter")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "death-counter"


class DeathManager:
    def __init__(self):
        self.count = 0
        self._lock = threading.Lock()

    def add_death(self):
        with self._lock:
            self.count += 1

    def get_count(self):
        with self._lock:
            return self.count


death_manager = DeathManager()


def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.info(f"[DEATHCOUNTER] Failed to load state: {e}")
    return {"width": 500, "height": 400}


def _api_post(path: str, data: dict) -> bool:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{API_BASE}{path}", data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        log.warning("API POST %s failed: %s", path, e)
        return False


def _api_get(path: str) -> dict | None:
    try:
        req = urllib.request.Request(f"{API_BASE}{path}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning("API GET %s failed: %s", path, e)
        return None


def _push_state():
    _api_post(f"/plugins/{PLUGIN_NAME}/state", {
        "state": {"deaths": death_manager.get_count()}
    })


def command_polling_loop():
    while True:
        result = _api_get(f"/plugins/{PLUGIN_NAME}/commands")
        if result:
            for cmd_entry in result.get("commands", []):
                cmd = cmd_entry.get("command")
                if cmd == "player_death":
                    death_manager.add_death()
                    _push_state()
        time.sleep(0.5)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@900&display=swap');
""" + THEME_STYLE + """
        body, html { 
            background: var(--background); margin: 0; padding: 0;
            width: 100%; height: 100%; display: flex;
            flex-direction: column; justify-content: center; align-items: center;
            overflow: hidden; font-family: 'Inter', sans-serif; color: var(--text);
            user-select: none;
        }
        .label { font-size: 12vh; font-weight: 700; opacity: 0.7; letter-spacing: 1.5vw; margin-bottom: -2vh; }
        .count { font-size: 65vh; font-weight: 900; line-height: 1; }
        .bump { transform: scale(1.05); transition: 0.1s; }
    </style>
</head>
<body>
    <div id="card" style="display:flex; flex-direction:column; align-items:center;">
        <span class="label">DEATHS</span>
        <span id="counter" class="count">0</span>
    </div>
    <script>
        const card = document.getElementById('card');
        const counter = document.getElementById('counter');
        function connect() {
            const es = new EventSource("/api/v1/plugins/death-counter/stream");
            es.onmessage = (e) => {
                counter.innerText = JSON.parse(e.data).deaths;
                card.classList.add('bump');
                setTimeout(() => card.classList.remove('bump'), 200);
            };
            es.onerror = () => { es.close(); setTimeout(connect, 2000); };
        }
        connect();

        window.addEventListener('resize', () => {
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {
                fetch('/api/v1/plugins/death-counter/command', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ command: 'save_dims', args: { width: window.outerWidth, height: window.outerHeight } })
                });
            }, 500);
        });
    </script>
</body>
</html>
"""


def _register_overlay():
    _api_post(f"/plugins/{PLUGIN_NAME}/overlay-html", {"html": HTML_TEMPLATE})


gui_hidden = args.gui_hidden

if __name__ == "__main__":
    win = load_win_size()

    _register_overlay()

    poll_thread = threading.Thread(target=command_polling_loop, daemon=True)
    poll_thread.start()

    if not gui_hidden:
        webview.create_window('Death Counter',
                              f'http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay',
                              width=win['width'], height=win['height'],
                              on_top=True, background_color=BG_COLOR)
        webview.start()
    else:
        log.info("GUI hidden, running server only.")
        poll_thread.join()
