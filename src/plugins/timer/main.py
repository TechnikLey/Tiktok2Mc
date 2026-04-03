# ==================================================
# timer - Countdown timer overlay plugin
# ==================================================
# Displays a countdown timer that resets on player
# death/respawn. When the timer hits zero it sends
# a POST to the win counter to increment wins.
# ==================================================

import webview, threading, requests, json, sys, yaml, logging
from flask import Flask, request
from core import parse_args, register_plugin, AppConfig, get_root_dir, get_base_file, get_base_dir

# --- Paths ---
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

DATA_DIR = (ROOT_DIR / "data").resolve()
STATE_FILE = (DATA_DIR / "window_state_timer.json").resolve()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

logging.getLogger('werkzeug').setLevel(logging.INFO)

args = parse_args()

# --- Configuration ---
try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f: cfg = yaml.safe_load(f) or {}
except Exception: cfg = {}

TIMER_MINS = cfg.get("Timer", {}).get("StartTime", 10)
WIN_PORT = cfg.get("WinCounter", {}).get("WebServerPort", 8080)
WEB_PORT = cfg.get("MinecraftServerAPI", {}).get("WebServerPortTimer", 7878)
# Win counter URL for incrementing wins when timer expires
ADD_URL = f"http://localhost:{WIN_PORT}/add?amount=1"
TIMER_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Timer",
        path=TIMER_EXE_PATH,
        enable=cfg.get("Timer", {}).get("Enable", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f: return json.load(f)
        except Exception: pass
    return {"width": 400, "height": 200}

# --- API bridge (Python <-> JS via pywebview) ---
class API:
    def on_timer_end(self):
        # Sends a POST to the win counter when timer reaches zero
        print(f"[ACTION] Timer reached 0. Sending POST to {ADD_URL}")
        try:
            requests.post(ADD_URL, timeout=2)
        except Exception as e:
            print(f"[ERROR] Could not reach counter: {e}")

app = Flask(__name__)
window = None

@app.route("/save_dims", methods=["POST"])
def save_dims():
    with STATE_FILE.open("w") as f: json.dump(request.json, f)
    return "OK"

@app.route('/webhook', methods=['POST'])
def webhook():
    if window is None:
        print("[WARN] Webhook received but no GUI window active (gui_hidden mode).")
        return "OK"
    ev = request.json.get("event")
    if ev == "player_death":
        window.evaluate_js("resetTimer(); setPaused(true);")
    elif ev == "player_respawn":
        window.evaluate_js("setPaused(false);")
    return "OK"

@app.route("/")
def index(): return HTML_TEMPLATE

# --- HTML / CSS / JS (timer overlay) ---
HTML_TEMPLATE = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            background-color: #000000; color: #89CFF0; margin: 0;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; overflow: hidden; font-family: 'Segoe UI', sans-serif;
            -webkit-app-region: drag; user-select: none;
        }}
        #display {{
            font-size: 70vh; font-weight: bold;
            font-variant-numeric: tabular-nums; white-space: nowrap;
        }}
        
        .warning {{ color: #FFD700; }} /* Yellow */
        
        .blink {{ 
            color: #FF8C00; 
            /* 1s duration syncs with the timer tick */
            animation: syncFlash 1s infinite steps(1); 
        }}
        
        .critical {{ 
            color: #FF0000 !important; 
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
        let timeLeft = {TIMER_MINS} * 60, isPaused = false, isWaiting = false;
        const display = document.getElementById('display');

        function update() {{
            const m = Math.floor(timeLeft / 60), s = timeLeft % 60;
            display.innerText = `${{m.toString().padStart(2,'0')}}:${{s.toString().padStart(2,'0')}}`;
            
            display.classList.remove('warning', 'blink', 'critical');

            // Color & animation logic
            if (timeLeft === 0 || isWaiting) {{
                display.classList.add('critical'); // Stays red at 0
            }} else if (timeLeft <= 10) {{
                display.classList.add('critical');
            }} else if (timeLeft <= 30) {{
                display.classList.add('blink');
            }} else if (timeLeft <= 60) {{
                display.classList.add('warning');
            }}
        }}

        window.resetTimer = () => {{ 
            isWaiting = false;
            timeLeft = {TIMER_MINS} * 60; 
            update(); 
        }};

        window.setPaused = (val) => {{ isPaused = val; }};

        setInterval(() => {{
            if (!isPaused && !isWaiting && timeLeft > 0) {{
                timeLeft--; 
                update();
                
                if (timeLeft === 0) {{
                    isWaiting = true;
                    update(); // Switch to red immediately
                    
                    if (window.pywebview && window.pywebview.api) {{
                        window.pywebview.api.on_timer_end();
                    }}
                    
                    // 2-second wait at 00:00 (red)
                    setTimeout(() => {{ 
                        window.resetTimer(); 
                    }}, 2000);
                }}
            }}
        }}, 1000);

        // Save window size
        window.addEventListener('resize', () => {{
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {{
                fetch('/save_dims', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ width: window.outerWidth, height: window.outerHeight }})
                }});
            }}, 500);
        }});
        update();
    </script>
</body>
</html>
"""

gui_hidden = args.gui_hidden

if __name__ == '__main__':
    size = load_win_size()
    api = API()
    server_thread = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=WEB_PORT, threaded=True, debug=False, use_reloader=False), daemon=True)
    
    server_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            'Scalable Timer',
            f'http://127.0.0.1:{WEB_PORT}',
            width=size['width'], 
            height=size['height'], 
            on_top=True,
            js_api=api
        )
        webview.start()
    else:
        print("GUI hidden, running server only.")
        server_thread.join()