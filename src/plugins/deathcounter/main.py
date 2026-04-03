# ==================================================
# deathcounter - Death counter overlay plugin
# ==================================================
# Displays a real-time death counter as a browser
# source / pywebview overlay. Receives death events
# via a /webhook POST endpoint (from MinecraftServerAPI)
# and pushes updates to connected clients via SSE.
# ==================================================

import json, yaml, sys, threading, webview
from flask import Flask, Response, request, render_template_string
from flask_cors import CORS
from queue import Queue
from core import parse_args, register_plugin, AppConfig, get_base_dir, get_root_dir, get_base_file

# --- Paths & configuration ---
args = parse_args()

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
STATE_FILE = (ROOT_DIR / "data" / "window_state_death.json").resolve()
WEB_SERVER_PORT = 7979 

def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f: return json.load(f)
        except Exception: pass
    return {"width": 500, "height": 400}

cfg = {}

if CONFIG_FILE.exists():
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            WEB_SERVER_PORT = cfg.get("MinecraftServerAPI", {}).get("DEATHCOUNTER", 7979)
    except Exception as e:
        print(f"Config error: {e}")
        cfg = {}
else:
    print(f"Config file not found: {CONFIG_FILE}")
    sys.exit(1)

MINECRAFTSERVERAPI_ENABLED = cfg.get("MinecraftServerAPI", {}).get("Enable", True)
SERVERAPI_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Death Counter",
        path=SERVERAPI_EXE_PATH,
        enable=MINECRAFTSERVERAPI_ENABLED,
        level=4,
        ics=True
    ))
    sys.exit(0)

# --- Flask app & death tracking ---
app = Flask(__name__)
CORS(app)

class DeathManager:
    """Tracks the death count and notifies connected SSE listeners."""
    def __init__(self):
        self.count = 0
        self.listeners = []
    def add_death(self):
        self.count += 1
        for q in list(self.listeners): q.put(self.count)

death_manager = DeathManager()

# --- HTML template (served as browser source) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@900&display=swap');
        body, html { 
            background: #000000; margin: 0; padding: 0;
            width: 100%; height: 100%; display: flex;
            flex-direction: column; justify-content: center; align-items: center;
            overflow: hidden; font-family: 'Inter', sans-serif; color: #8ef3ff;
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
            const es = new EventSource("/stream");
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

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/save_dims", methods=["POST"])
def save_dims():
    with STATE_FILE.open("w") as f: json.dump(request.json, f)
    return "OK"

@app.route("/webhook", methods=["POST"])
def add():
    if request.json.get("event") == "player_death":
        death_manager.add_death()
    return "OK"

@app.route("/stream")
def stream():
    q = Queue(); death_manager.listeners.append(q)
    def event_stream():
        try:
            yield f"data: {json.dumps({'deaths': death_manager.count})}\n\n"
            while True: yield f"data: {json.dumps({'deaths': q.get()})}\n\n"
        finally:
            try: death_manager.listeners.remove(q)
            except ValueError: pass
    return Response(event_stream(), mimetype="text/event-stream")

gui_hidden = args.gui_hidden

if __name__ == "__main__":
    win = load_win_size()
    server_thread = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=WEB_SERVER_PORT, threaded=True, use_reloader=False), daemon=True)
    server_thread.start()

    if not gui_hidden:
        webview.create_window('Death Counter', f'http://127.0.0.1:{WEB_SERVER_PORT}', width=win['width'], height=win['height'], on_top=True, background_color='#000000')
        webview.start()
    else:
        print("GUI hidden, running server only.")
        server_thread.join()