#!/usr/bin/env python3
# ==================================================
# likegoal - Like goal progress bar plugin
# ==================================================
# Displays a progress bar that fills up as the stream
# accumulates likes. Supports three goal modes based
# on the GoalMultiplier config value:
#   0 = reset (likes reset to 0 after reaching the goal)
#   1 = step  (goal increases by InitialGoal each time)
#   2+= multiply (goal is multiplied each time)
# All settings are read from config.yaml.
# Data is pushed to the overlay via SSE.
# ==================================================

import webview
import threading
import json
from queue import Queue
from flask import Flask, Response, request, jsonify
import sys
import yaml
from core import parse_args, AppConfig, get_base_dir, get_base_file, get_root_dir
from core.theme import load_plugin_theme, theme_css
from core.api.client import register_plugin
import logging
log = logging.getLogger(__name__)

# =========================
# Paths & configuration
# =========================
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()

CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()

args = parse_args()

cfg = {}

try:
    if not CONFIG_FILE.exists():
        log.info("Config not found")
        sys.exit(1)
    else:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        LIKE_GOAL_PORT = cfg.get("like_goal", {}).get("port", 29193)
        CUSTOM_TEXT = cfg.get("like_goal", {}).get("display_text", "Like Goal")
        INITIAL_GOAL = int(cfg.get("like_goal", {}).get("initial_goal", 100_000))
        GOAL_MULTIPLIER = int(cfg.get("like_goal", {}).get("goal_multiplier", 2))
        # Server host for binding (default: local only; set to "0.0.0.0" to allow network access)
        SERVER_HOST = cfg.get("server_host", "127.0.0.1")
except Exception as e:
    log.error(f"Config error: {e}")
    LIKE_GOAL_PORT = 29193
    CUSTOM_TEXT = "Like Goal"
    INITIAL_GOAL = 100_000
    GOAL_MULTIPLIER = 2
    SERVER_HOST = "127.0.0.1"

THEME = load_plugin_theme(cfg, "like_goal")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

LIKEGOAL_EXE_PATH = get_base_file()

# Register with central API
try:
    register_plugin(AppConfig(
        name="Like Goal",
        path=LIKEGOAL_EXE_PATH,
        enable=cfg.get("like_goal", {}).get("enabled", False),
        level=4,
        ics=True,
        port=LIKE_GOAL_PORT,
    ))
except Exception:
    log.warning("[LIKEGOAL] Could not register with central API")

# =========================
# Flask setup & like tracking
# =========================
app = Flask(__name__)

class LikeManager:
    """Tracks cumulative likes and computes progress toward the next goal."""
    def __init__(self, initial_goal=100_000, multiplier=2):
        self.likes = 0
        self.initial_goal = initial_goal
        self.multiplier = multiplier
        self.goal = initial_goal
        self.previous_goal = 0
        self.listeners = []
        self._lock = threading.Lock()

    def add_likes(self, amount=1):
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
        self._notify()

    def _notify(self):
        data = self.get_data()
        with self._lock:
            for q in list(self.listeners):
                q.put(data)

    def get_data(self):
        segment_size = self.goal - self.previous_goal
        progress_in_segment = self.likes - self.previous_goal
        percent = round((progress_in_segment / segment_size) * 100, 2) if segment_size > 0 else 0
        return {
            "likes": self.likes,
            "goal": self.goal,
            "percent": percent
        }

like_manager = LikeManager(initial_goal=max(INITIAL_GOAL, 1), multiplier=GOAL_MULTIPLIER)

# =========================
# HTML overlay template
# =========================
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
const evtSource = new EventSource(`/stream`);

evtSource.onmessage = function(event) {{
    try {{
        const data = JSON.parse(event.data);
        const bar = document.getElementById("bar");
        const text = document.getElementById("text");

        // Simple update without effect logic
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

# =========================
# Flask routes
# =========================
@app.route("/")
def index():
    return HTML_TEMPLATE

@app.route("/update_likes")
def update_likes():
    add_val = request.args.get("add", default=0, type=int)
    like_manager.add_likes(add_val)
    return jsonify(like_manager.get_data())

@app.route("/stream")
def stream():
    q = Queue()
    with like_manager._lock:
        like_manager.listeners.append(q)
    def event_stream():
        try:
            yield f"data: {json.dumps(like_manager.get_data())}\n\n"
            while True:
                try:
                    data = q.get(timeout=1)
                    yield f"data: {json.dumps(data)}\n\n"
                except Exception:
                    yield f"data: {json.dumps(like_manager.get_data())}\n\n"
        except GeneratorExit:
            pass
        finally:
            with like_manager._lock:
                try: like_manager.listeners.remove(q)
                except ValueError: pass
    return Response(event_stream(), mimetype="text/event-stream")

def run_flask():
    app.run(host=SERVER_HOST, port=LIKE_GOAL_PORT, threaded=True, debug=False, use_reloader=False)

gui_hidden = args.gui_hidden

# =========================
# Main execution
# =========================
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask, daemon=True)

    server_thread.start()

    if not gui_hidden:
        window = webview.create_window(
            "Like Goal Overlay",
            f"http://127.0.0.1:{LIKE_GOAL_PORT}",
            width=600,
            height=150,
            on_top=True,
            background_color=BG_COLOR
        )
        webview.start(debug=False)
    else:
        log.info("GUI hidden, running server only.")
        server_thread.join()