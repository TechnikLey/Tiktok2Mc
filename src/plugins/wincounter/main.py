#!/usr/bin/env python3
# ==================================================
# wincounter - Win/loss counter overlay plugin
# ==================================================
# Tracks wins and losses.  Wins via POST /add,
# optional death decrement via webhook
# (decrement_on_death).  Win escalation: when wins
# reach "needed", target += 10 and wins reset.
# State is persisted to stats.json.
# ==================================================

import webview, threading, json, sys, os
from pathlib import Path
from flask import Flask, render_template_string, Response, request
from queue import Queue
from core import parse_args, get_base_file, get_base_dir
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)

# --- Paths ---
BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR.parent / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATS_FILE = (DATA_DIR / "stats.json").resolve()
STATE_FILE = (DATA_DIR / "window_state_wins.json").resolve()

args = parse_args()

# --- Window state (restores last known size) ---
def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                size = json.load(f)
                # Validate that dimensions are not accidentally too small
                return {
                    "width": max(size.get("width", 600), 200),
                    "height": max(size.get("height", 300), 100)
                }
        except Exception as e:
            log.info(f"[WINCOUNTER] Failed to load window size: {e}")
    return {"width": 600, "height": 300}

# --- Configuration ---
cfg = load_plugin_config(PLUGIN_DIR)
PORT = cfg.get("port", 29191)
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
DECREMENT_ON_DEATH = cfg.get("decrement_on_death", False)

THEME = load_plugin_theme(cfg, "win_counter")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]
WINCOUNTER_EXE_PATH = get_base_file()


app = Flask(__name__)
win_manager_instance = None  # Initialized below

class WinManager:
    """Tracks wins, losses, and the escalating win target. Persists state to disk."""
    def __init__(self):
        self.wins, self.needed, self.record_low = 0, 10, 0
        self.listeners = []
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
        data = self.get_data()
        with self._lock:
            for q in list(self.listeners):
                q.put(data)

    def add_win(self, amount=1):
        self.wins += amount
        while self.wins >= self.needed:
            self.wins -= self.needed
            self.needed += 10
        self._notify()

    def remove_win(self, amount=1):
        self.wins -= amount
        if self.wins < self.record_low:
            self.record_low = self.wins
        self._notify()

    def get_data(self):
        return {
            "wins": self.wins,
            "needed": self.needed,
            "record_low": self.record_low,
            "win_color": THEME["danger"] if self.wins < 0 else THEME["text"]
        }

win_manager_instance = WinManager()

# --- HTML template (browser source overlay) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{THEME_STYLE}
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
        const es = new EventSource("/stream");
        es.onmessage = (e) => {
            const d = JSON.parse(e.data);
            document.getElementById('wins').innerText = d.wins;
            document.getElementById('wins').style.color = d.win_color;
            document.getElementById('needed').innerText = d.needed;
            document.getElementById('record_low').innerText = d.record_low;
        };

        // Window resize: save outer dimensions for state persistence.
        window.addEventListener('resize', () => {
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {
                fetch('/save_dims', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        width: window.outerWidth, 
                        height: window.outerHeight 
                    })
                });
            }, 500);
        });
    </script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE.format(THEME_STYLE=THEME_STYLE))

@app.route("/save_dims", methods=["POST"])
def save_dims():
    data = request.json or {}
    with STATE_FILE.open("w", encoding="utf-8") as f: json.dump(data, f)
    return "OK"

@app.route("/add", methods=["POST"])
def add():
    win_manager_instance.add_win(int(request.args.get('amount', 1)))
    return "OK"

@app.route("/remove", methods=["POST"])
def remove():
    amount = int(request.args.get('amount', 1))
    win_manager_instance.remove_win(amount)
    return "OK"

@app.route('/webhook', methods=['POST'])
def handle_minecraft_events():
    try:
        data = request.json
        if not data:
            return {"status": "no data"}, 400

        event = data.get("event")

        if event == "player_death":
            if DECREMENT_ON_DEATH:
                win_manager_instance.remove_win(1)
                log.info("[WINCOUNTER] Player died — win removed.")
            else:
                log.debug("[WINCOUNTER] Ignoring death event (decrement_on_death disabled)")

    except Exception as e:
        log.error(f"Webhook error: {e}")

    return {"status": "processed"}, 200

@app.route("/stream")
def stream():
    # Create a queue for this specific browser tab (SSE listener)
    q = Queue()
    with win_manager_instance._lock:
        win_manager_instance.listeners.append(q)
    
    def event_stream():
        try:
            yield f"data: {json.dumps(win_manager_instance.get_data())}\n\n"
            while True:
                try:
                    result = q.get(timeout=1)
                    yield f"data: {json.dumps(result)}\n\n"
                except Exception:
                    yield f"data: {json.dumps(win_manager_instance.get_data())}\n\n"
        except GeneratorExit:
            pass
        finally:
            with win_manager_instance._lock:
                try: win_manager_instance.listeners.remove(q)
                except ValueError: pass
            
    return Response(event_stream(), mimetype="text/event-stream")

gui_hidden = args.gui_hidden

if __name__ == "__main__":
    size = load_win_size()
    server_thread = threading.Thread(target=lambda: app.run(host=SERVER_HOST, port=PORT, threaded=True, use_reloader=False), daemon=True)

    server_thread.start()
    
    if not gui_hidden:
        # Create the window
        window = webview.create_window(
            'Win Counter Overlay', 
            f'http://127.0.0.1:{PORT}', 
            width=size['width'] + 30, 
            height=size['height'] + 30, 
            on_top=True,
            background_color=BG_COLOR
        )
        webview.start()
    else:
        log.info("GUI hidden, running server only.")
        server_thread.join()
