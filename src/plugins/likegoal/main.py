import webview
import threading
import json
import sys
import os
import urllib.request
from queue import Queue
from pathlib import Path
from core import parse_args, get_base_dir, get_base_file
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)

BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
cfg = load_plugin_config(PLUGIN_DIR)

LIKE_GOAL_PORT = cfg.get("port", 29193)
CUSTOM_TEXT = cfg.get("display_text", "Like Goal")
INITIAL_GOAL = int(cfg.get("initial_goal", 100_000))
GOAL_MULTIPLIER = int(cfg.get("goal_multiplier", 2))
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")

THEME = load_plugin_theme(cfg, "like_goal")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "like-goal"


class LikeManager:
    def __init__(self, initial_goal=100_000, multiplier=2):
        self.likes = 0
        self.initial_goal = initial_goal
        self.multiplier = multiplier
        self.goal = initial_goal
        self.previous_goal = 0
        self._lock = threading.Lock()

    def add_likes(self, amount=1):
        with self._lock:
            self.likes += amount
            while self.likes >= self.goal:
                if self.multiplier == 0:
                    self.likes = 0
                    self.goal = self.initial_goal
                    self.previous_goal = 0
                elif self.multiplier == 1:
                    self.previous_goal = self.goal
                    self.goal += self.initial_goal
                else:
                    self.previous_goal = self.goal
                    self.goal = int(self.goal * self.multiplier)

    def get_data(self):
        with self._lock:
            segment_size = self.goal - self.previous_goal
            progress_in_segment = self.likes - self.previous_goal
            percent = round((progress_in_segment / segment_size) * 100, 2) if segment_size > 0 else 0
            return {
                "likes": self.likes,
                "goal": self.goal,
                "percent": percent
            }


like_manager = LikeManager(initial_goal=max(INITIAL_GOAL, 1), multiplier=GOAL_MULTIPLIER)


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
    _api_post(f"/plugins/{PLUGIN_NAME}/state", {"state": like_manager.get_data()})


def command_polling_loop():
    while True:
        result = _api_get(f"/plugins/{PLUGIN_NAME}/commands")
        if result:
            for cmd_entry in result.get("commands", []):
                cmd = cmd_entry.get("command")
                args_data = cmd_entry.get("args", {})
                if cmd == "update_likes":
                    add_val = int(args_data.get("add", 0))
                    if add_val > 0:
                        like_manager.add_likes(add_val)
                        _push_state()
        time.sleep(0.5)


HTML_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<style>
{THEME_STYLE}

    body {{
        margin: 0;
        padding: 0 20px;
        background: var(--background);
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        overflow: hidden;
    }}

    .container {{
        width: 100%;
        max-width: 900px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}

    .milestone-command {{
        font-size: clamp(14px, 3vw, 20px);
        font-weight: 700;
        color: var(--text);
        text-shadow: 0 0 10px var(--danger);
        margin-bottom: 10px;
        letter-spacing: 1px;
        opacity: 0.9;
    }}

    .bar-bg {{
        width: 100%;
        height: 60px;
        background: rgba(255, 255, 255, 0.05);
        border: 2px solid rgba(255, 255, 255, 0.1);
        position: relative;
        overflow: hidden;
        box-shadow: inset 0 0 20px #000;
    }}

    .bar-fill {{
        height: 100%;
        width: 0%;
        background: linear-gradient(90deg, var(--accent), var(--accent2));
        transition: width 0.5s ease-out;
        box-shadow: 0 0 20px var(--accent);
    }}

    .text-overlay {{
        position: absolute;
        width: 100%;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: var(--text);
        font-size: 22px;
        font-weight: 900;
        text-align: center;
        text-shadow: 2px 2px 4px #000;
        z-index: 10;
    }}
</style>
</head>
<body id="body">

<div class="container">
    <div class="milestone-command" id="command">{CUSTOM_TEXT}</div>
    <div class="bar-bg">
        <div class="bar-fill" id="bar"></div>
        <div class="text-overlay" id="text">0% (0 / {INITIAL_GOAL:,})</div>
    </div>
</div>

<script>
const evtSource = new EventSource(`/api/v1/plugins/like-goal/stream`);

evtSource.onmessage = function(event) {{
    try {{
        const data = JSON.parse(event.data);
        const bar = document.getElementById("bar");
        const text = document.getElementById("text");

        bar.style.width = data.percent + "%";
        text.innerText = `${{data.percent}}% (${{data.likes.toLocaleString()}} / ${{data.goal.toLocaleString()}})`;

        console.log("Update:", data.likes);
    }} catch (e) {{
        console.error("Error processing data:", e);
    }}
}};

evtSource.onerror = function() {{
    console.log("Connection lost... Reconnecting.");
}};
</script>
</body>
</html>
"""


def _register_overlay():
    _api_post(f"/plugins/{PLUGIN_NAME}/overlay-html", {"html": HTML_TEMPLATE})


args = parse_args()
gui_hidden = args.gui_hidden

if __name__ == "__main__":
    _register_overlay()

    poll_thread = threading.Thread(target=command_polling_loop, daemon=True)
    poll_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            "Like Goal Overlay",
            f"http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay",
            width=600,
            height=150,
            on_top=True,
            background_color=BG_COLOR
        )
        webview.start(debug=False)
    else:
        log.info("GUI hidden, running server only.")
        poll_thread.join()
