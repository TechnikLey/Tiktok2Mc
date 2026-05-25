#!/usr/bin/env python3
# ==================================================
# overlaytxt - Text overlay plugin (green screen)
# ==================================================

import webview
from flask import Flask, render_template_string, request, Response
import threading
import sys
import yaml
import json
from queue import Queue
from collections import defaultdict
from core import parse_args, AppConfig, get_root_dir, get_base_dir, get_base_file
from core.theme import load_plugin_theme, theme_css
from python.registry import register_plugin
import logging
log = logging.getLogger(__name__)

# ==========================================
# Paths & configuration
# ==========================================

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

args = parse_args()
full_config = {}

# Standardwerte
APP_PORT = 29186 
DISPLAY_MODE = "overwrite"
FADE_IN = 500
FADE_OUT = 500
OVERLAYS_CONFIG = []
# Server host for binding (default: local only; set to "0.0.0.0" to allow network access)
SERVER_HOST = "127.0.0.1"

if CONFIG_FILE.exists():
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            full_config = yaml.safe_load(f)
            # Fokus auf den Unterpunkt Overlaytxt
            conf = full_config.get("overlay_text", {})
            
            APP_PORT = conf.get("port", 29186)
            DISPLAY_MODE = conf.get("display_mode", "overwrite")
            FADE_IN = max(0, int(conf.get("fade_in", 500)))
            FADE_OUT = max(0, int(conf.get("fade_out", 500)))
            
            # NEU: Liste wird jetzt hier gesucht
            OVERLAYS_CONFIG = conf.get("overlays", [])
            SERVER_HOST = full_config.get("server_host", "127.0.0.1")
            
    except Exception as e:
        log.info(f"[!] Config error: {e}")

if not OVERLAYS_CONFIG:
    OVERLAYS_CONFIG = [{"name": "default"}]

THEME = load_plugin_theme(full_config, "overlay_text")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

OVERLAYTXT_EXE_PATH = get_base_file()

register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Overlaytxt",
        path=OVERLAYTXT_EXE_PATH,
        enable=full_config.get("overlay_text", {}).get("enabled", True),
        level=4,
        ics=True,
        port=APP_PORT,
    ))
    sys.exit(0)

app = Flask(__name__)

listeners = defaultdict(list)

# ==========================================
# Flask routes
# ==========================================

@app.route('/')
def index():
    overlay_name = request.args.get('overlay', 'default')
    chroma = request.args.get('chroma', '0') == '1'
    return render_template_string(
        HTML_TEMPLATE, 
        display_mode=DISPLAY_MODE, 
        fade_in=FADE_IN, 
        fade_out=FADE_OUT, 
        chroma=chroma,
        overlay_name=overlay_name,
        theme_style=THEME_STYLE,
        chroma_color=THEME["background"]
    )

@app.route("/stream/<overlay_name>")
def stream(overlay_name):
    q = Queue()
    listeners[overlay_name].append(q)
    def event_stream():
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            if q in listeners[overlay_name]:
                listeners[overlay_name].remove(q)
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/display/<overlay_name>', methods=['POST'])
def display(overlay_name):
    content = request.json
    if not content:
        return "No data", 400
    
    data = {
        "title": content.get("title", ""),
        "subtitle": content.get("subtitle", ""),
        "duration": content.get("duration", 3)
    }
    
    for q in listeners[overlay_name]:
        q.put(data)
        
    return f"Angezeigt auf {overlay_name}", 200

# ==========================================
# HTML template (green screen overlay)
# ==========================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{{ theme_style }}
        body {
            margin: 0; padding: 0; overflow: hidden;
            background-color: {% if chroma %}{{ chroma_color }}{% else %}transparent{% endif %};
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            color: var(--text);
            font-family: 'Segoe UI', Arial, sans-serif;
            text-shadow: 2px 2px 0px #000, -2px -2px 0px #000, 2px -2px 0px #000, -2px 2px 0px #000;
        }
        #container {
            text-align: center;
            opacity: 0;
            transition: opacity {{ fade_in }}ms ease-in-out;
        }
        h1 { font-size: 70px; margin: 0; color: var(--text); }
        p { font-size: 30px; margin: 0; color: var(--text); }
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
        
        // Dynamischer Stream-Endpunkt basierend auf dem Namen
        const eventSource = new EventSource("/stream/{{ overlay_name }}");
        
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

gui_hidden = getattr(args, 'gui_hidden', False)

def start_flask():
    app.run(host=SERVER_HOST, port=APP_PORT, debug=False, use_reloader=False)

if __name__ == '__main__':
    server_thread = threading.Thread(target=start_flask, daemon=True)
    server_thread.start()

    if not gui_hidden:
        for idx, ov in enumerate(OVERLAYS_CONFIG):
            name = ov.get("name", f"overlay_{idx}")
            webview.create_window(
                f'Overlay: {name.upper()}', 
                f'http://127.0.0.1:{APP_PORT}/?overlay={name}&chroma=1', 
                transparent=False, 
                frameless=False, 
                on_top=True,
                width=800, 
                height=300,
                x=100 + (idx * 50), # Leicht versetzt auf dem Bildschirm
                y=100 + (idx * 50),
                background_color=BG_COLOR
            )
        webview.start()
    else:
        log.info(f"GUI hidden, running server on port {APP_PORT} only.")
        server_thread.join()