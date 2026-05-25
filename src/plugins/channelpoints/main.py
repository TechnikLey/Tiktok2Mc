#!/usr/bin/env python3
# ==================================================
# channelpoints - Viewer loyalty points plugin
# ==================================================
# Awards points to active viewers, lets them check
# their balance and spend points on rewards.
# ==================================================

import sqlite3
import json
import threading
import time
import sys
import yaml
from queue import Queue
from pathlib import Path
from flask import Flask, request, Response, jsonify
from core import parse_args, AppConfig, get_root_dir, get_base_file, get_base_dir
from python.registry import register_plugin

# --- Paths ---
BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
DATA_DIR = (ROOT_DIR / "data").resolve()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
CHANNEL_POINTS_DIR = (BASE_DIR / ".." / "data").resolve()
DB_PATH = (CHANNEL_POINTS_DIR / "channel_points.db").resolve()

args = parse_args()

# --- Configuration ---
try:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except Exception as e:
    print(f"[CHANNEL POINTS] Config load error: {e}")
    cfg = {}

cp_cfg = cfg.get("channel_points", {})
PORT = cp_cfg.get("port", 29195)
AWARD_AMOUNT = cp_cfg.get("award_amount", 10)
AWARD_INTERVAL = cp_cfg.get("award_interval_seconds", 60)
PING_TIMEOUT = cp_cfg.get("ping_timeout_minutes", 10)
TOP_COUNT = cp_cfg.get("leaderboard_count", 10)
SERVER_HOST = cfg.get("server_host", "127.0.0.1")
CP_EXE_PATH = get_base_file()

# --- Plugin self-registration ---
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="Channel Points",
        path=CP_EXE_PATH,
        enable=cp_cfg.get("enabled", True),
        level=4,
        ics=True,
        port=PORT,
    ))
    sys.exit(0)

# --- Database ---
def init_db():
    CHANNEL_POINTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user TEXT PRIMARY KEY,
            points INTEGER NOT NULL DEFAULT 0,
            last_seen REAL NOT NULL,
            total_earned INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            cost INTEGER NOT NULL,
            description TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect(str(DB_PATH))

# --- SSE clients ---
class OverlayClients:
    def __init__(self):
        self.listeners = []

    def add(self, q):
        self.listeners.append(q)

    def remove(self, q):
        try:
            self.listeners.remove(q)
        except ValueError:
            pass

    def notify(self, data):
        for q in self.listeners:
            q.put(data)

overlay_clients = OverlayClients()

# --- Award loop ---
def award_loop():
    while True:
        time.sleep(AWARD_INTERVAL)
        try:
            cutoff = time.time() - PING_TIMEOUT * 60
            db = get_db()
            db.execute(
                "UPDATE users SET points = points + ?, total_earned = total_earned + ? WHERE last_seen > ?",
                (AWARD_AMOUNT, AWARD_AMOUNT, cutoff),
            )
            db.commit()
            db.close()
            overlay_clients.notify(get_leaderboard_data())
        except Exception as e:
            print(f"[CHANNEL POINTS] Award loop error: {e}")

# --- Helpers ---
def get_leaderboard_data():
    db = get_db()
    rows = db.execute(
        "SELECT user, points FROM users ORDER BY points DESC LIMIT ?", (TOP_COUNT,)
    ).fetchall()
    db.close()
    return {"type": "leaderboard", "entries": [{"user": r[0], "points": r[1]} for r in rows]}

def get_user_points(user):
    db = get_db()
    row = db.execute("SELECT points FROM users WHERE user = ?", (user,)).fetchone()
    db.close()
    return row[0] if row else 0

def ping_user(user):
    db = get_db()
    db.execute(
        "INSERT INTO users (user, points, last_seen, total_earned) VALUES (?, 0, ?, 0) ON CONFLICT(user) DO UPDATE SET last_seen = ?",
        (user, time.time(), time.time()),
    )
    db.commit()
    db.close()

def spend_points(user, amount, action=""):
    db = get_db()
    row = db.execute("SELECT points FROM users WHERE user = ?", (user,)).fetchone()
    if not row or row[0] < amount:
        db.close()
        return False
    db.execute(
        "UPDATE users SET points = points - ? WHERE user = ?", (amount, user)
    )
    db.commit()
    db.close()
    overlay_clients.notify(get_leaderboard_data())
    return True

# --- Flask ---
app = Flask(__name__)

@app.route("/ping", methods=["POST"])
def handle_ping():
    user = (request.json or {}).get("user", "") if request.is_json else request.args.get("user", "")
    if user:
        ping_user(user)
    return "OK"

@app.route("/points", methods=["GET"])
def handle_points():
    user = request.args.get("user", "")
    if not user:
        return jsonify({"error": "Missing user"}), 400
    return jsonify({"user": user, "points": get_user_points(user)})

