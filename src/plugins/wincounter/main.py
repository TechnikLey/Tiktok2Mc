# ==================================================
# wincounter - Win/loss counter overlay plugin
# ==================================================
# Tracks wins and losses. Wins increase on timer
# expiry (POST /add), deaths subtract via webhook.
# When wins reach the "needed" threshold, the target
# increases by 10 and wins reset. State is persisted
# to stats.json.
# ==================================================

import webview, threading, json, sys, yaml
from pathlib import Path
from flask import Flask, render_template_string, Response, request
from queue import Queue
from core import parse_args, register_plugin, AppConfig, get_base_file, get_base_dir, get_root_dir

# --- Paths ---
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

DATA_DIR = (ROOT_DIR / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATS_FILE = (DATA_DIR / "stats.json").resolve()
STATE_FILE = (DATA_DIR / "window_state_wins.json").resolve()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

args = parse_args()

# --- Window state (restores last known size) ---
def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f:
                size = json.load(f)
                # Validate that dimensions are not accidentally too small
                return {
                    "width": max(size.get("width", 600), 200),
                    "height": max(size.get("height", 300), 100)
                }
        except Exception: pass
    return {"width": 600, "height": 300}

# --- Configuration ---
try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except Exception: cfg = {}
PORT = cfg.get("WinCounter", {}).get("WebServerPort", 8080)
WINCOUNTER_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Win Counter",
        path=WINCOUNTER_EXE_PATH,
        enable=cfg.get("WinCounter", {}).get("Enable", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

app = Flask(__name__)
win_manager_instance = None  # Initialized below

class WinManager:
    """Tracks wins, losses, and the escalating win target. Persists state to disk."""
    def __init__(self):
        self.wins, self.needed, self.record = 0, 10, 0
        self.listeners = []
        self.load_stats()

    def load_stats(self):
        if STATS_FILE.exists():
            try:
                with STATS_FILE.open("r") as f:
                    d = json.load(f)
                    self.wins = d.get("wins", 0)
                    self.needed = d.get("needed", 10)
                    self.record = d.get("record", 0)
            except Exception: pass

    def save_stats(self):
        try:
            with STATS_FILE.open("w") as f:
                json.dump({"wins": self.wins, "record": self.record, "needed": self.needed}, f, indent=4)
        except Exception: pass

    def _notify(self):
        self.save_stats()
        data = self.get_data()
        for q in list(self.listeners): q.put(data)

    def add_win(self, amount=1):
        self.wins += amount
        while self.wins >= self.needed:
            self.wins -= self.needed
            self.needed += 10
        self._notify()

    def remove_win(self, amount=1):
        self.wins -= amount
        if self.wins < self.record: self.record = self.wins
        self._notify()

    def get_data(self):
        return {
            "wins": self.wins, 
            "needed": self.needed, 
            "record": self.record, 
            "win_color": "#ff4d4d" if self.wins < 0 else "white"
        }

win_manager_instance = WinManager()

# --- HTML template (browser source overlay) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { 
            background-color: #000000; color: white; 
            font-family: 'Consolas', monospace; margin: 0; 
            display: flex; flex-direction: column; 
            justify-content: center; align-items: center;
            height: 100vh; width: 100vw;
            overflow: hidden; user-select: none;
        }
        .container { 
            display: flex; align-items: center; 
            gap: 3vw; 
            font-size: 25vmin; /* Scaled up */
            font-weight: bold; 
            white-space: nowrap;
            line-height: 1;
        }
        .record-section { 
            margin-top: 1vh; 
            font-size: 10vmin; 
            color: #666; 
        }
    </style>
</head>
<body>
    <div class="container">
        <span>Wins:</span><span id="wins">0</span><span style="color: #333;">|</span><span id="needed">10</span>
    </div>
    <div class="record-section">Record: <span id="record">0</span></div>
    
    <script>
        const es = new EventSource("/stream");
        es.onmessage = (e) => {
            const d = JSON.parse(e.data);
            document.getElementById('wins').innerText = d.wins;
            document.getElementById('wins').style.color = d.win_color;
            document.getElementById('needed').innerText = d.needed;
            document.getElementById('record').innerText = d.record;
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
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/save_dims", methods=["POST"])
def save_dims():
    data = request.json
    with STATE_FILE.open("w") as f: json.dump(data, f)
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
            win_manager_instance.remove_win(1)
            print("\n[STATUS] [DEAD] Player died! Win removed.")

    except Exception as e:
        print(f"[ERROR] Webhook error: {e}")

    return {"status": "processed"}, 200

@app.route("/stream")
def stream():
    # Create a queue for this specific browser tab (SSE listener)
    q = Queue()
    win_manager_instance.listeners.append(q)
    
    def event_stream():
        try:
            # Send initial state immediately on connect
            yield f"data: {json.dumps(win_manager_instance.get_data())}\n\n"
            while True:
                result = q.get()  # Blocks until a new update arrives
                yield f"data: {json.dumps(result)}\n\n"
        finally:
            try: win_manager_instance.listeners.remove(q)
            except ValueError: pass
            
    return Response(event_stream(), mimetype="text/event-stream")

gui_hidden = args.gui_hidden

if __name__ == "__main__":
    size = load_win_size()
    server_thread = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False), daemon=True)

    server_thread.start()
    
    if not gui_hidden:
        # Create the window
        window = webview.create_window(
            'Win Counter Overlay', 
            f'http://127.0.0.1:{PORT}', 
            width=size['width'] + 30, 
            height=size['height'] + 30, 
            on_top=True,
            background_color='#000000'
        )
        webview.start()
    else:
        print("GUI hidden, running server only.")
        server_thread.join()