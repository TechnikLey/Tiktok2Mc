import sqlite3
import json
import threading
import time
import sys
import os
import urllib.request
from pathlib import Path
from core import parse_args, get_base_file, get_base_dir
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css
import logging
log = logging.getLogger(__name__)

BASE_DIR = get_base_dir()

PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR.parent / "data").resolve()
DB_PATH = (DATA_DIR / "channel_points.db").resolve()

args = parse_args()

cfg = load_plugin_config(PLUGIN_DIR)

PORT = cfg.get("port", 29195)
AWARD_AMOUNT = cfg.get("award_amount", 10)
AWARD_INTERVAL = cfg.get("award_interval_seconds", 60)
PING_TIMEOUT = cfg.get("ping_timeout_minutes", 10)
TOP_COUNT = cfg.get("leaderboard_count", 10)
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")

THEME = load_plugin_theme(cfg, "channel_points")
THEME_STYLE = theme_css(THEME)
BG_COLOR = THEME["background"]

API_BASE = "http://127.0.0.1:29185/api/v1"
PLUGIN_NAME = "channel-points"


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
            _push_state()
        except Exception as e:
            log.info(f"[CHANNEL POINTS] Award loop error: {e}")


def get_leaderboard_data():
    db = get_db()
    rows = db.execute(
        "SELECT user, points FROM users ORDER BY points DESC LIMIT ?", (TOP_COUNT,)
    ).fetchall()
    user_rows = db.execute("SELECT user, points FROM users").fetchall()
    db.close()
    return {
        "type": "leaderboard",
        "entries": [{"user": r[0], "points": r[1]} for r in rows],
        "user_points": {r[0]: r[1] for r in user_rows},
    }


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
    _push_state()
    return True


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
    _api_post(f"/plugins/{PLUGIN_NAME}/state", {"state": get_leaderboard_data()})


def command_polling_loop():
    while True:
        result = _api_get(f"/plugins/{PLUGIN_NAME}/commands")
        if result:
            for cmd_entry in result.get("commands", []):
                cmd = cmd_entry.get("command")
                args_data = cmd_entry.get("args", {})
                if cmd == "tiktok_event":
                    # Decoupled event handling — main system routes based on manifest
                    user = args_data.get("user", "")
                    if user:
                        ping_user(user)
                elif cmd == "get_points":
                    _push_state()
                elif cmd == "spend":
                    user = args_data.get("user", "")
                    amount = int(args_data.get("amount", 0))
                    action = args_data.get("action", "")
                    if user and amount > 0:
                        spend_points(user, amount, action)
        time.sleep(0.5)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
""" + THEME_STYLE + """
        body {
            margin: 0; padding: 20px;
            background: var(--background);
            color: var(--text);
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
            border-bottom: 2px solid var(--accent);
            font-size: 1em;
            color: var(--accent2);
        }
        td {
            padding: 6px 12px;
        }
        .pos { color: var(--accent); font-weight: bold; width: 30px; }
        .name { }
        .points { text-align: right; font-weight: bold; color: var(--accent3); }
        .top1 { font-size: 1.4em; }
        .top1 .points { font-size: 1.2em; color: var(--danger); }
        .top2 { font-size: 1.2em; }
        .top3 { font-size: 1.1em; }
    </style>
</head>
<body>
    <h2 style="margin:0 0 10px 0; color: var(--accent);">Leaderboard</h2>
    <table id="board">
        <thead><tr><th></th><th>Viewer</th><th style="text-align:right;">Points</th></tr></thead>
        <tbody id="tbody"></tbody>
    </table>
    <script>
        const tbody = document.getElementById('tbody');
        const evtSource = new EventSource('/api/v1/plugins/channel-points/stream');
        evtSource.onmessage = function(e) {
            const data = JSON.parse(e.data);
            if (data.type !== 'leaderboard') return;
            tbody.innerHTML = '';
            (data.entries || data.leaderboard || []).forEach(function(entry, i) {
                const tr = document.createElement('tr');
                if (i === 0) tr.className = 'top1';
                else if (i === 1) tr.className = 'top2';
                else if (i === 2) tr.className = 'top3';
                tr.innerHTML = '<td class="pos">#' + (i+1) + '</td><td class="name">' + escapeHtml(entry.user) + '</td><td class="points">' + entry.points + '</td>';
                tbody.appendChild(tr);
            });
        };
        function escapeHtml(s) {
            const div = document.createElement('div');
            div.appendChild(document.createTextNode(s));
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


def _register_overlay():
    _api_post(f"/plugins/{PLUGIN_NAME}/overlay-html", {"html": HTML_TEMPLATE})


gui_hidden = args.gui_hidden

if __name__ == "__main__":
    _register_overlay()

    award_thread = threading.Thread(target=award_loop, daemon=True)
    award_thread.start()

    poll_thread = threading.Thread(target=command_polling_loop, daemon=True)
    poll_thread.start()

    if not gui_hidden:
        import webview
        size = {"width": 400, "height": 600}
        window = webview.create_window(
            "Channel Points",
            f"http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay",
            width=size["width"],
            height=size["height"],
            on_top=True,
        )
        webview.start()
    else:
        log.info(f"[CHANNEL POINTS] Running. Leaderboard at http://127.0.0.1:29185/api/v1/plugins/{PLUGIN_NAME}/overlay")
        poll_thread.join()
