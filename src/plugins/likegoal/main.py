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
from core import parse_args, register_plugin, AppConfig, get_base_dir, get_base_file, get_root_dir

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
        print("Config not found")
        sys.exit(1)
    else:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        LIKE_GOAL_PORT = cfg.get("Gifts", {}).get("LIKE_GOAL_PORT", 9797)
        CUSTOM_TEXT = cfg.get("LikeGoal", {}).get("DisplayText", "Like Goal")
        INITIAL_GOAL = cfg.get("LikeGoal", {}).get("InitialGoal", 100_000)
        GOAL_MULTIPLIER = cfg.get("LikeGoal", {}).get("GoalMultiplier", 2)
except Exception as e:
    print(f"Config error: {e}")
    LIKE_GOAL_PORT = 9797
    CUSTOM_TEXT = "Like Goal"
    INITIAL_GOAL = 100_000
    GOAL_MULTIPLIER = 2

LIKEGOAL_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Like Goal",
        path=LIKEGOAL_EXE_PATH,
        enable=cfg.get("LikeGoal", {}).get("Enable", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

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

    def add_likes(self, amount=1):
        self.likes += amount
        while self.likes >= self.goal:
            if self.multiplier == 0:
                # Reset mode: start over from zero
                self.likes = 0
                self.goal = self.initial_goal
                self.previous_goal = 0
            elif self.multiplier == 1:
                # Step mode: increase goal by InitialGoal
                self.previous_goal = self.goal
                self.goal += self.initial_goal
            else:
                # Multiply mode: multiply goal
                self.previous_goal = self.goal
                self.goal = int(self.goal * self.multiplier)
        self._notify()

    def _notify(self):
        data = self.get_data()
        for q in self.listeners:
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

like_manager = LikeManager(initial_goal=INITIAL_GOAL, multiplier=GOAL_MULTIPLIER)

# =========================
# HTML overlay template
# =========================
HTML_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<style>
    :root {{
        /* RESTORED OLD COLORS */
        --neon-blue: #00f5ff;
        --neon-purple: #8a2be2;
        --neon-red: #ff4d4d;
        --bg-color: #050505;
    }}

    body {{
        margin: 0;
        padding: 0 20px;
        background: var(--bg-color);
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

    /* Small and subtle text */
    .milestone-command {{
        font-size: clamp(14px, 3vw, 20px);
        font-weight: 700;
        color: #fff;
        text-shadow: 0 0 10px var(--neon-red);
        margin-bottom: 10px;
        letter-spacing: 1px;
        opacity: 0.9;
    }}

    /* Keep the bar as the main focus */
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
        background: linear-gradient(90deg, var(--neon-blue), var(--neon-purple));
        /* Smooth width transition only, no animations */
        transition: width 0.5s ease-out;
        box-shadow: 0 0 20px var(--neon-blue);
    }}

    .text-overlay {{
        position: absolute;
        width: 100%;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: #fff;
        font-size: 22px;
        font-weight: 900;
        text-align: center;
        text-shadow: 2px 2px 4px #000;
        z-index: 10;
    }}

    /* REMOVED ALL ANIMATIONS AND GLITCHES */
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
const LIKE_GOAL_PORT = "{LIKE_GOAL_PORT}"; 
const evtSource = new EventSource(`http://127.0.0.1:${{LIKE_GOAL_PORT}}/stream`);

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
    like_manager.listeners.append(q)
    def event_stream():
        try:
            yield f"data: {json.dumps(like_manager.get_data())}\n\n"
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            try: like_manager.listeners.remove(q)
            except ValueError: pass
    return Response(event_stream(), mimetype="text/event-stream")

def run_flask():
    app.run(host="127.0.0.1", port=LIKE_GOAL_PORT, threaded=True)

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
            background_color="#050505"
        )
        webview.start(debug=False)
    else:
        print("GUI hidden, running server only.")
        server_thread.join()