@app.route("/spend", methods=["POST"])
def handle_spend():
    data = request.json or {}
    user = data.get("user", "")
    amount = int(data.get("amount", 0))
    action = data.get("action", "")
    if not user or amount <= 0:
        return jsonify({"error": "Missing user or invalid amount"}), 400
    if spend_points(user, amount, action):
        return jsonify({"success": True, "user": user, "points": get_user_points(user)})
    return jsonify({"error": "Not enough points"}), 400

@app.route("/leaderboard", methods=["GET"])
def handle_leaderboard():
    return jsonify(get_leaderboard_data())

@app.route("/stream")
def stream():
    q = Queue()
    overlay_clients.add(q)
    q.put(get_leaderboard_data())

    def generate():
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        except GeneratorExit:
            overlay_clients.remove(q)

    return Response(generate(), mimetype="text/event-stream")

@app.route("/")
def index():
    return HTML_TEMPLATE

@app.route("/comment", methods=["POST"])
def handle_comment():
    user = request.args.get("user", "")
    text = request.args.get("text", "").strip().lower()
    if not user or not text:
        return "OK"

    parts = text.split()
    cmd = parts[0]

    if cmd == "points":
        pts = get_user_points(user)
        print(f"[CHANNEL POINTS] {user} has {pts} points")
        return jsonify({"user": user, "points": pts})

    if cmd == "redeem" and len(parts) >= 2:
        reward_name = parts[1]
        db = get_db()
        reward = db.execute("SELECT cost FROM rewards WHERE name = ?", (reward_name,)).fetchone()
        db.close()
        if not reward:
            print(f"[CHANNEL POINTS] Unknown reward '{reward_name}'")
            return jsonify({"error": "Unknown reward"}), 400
        if spend_points(user, reward[0], reward_name):
            print(f"[CHANNEL POINTS] {user} redeemed '{reward_name}' for {reward[0]} points")
            return jsonify({"success": True, "user": user, "reward": reward_name, "cost": reward[0]})
        return jsonify({"error": "Not enough points"}), 400

    return jsonify({"error": "Unknown command"}), 400


# --- HTML / CSS / JS (leaderboard overlay) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            margin: 0; padding: 20px;
            background: #000;
            color: #fff;
            font-family: 'Segoe UI', sans-serif;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 1.2em;
        }
        th {
            text-align: left;
            padding: 8px 12px;
            border-bottom: 2px solid #FFD700;
            font-size: 1em;
            color: #00BFFF;
        }
        td {
            padding: 6px 12px;
        }
        .pos { color: #FFD700; font-weight: bold; width: 30px; }
        .name { }
        .points { text-align: right; font-weight: bold; color: #40E0D0; }
        .top1 { font-size: 1.4em; }
        .top1 .points { font-size: 1.2em; color: #FF4500; }
        .top2 { font-size: 1.2em; }
        .top3 { font-size: 1.1em; }
    </style>
</head>
<body>
    <h2 style="margin:0 0 10px 0; color: #FFD700;">Leaderboard</h2>
    <table id="board">
        <thead><tr><th></th><th>Viewer</th><th style="text-align:right;">Points</th></tr></thead>
        <tbody id="tbody"></tbody>
    </table>
    <script>
        const tbody = document.getElementById('tbody');
        const evtSource = new EventSource('/stream');
        evtSource.onmessage = function(e) {
            const data = JSON.parse(e.data);
            if (data.type !== 'leaderboard') return;
            tbody.innerHTML = '';
            data.entries.forEach(function(entry, i) {
                const tr = document.createElement('tr');
                if (i === 0) tr.className = 'top1';
                else if (i === 1) tr.className = 'top2';
                else if (i === 2) tr.className = 'top3';
                tr.innerHTML = '<td class="pos">#' + (i+1) + '</td><td class="name">' + entry.user + '</td><td class="points">' + entry.points + '</td>';
                tbody.appendChild(tr);
            });
        };
    </script>
</body>
</html>
"""

# --- Start ---
gui_hidden = args.gui_hidden

if __name__ == "__main__":
    award_thread = threading.Thread(target=award_loop, daemon=True)
    award_thread.start()

    server_thread = threading.Thread(
        target=lambda: app.run(host=SERVER_HOST, port=PORT, threaded=True, debug=False, use_reloader=False),
        daemon=True
    )
    server_thread.start()

    if not gui_hidden:
        import webview
        size = {"width": 400, "height": 600}
        window = webview.create_window(
            "Channel Points",
            f"http://127.0.0.1:{PORT}",
            width=size["width"],
            height=size["height"],
            on_top=True,
        )
        webview.start()
    else:
        print(f"[CHANNEL POINTS] Running. Leaderboard at http://{SERVER_HOST}:{PORT}")
        server_thread.join()
