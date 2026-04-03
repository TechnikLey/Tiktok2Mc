# ==================================================
# overlaytxt - Text overlay plugin (green screen)
# ==================================================
# Displays short text notifications on a chroma-key
# green background, intended to be used as an OBS
# browser source. Text is sent via POST /display and
# pushed to clients via SSE.
# ==================================================

import webview
from flask import Flask, render_template_string, request, Response
import threading
import sys
import yaml
import json
from queue import Queue
from core import parse_args, register_plugin, AppConfig, get_root_dir, get_base_dir, get_base_file

# ==========================================
# Paths & configuration
# ==========================================

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
APP_PORT = 5005 

args = parse_args()

config = {}
DISPLAY_MODE = "overwrite"
FADE_IN = 500
FADE_OUT = 500

if CONFIG_FILE.exists():
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            APP_PORT = config.get("Overlaytxt", {}).get("Port", 5005)
            DISPLAY_MODE = config.get("Overlaytxt", {}).get("DisplayMode", "overwrite")
            FADE_IN = max(0, int(config.get("Overlaytxt", {}).get("FadeIn", 500)))
            FADE_OUT = max(0, int(config.get("Overlaytxt", {}).get("FadeOut", 500)))
    except Exception as e:
        print(f"[!] Config error: {e}")

OVERLAYTXT_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Overlaytxt",
        path=OVERLAYTXT_EXE_PATH,
        enable=config.get("Overlaytxt", {}).get("Enable", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

app = Flask(__name__)
listeners = []

# ==========================================
# Flask routes
# ==========================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, display_mode=DISPLAY_MODE, fade_in=FADE_IN, fade_out=FADE_OUT)

@app.route("/stream")
def stream():
    q = Queue()
    listeners.append(q)
    def event_stream():
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            try: listeners.remove(q)
            except ValueError: pass
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/display', methods=['POST'])
def display():
    content = request.json
    if not content:
        return "No data", 400
    data = {
        "title": content.get("title", ""),
        "subtitle": content.get("subtitle", ""),
        "duration": content.get("duration", 3)
    }
    for q in listeners:
        q.put(data)
    return "Angezeigt", 200

# ==========================================
# HTML template (green screen overlay)
# ==========================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            margin: 0; padding: 0; overflow: hidden;
            background-color: #00FF00; /* Chroma-key green */
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            text-shadow: 2px 2px 0px #000, -2px -2px 0px #000, 2px -2px 0px #000, -2px 2px 0px #000;
        }
        #container {
            text-align: center;
            opacity: 0;
            transition: opacity {{ fade_in }}ms ease-in-out;
        }
        h1 { font-size: 70px; margin: 0; color: #FFFFFF; }
        p { font-size: 30px; margin: 0; color: #FFFFFF; }
        .show { opacity: 1 !important; }
    </style>
</head>
<body>
    <div id="container">
        <h1 id="title"></h1>
        <p id="subtitle"></p>
    </div>

    <script>
        const DISPLAY_MODE = "{{ display_mode }}";
        const FADE_IN_MS = {{ fade_in }};
        const FADE_OUT_MS = {{ fade_out }};
        const eventSource = new EventSource("/stream");
        const container = document.getElementById('container');
        const titleEl = document.getElementById('title');
        const subtitleEl = document.getElementById('subtitle');

        let timeout = null;
        let showing = false;
        const messageQueue = [];

        function showMessage(data) {
            showing = true;
            titleEl.innerText = data.title;
            subtitleEl.innerText = data.subtitle;
            container.classList.add('show');

            clearTimeout(timeout);
            timeout = setTimeout(() => {
                container.style.transition = 'opacity ' + FADE_OUT_MS + 'ms ease-in-out';
                container.classList.remove('show');
                if (DISPLAY_MODE === "queue") {
                    setTimeout(() => {
                        showing = false;
                        container.style.transition = 'opacity ' + FADE_IN_MS + 'ms ease-in-out';
                        if (messageQueue.length > 0) {
                            showMessage(messageQueue.shift());
                        }
                    }, FADE_OUT_MS);
                } else {
                    showing = false;
                }
            }, data.duration * 1000);
        }

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (DISPLAY_MODE === "queue" && showing) {
                messageQueue.push(data);
            } else {
                showMessage(data);
            }
        };
    </script>
</body>
</html>
"""

gui_hidden = args.gui_hidden

def start_flask():
    app.run(host='127.0.0.1', port=APP_PORT, debug=False, use_reloader=False)

if __name__ == '__main__':
    server_thread = threading.Thread(target=start_flask, daemon=True)

    server_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            'Overlay', 
            f'http://127.0.0.1:{APP_PORT}', 
            transparent=False, # Disabled for green screen
            frameless=False, 
            on_top=True,
            width=800, # Wider for long text
            height=300,
            background_color='#00FF00'
        )
        webview.start()
    else:
        print("GUI hidden, running server only.")
        server_thread.join()