# ==================================================
# gui.py - Web-based configuration & database GUI
# ==================================================
# Starts a Flask web server with a pywebview desktop
# window for browsing the TikTok gift database.
# ==================================================

import json
import threading
import time
import yaml
import webview
from flask import Flask, render_template, request
from core.paths import get_base_dir
from core.cli import parse_args

# --- Base directory ---
BASE_DIR = get_base_dir()

# --- Flask app setup ---
TEMPLATE_FOLDER = BASE_DIR / "templates"
STATIC_FOLDER = BASE_DIR / "static"
app = Flask(__name__, template_folder=TEMPLATE_FOLDER, static_folder=STATIC_FOLDER)

# --- Configuration ---
CONFIG_FILE = (BASE_DIR.parent / "config" / "config.yaml").resolve()
if not CONFIG_FILE.exists():
    raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}

GUI_PORT = config.get("GUI", {}).get("Port", 5000)
GUI_ENABLED = config.get("GUI", {}).get("Enable", False)

# --- Gift database file ---
DB_FILE = (BASE_DIR / "gifts.json").resolve()

# -------------------- ROUTES --------------------

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/db", methods=["GET", "POST"])
def db_page():
    results = []
    search_query = ""
    field = "name"

    if DB_FILE.exists():
        with DB_FILE.open("r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = []

    if request.method == "POST":
        search_query = request.form.get("search", "").strip()
        field = request.form.get("field", "name")

        if search_query:
            results = [
                entry for entry in db
                if search_query.lower() in str(entry.get(field, "")).lower()
            ]
        else:
            results = db

    return render_template(
        "db.html",
        results=results,
        search_query=search_query,
        field=field,
    )


def start_flask():
    app.run(host="127.0.0.1", port=GUI_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    time.sleep(1)

    gui_hidden = parse_args().gui_hidden

    if not gui_hidden:
        webview.create_window(
            "Server Config Editor",
            f"http://127.0.0.1:{GUI_PORT}",
            width=900,
            height=700,
        )
        webview.start()
    else:
        print("GUI hidden, server running in background.")
        flask_thread.join()

    print("GUI closed, program terminated.")