#!/usr/bin/env python3
# ==================================================
# timer - Countdown timer overlay plugin
# ==================================================
# Displays a countdown timer that resets on player
# death/respawn. When the timer hits zero it sends
# a POST to the win counter to increment wins.
# Works in pywebview AND as an OBS browser source.
# ==================================================

import webview, threading, requests, json, sys, yaml, logging, time
from flask import Flask, request, Response
from core import parse_args, AppConfig, get_root_dir, get_base_file, get_base_dir
from core.theme import load_plugin_theme, theme_css
from python.registry import register_plugin
from queue import Queue

# --- Paths ---
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

DATA_DIR = (ROOT_DIR / "data").resolve()
STATE_FILE = (DATA_DIR / "window_state_timer.json").resolve()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.INFO)

args = parse_args()

# --- Configuration ---
try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f: cfg = yaml.safe_load(f) or {}
except Exception: cfg = {}

TIMER_MINS = cfg.get("timer", {}).get("start_time", 10)
WIN_PORT = cfg.get("win_counter", {}).get("port", 29191)
WEB_PORT = cfg.get("timer", {}).get("port", 29189)
SERVER_HOST = cfg.get("server_host", "127.0.0.1")
ADD_URL = f"http://127.0.0.1:{WIN_PORT}/add?amount=1"
TIMER_EXE_PATH = get_base_file()

THEME = load_plugin_theme(cfg, "timer")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Timer",
        path=TIMER_EXE_PATH,
        enable=cfg.get("timer", {}).get("enabled", True),
        level=4,
        ics=True,
        port=WEB_PORT,
    ))
    sys.exit(0)

# --- Timer State (Python-side, works with or without pywebview) ---
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
                    return True  # signal: timer hit zero
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


# --- SSE client management ---
class OverlayClients:
    def __init__(self):
        self.listeners = []

    def add(self, q):
        self.listeners.append(q)

    def remove(self, q):
        try:
            self.listeners.remove(q)
        except ValueError:
            pass

    def notify(self, data):
        for q in self.listeners:
            q.put(data)


overlay_clients = OverlayClients()


def timer_tick_loop():
    while True:
        hit_zero = timer_state.tick()
        if hit_zero:
            log.info(f"[ACTION] Timer reached 0. Sending POST to {ADD_URL}")
            try:
                requests.post(ADD_URL, timeout=2)
            except Exception as e:
                log.error(f"Could not reach counter: {e}")
            threading.Timer(2.0, timer_state.reset).start()
        overlay_clients.notify(timer_state.get_state())
        time.sleep(1)


# --- Flask app ---
app = Flask(__name__)
window = None


def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f:
                return json.load(f)
        except Exception as e:
            log.info(f"[TIMER] Failed to load state: {e}")
    return {"width": 400, "height": 200}


@app.route("/save_dims", methods=["POST"])
def save_dims():
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(request.json, f)
    except Exception as e:
        log.info(f"[TIMER] Failed to save dimensions: {e}")
    return "OK"


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
    except Exception as e:
        log.info(f"[TIMER] Invalid JSON in webhook: {e}")
        return "OK"
    ev = data.get("event") if data else None
    if ev == "player_death":
        timer_state.pause()
        timer_state.reset()
    elif ev == "player_respawn":
        timer_state.unpause()
    return "OK"


@app.route("/stream")
def stream():
    q = Queue()
    overlay_clients.add(q)

    def generate():
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        except GeneratorExit:
            overlay_clients.remove(q)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/")
def index():
    return HTML_TEMPLATE


# --- HTML / CSS / JS (timer overlay) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{THEME_STYLE}
        body {
            background-color: var(--background); color: var(--text); margin: 0;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; overflow: hidden; font-family: 'Segoe UI', sans-serif;
            -webkit-app-region: drag; user-select: none;
        }
        #display {
            font-size: 70vh; font-weight: bold;
            font-variant-numeric: tabular-nums; white-space: nowrap;
        }
        .warning { color: var(--warning); }
        .blink {
            color: var(--blink);
            animation: syncFlash 1s infinite steps(1);
        }
        .critical {
            color: var(--danger) !important;
            animation: pulse 0.5s infinite ease-in-out;
        }
        @keyframes syncFlash {
            0% { opacity: 1; }
            50% { opacity: 0.2; }
            100% { opacity: 1; }
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.08); }
            100% { transform: scale(1); }
        }
    </style>
</head>
<body>
    <div id="display">00:00</div>
    <script>
        const display = document.getElementById('display');

        function update(data) {
            const t = data.time_left;
            const m = Math.floor(t / 60), s = t % 60;
            display.innerText = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');

            display.classList.remove('warning', 'blink', 'critical');

            if (t === 0 || data.is_waiting) {
                display.classList.add('critical');
            } else if (t <= 10) {
                display.classList.add('critical');
            } else if (t <= 30) {
                display.classList.add('blink');
            } else if (t <= 60) {
                display.classList.add('warning');
            }
        }

        const evtSource = new EventSource('/stream');
        evtSource.onmessage = function(e) {
            update(JSON.parse(e.data));
        };

        window.addEventListener('resize', () => {
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {
                fetch('/save_dims', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ width: window.outerWidth, height: window.outerHeight })
                });
            }, 500);
        });
    </script>
</body>
</html>
"""


gui_hidden = args.gui_hidden

if __name__ == '__main__':
    size = load_win_size()

    # Start the countdown thread
    tick_thread = threading.Thread(target=timer_tick_loop, daemon=True)
    tick_thread.start()

    # Start Flask
    server_thread = threading.Thread(
        target=lambda: app.run(host=SERVER_HOST, port=WEB_PORT, threaded=True, debug=False, use_reloader=False),
        daemon=True
    )
    server_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            'Scalable Timer',
            f'http://127.0.0.1:{WEB_PORT}',
            width=size['width'],
            height=size['height'],
            on_top=True,
            background_color=BG_COLOR,
        )
        webview.start()
    else:
        log.info(f"[TIMER] Running in gui_hidden mode. Open http://{SERVER_HOST}:{WEB_PORT} in OBS as a Browser Source.")
        server_thread.join()
