import webview
import threading
import json
import sys
import os
import time
import urllib.request
from pathlib import Path
from core import parse_args, get_base_file, get_base_dir
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)

BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR.parent / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATS_FILE = (DATA_DIR / "stats.json").resolve()
STATE_FILE = (DATA_DIR / "window_state_wins.json").resolve()

args = parse_args()


def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                size = json.load(f)
                return {
                    "width": max(size.get("width", 600), 200),
                    "height": max(size.get("height", 300), 100)
                }
        except Exception as e:
            log.info(f"[WINCOUNTER] Failed to load window size: {e}")
    return {"width": 600, "height": 300}


cfg = load_plugin_config(PLUGIN_DIR)
PORT = cfg.get("port", 29191)
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
DECREMENT_ON_DEATH = cfg.get("decrement_on_death", False)

THEME = load_plugin_theme(cfg, "win_counter")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "win-counter"


class WinManager:
    def __init__(self):
        self.wins, self.needed, self.record_low = 0, 10, 0
        self._lock = threading.Lock()
        self.load_stats()

    def load_stats(self):
        if STATS_FILE.exists():
            try:
                with STATS_FILE.open("r", encoding="utf-8") as f:
                    d = json.load(f)
                    self.wins = d.get("wins", 0)
                    self.needed = d.get("needed", 10)
                    self.record_low = d.get("record_low", d.get("record", 0))
            except Exception as e:
                log.info(f"[WINCOUNTER] Failed to load stats: {e}")

    def save_stats(self):
        try:
            with STATS_FILE.open("w", encoding="utf-8") as f:
                json.dump({"wins": self.wins, "record_low": self.record_low, "needed": self.needed}, f, indent=4)
        except Exception as e:
            log.info(f"[WINCOUNTER] Failed to save stats: {e}")

    def _notify(self):
        self.save_stats()

    def add_win(self, amount=1):
        with self._lock:
            self.wins += amount
            while self.wins >= self.needed:
                self.wins -= self.needed
                self.needed += 10
        self._notify()

    def remove_win(self, amount=1):
        with self._lock:
            self.wins -= amount
            if self.wins < self.record_low:
                self.record_low = self.wins
        self._notify()

    def get_data(self):
        with self._lock:
            return {
                "wins": self.wins,
                "needed": self.needed,
                "record_low": self.record_low,
                "win_color": THEME["danger"] if self.wins < 0 else THEME["text"]
            }


win_manager_instance = WinManager()


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
    _api_post(f"/plugins/{PLUGIN_NAME}/state", {"state": win_manager_instance.get_data()})


def command_polling_loop():
    while True:
        result = _api_get(f"/plugins/{PLUGIN_NAME}/commands")
        if result:
            for cmd_entry in result.get("commands", []):
                cmd = cmd_entry.get("command")
                args_data = cmd_entry.get("args", {})
                if cmd == "add_win":
                    win_manager_instance.add_win(int(args_data.get("amount", 1)))
                    _push_state()
                elif cmd == "remove_win":
                    win_manager_instance.remove_win(int(args_data.get("amount", 1)))
                    _push_state()
                elif cmd == "player_death":
                    if DECREMENT_ON_DEATH:
                        win_manager_instance.remove_win(1)
                        _push_state()
        time.sleep(0.5)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
""" + THEME_STYLE + """
        body { 
            background-color: var(--background); color: var(--text); 
            font-family: 'Consolas', monospace; margin: 0; 
            display: flex; flex-direction: column; 
            justify-content: center; align-items: center;
            height: 100vh; width: 100vw;
            overflow: hidden; user-select: none;
        }
        .container { 
            display: flex; align-items: center; 
            gap: 3vw; 
            font-size: 25vmin;
            font-weight: bold; 
            white-space: nowrap;
            line-height: 1;
        }
        .record-section { 
            margin-top: 1vh; 
            font-size: 10vmin; 
            color: var(--muted); 
        }
    </style>
</head>
<body>
    <div class="container">
        <span>Wins:</span><span id="wins">0</span><span style="color: var(--separator);">|</span><span id="needed">10</span>
    </div>
    <div class="record-section">Record Low: <span id="record_low">0</span></div>
    
    <script>
        const es = new EventSource("/api/v1/plugins/win-counter/stream");
        es.onmessage = (e) => {
            const d = JSON.parse(e.data);
            document.getElementById('wins').innerText = d.wins;
            document.getElementById('wins').style.color = d.win_color;
            document.getElementById('needed').innerText = d.needed;
            document.getElementById('record_low').innerText = d.record_low;
        };

        window.addEventListener('resize', () => {
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {
                fetch('/api/v1/plugins/win-counter/command', {
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
    size = load_win_size()

    _register_overlay()

    poll_thread = threading.Thread(target=command_polling_loop, daemon=True)
    poll_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            'Win Counter Overlay',
            f'http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay',
            width=size['width'] + 30,
            height=size['height'] + 30,
            on_top=True,
            background_color=BG_COLOR
        )
        webview.start()
    else:
        log.info("GUI hidden, running server only.")
        poll_thread.join()
