import webview
import threading
import sys
import json
import time
import urllib.request
import os
from pathlib import Path
from collections import defaultdict
from core import parse_args, get_base_file, get_base_dir
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)

BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
args = parse_args()

cfg = load_plugin_config(PLUGIN_DIR)

APP_PORT = cfg.get("port", 29186)
DISPLAY_MODE = cfg.get("display_mode", "overwrite")
FADE_IN = max(0, int(cfg.get("fade_in", 500)))
FADE_OUT = max(0, int(cfg.get("fade_out", 500)))
OVERLAYS_CONFIG = cfg.get("overlays", [])
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")

if not OVERLAYS_CONFIG:
    OVERLAYS_CONFIG = [{"name": "default"}]

THEME = load_plugin_theme(cfg, "overlay_text")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "overlay-text"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{{ theme_style }}
        body {{
            margin: 0; padding: 0; overflow: hidden;
            background-color: {% if chroma %}{{ chroma_color }}{% else %}transparent{% endif %};
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            color: var(--text);
            font-family: 'Segoe UI', Arial, sans-serif;
            text-shadow: 2px 2px 0px #000, -2px -2px 0px #000, 2px -2px 0px #000, -2px 2px 0px #000;
        }}
        #container {{
            text-align: center;
            opacity: 0;
            transition: opacity {{ fade_in }}ms ease-in-out;
        }}
        h1 {{ font-size: 70px; margin: 0; color: var(--text); }}
        p {{ font-size: 30px; margin: 0; color: var(--text); }}
        .show {{ opacity: 1 !important; }}
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
        const OVERLAY_NAME = "{{ overlay_name }}";

        const eventSource = new EventSource("/api/v1/plugins/overlay-text/stream");

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
            if (data.command !== "display") return;
            if (data.overlay_name && data.overlay_name !== OVERLAY_NAME) return;
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


def _render_html(overlay_name: str) -> str:
    return HTML_TEMPLATE.replace("{{ theme_style }}", THEME_STYLE) \
        .replace("{{ chroma_color }}", THEME["background"]) \
        .replace("{{ display_mode }}", str(DISPLAY_MODE)) \
        .replace("{{ fade_in }}", str(FADE_IN)) \
        .replace("{{ fade_out }}", str(FADE_OUT)) \
        .replace("{{ overlay_name }}", overlay_name)


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


def command_polling_loop():
    while True:
        result = _api_get(f"/plugins/{PLUGIN_NAME}/commands")
        if result:
            for cmd_entry in result.get("commands", []):
                cmd = cmd_entry.get("command")
                args = cmd_entry.get("args", {})
                if cmd == "display":
                    _api_post(f"/plugins/{PLUGIN_NAME}/state", {
                        "state": {
                            "command": "display",
                            "overlay_name": args.get("overlay_name", "default"),
                            "title": args.get("title", ""),
                            "subtitle": args.get("subtitle", ""),
                            "duration": args.get("duration", 3),
                        }
                    })
        time.sleep(0.5)


def _register_overlay():
    for idx, ov in enumerate(OVERLAYS_CONFIG):
        name = ov.get("name", f"overlay_{idx}")
        html = _render_html(name)
        _api_post(f"/plugins/{PLUGIN_NAME}/overlay-html", {"html": html})


gui_hidden = getattr(args, 'gui_hidden', False)

if __name__ == '__main__':
    _register_overlay()

    poll_thread = threading.Thread(target=command_polling_loop, daemon=True)
    poll_thread.start()

    if not gui_hidden:
        for idx, ov in enumerate(OVERLAYS_CONFIG):
            name = ov.get("name", f"overlay_{idx}")
            webview.create_window(
                f'Overlay: {name.upper()}',
                f'http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay?overlay={name}&chroma=1',
                transparent=False,
                frameless=False,
                on_top=True,
                width=800,
                height=300,
                x=100 + (idx * 50),
                y=100 + (idx * 50),
                background_color=BG_COLOR
            )
        webview.start()
    else:
        log.info(f"GUI hidden, overlay registered with Main API.")
        poll_thread.join()
