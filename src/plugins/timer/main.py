import webview
import threading
import json
import sys
import time
import os
import urllib.request
from pathlib import Path
from core import parse_args, get_base_file, get_base_dir
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.INFO)

BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR.parent / "data").resolve()
STATE_FILE = (DATA_DIR / "window_state_timer.json").resolve()

args = parse_args()

cfg = load_plugin_config(PLUGIN_DIR)

TIMER_MINS = cfg.get("start_time", 10)
WEB_PORT = cfg.get("port", 29189)
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")

AUTO_WIN = cfg.get("auto_win", False)
PAUSE_ON_DEATH = cfg.get("pause_on_death", False)

THEME = load_plugin_theme(cfg, "timer")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "timer"


class TimerState:
    def __init__(self, initial_seconds):
        self.initial = initial_seconds
        self.time_left = initial_seconds
        self.is_paused = False
        self.is_waiting = False
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self.time_left = self.initial
            self.is_waiting = False

    def pause(self):
        with self._lock:
            self.is_paused = True

    def unpause(self):
        with self._lock:
            self.is_paused = False

    def tick(self):
        with self._lock:
            if not self.is_paused and not self.is_waiting and self.time_left > 0:
                self.time_left -= 1
                if self.time_left == 0:
                    self.is_waiting = True
                    return True
        return False

    def get_state(self):
        with self._lock:
            return {
                "time_left": self.time_left,
                "is_paused": self.is_paused,
                "is_waiting": self.is_waiting,
                "initial": self.initial,
            }


timer_state = TimerState(TIMER_MINS * 60)


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


def _api_get(path: str, timeout: int = 5) -> dict | None:
    try:
        req = urllib.request.Request(f"{API_BASE}{path}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning("API GET %s failed: %s", path, e)
        return None


def _push_state():
    _api_post(f"/plugins/{PLUGIN_NAME}/state", {"state": timer_state.get_state()})


def command_polling_loop():
    while True:
        result = _api_get(f"/plugins/{PLUGIN_NAME}/commands?wait=1", timeout=35)
        if result:
            for cmd_entry in result.get("commands", []):
                cmd = cmd_entry.get("command")
                if cmd == "start":
                    timer_state.unpause()
                    _push_state()
                elif cmd == "pause":
                    timer_state.pause()
                    _push_state()
                elif cmd == "reset":
                    timer_state.reset()
                    _push_state()
                elif cmd == "player_death":
                    if PAUSE_ON_DEATH:
                        timer_state.pause()
                        timer_state.reset()
                        _push_state()
                elif cmd == "player_respawn":
                    if PAUSE_ON_DEATH:
                        timer_state.unpause()
                        _push_state()


def timer_tick_loop():
    while True:
        hit_zero = timer_state.tick()
        if hit_zero:
            if AUTO_WIN:
                _api_post(f"/plugins/win-counter/command", {
                    "command": "add_win",
                    "args": {"amount": 1},
                })
            else:
                log.info("[TIMER] Timer reached 0 (auto_win disabled)")
            timer_state.reset()
        _push_state()
        time.sleep(1)


def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.info(f"[TIMER] Failed to load state: {e}")
    return {"width": 400, "height": 200}


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{THEME_STYLE}
        body {{
            background-color: var(--background); color: var(--text); margin: 0;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; overflow: hidden; font-family: 'Segoe UI', sans-serif;
            -webkit-app-region: drag; user-select: none;
        }}
        #display {{
            font-size: 70vh; font-weight: bold;
            font-variant-numeric: tabular-nums; white-space: nowrap;
        }}
        .warning {{ color: var(--warning); }}
        .blink {{
            color: var(--blink);
            animation: syncFlash 1s infinite steps(1);
        }}
        .critical {{
            color: var(--danger) !important;
            animation: pulse 0.5s infinite ease-in-out;
        }}
        @keyframes syncFlash {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.2; }}
            100% {{ opacity: 1; }}
        }}
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.08); }}
            100% {{ transform: scale(1); }}
        }}
    </style>
</head>
<body>
    <div id="display">00:00</div>
    <script>
        const display = document.getElementById('display');

        function update(data) {{
            const t = data.time_left;
            const m = Math.floor(t / 60), s = t % 60;
            display.innerText = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');

            display.classList.remove('warning', 'blink', 'critical');

            if (t === 0 || data.is_waiting) {{
                display.classList.add('critical');
            }} else if (t <= 10) {{
                display.classList.add('critical');
            }} else if (t <= 30) {{
                display.classList.add('blink');
            }} else if (t <= 60) {{
                display.classList.add('warning');
            }}
        }}

        const evtSource = new EventSource('/api/v1/plugins/timer/stream');
        evtSource.onmessage = function(e) {{
            update(JSON.parse(e.data));
        }};

        window.addEventListener('resize', () => {{
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {{
                fetch('/api/v1/plugins/timer/command', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ command: 'save_dims', args: {{ width: window.outerWidth, height: window.outerHeight }} }})
                }});
            }}, 500);
        }});
    </script>
</body>
</html>
""".format(THEME_STYLE=THEME_STYLE)


def _register_overlay():
    _api_post(f"/plugins/{PLUGIN_NAME}/overlay-html", {"html": HTML_TEMPLATE})


gui_hidden = args.gui_hidden

if __name__ == '__main__':
    size = load_win_size()

    _register_overlay()

    tick_thread = threading.Thread(target=timer_tick_loop, daemon=True)
    tick_thread.start()

    poll_thread = threading.Thread(target=command_polling_loop, daemon=True)
    poll_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            'Scalable Timer',
            f'http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay',
            width=size['width'],
            height=size['height'],
            on_top=True,
            background_color=BG_COLOR,
        )
        webview.start()
    else:
        log.info(f"[TIMER] Running in gui_hidden mode. Open http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay in OBS as a Browser Source.")
        tick_thread.join()
