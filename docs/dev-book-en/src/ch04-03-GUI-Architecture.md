## GUI Architecture: pywebview + Flask Backend

### Concept: GUI vs DCS
- **DCS**: Pure HTTP servers without GUI (port-based)
- **GUI (ICS)**: Graphical interface in its own window + HTTP backend
- Advantage: Visually intuitive, easy configuration for users
- Technology: **pywebview** (Electron-like) + **Flask** (web framework)

### Architecture Diagram

```
┌─────────────────────────────────────┐
│   Streaming Tool GUI                │
│  ┌───────────────────────────────┐  │
│  │   pywebview Window            │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │   HTML/CSS/JavaScript   │  │  │
│  │  │   (User Interface)      │  │  │
│  │  └──────────┬──────────────┘  │  │
│  └─────────────┼─────────────────┘  │
│                │ (HTTP Requests)    │
│  ┌─────────────▼──────────────────┐ │
│  │   Flask Server (Backend)       │ │
│  │  • /api/config (GET/POST)      │ │
│  │  • /api/status (GET)           │ │
│  │  • /api/save (POST)            │ │
│  │  • /stream (SSE)               │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Structure of a GUI Plugin File

**File structure of a GUI plugin:**
```
gui_plugin.py
├── Initialize Flask app
├── Route @app.route("/"): Return HTML UI
├── Route @app.route("/api/config"): Load/save configuration
├── Route @app.route("/stream"): Server-Sent Events (SSE)
└── main(): Open pywebview window
```

### Practical Example: Simple GUI Plugin

`gui_example.py`:
```python
import os
import json
from flask import Flask, render_template_string, request
import webview

app = Flask(__name__)
CONFIG_FILE = "plugin_config.json"

HTML = """
<!DOCTYPE html>
<html><head>
    <title>GUI Plugin</title>
    <style>
        body { font-family: Arial; background: #222; color: #fff; padding: 20px; }
        button { padding: 10px 20px; background: #4CAF50; color: white; border: none; cursor: pointer; }
        input { padding: 8px; width: 200px; }
    </style>
</head>
<body>
    <h2>Configuration</h2>
    <input type="text" id="config_input" placeholder="Enter value">
    <button onclick="fetchConfig()">Load</button>
    <button onclick="saveConfig()">Save</button>
    <div id="output"></div>
    
    <script>
        function fetchConfig() {
            fetch('/api/config').then(r => r.json()).then(data => {
                document.getElementById('output').innerHTML = JSON.stringify(data);
                document.getElementById('config_input').value = data.setting || '';
            });
        }
        
        function saveConfig() {
            const value = document.getElementById('config_input').value;
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({setting: value})
            }).then(() => fetchConfig());
        }
        
        fetchConfig(); // Initial load
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/config", methods=['GET', 'POST'])
def config_handler():
    if request.method == 'GET':
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            return {"setting": ""}
    else:  # POST
        data = request.json
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
        return {"status": "saved"}

def main():
    # Start Flask in background
    from threading import Thread
    Thread(target=lambda: app.run(port=5001, debug=False, use_reloader=False), daemon=True).start()
    
    # Open pywebview window (shows localhost:5001)
    webview.create_window('GUI Plugin', 'http://localhost:5001')
    webview.start()

if __name__ == '__main__':
    main()
```

**Process:**
1. pywebview opens a window
2. Window loads HTML from `http://localhost:5001`
3. JavaScript sends HTTP requests to Flask routes
4. Backend processes, saves config, sends response

### Critical Aspects

| Aspect | Meaning | Example |
|--------|---------|---------|
| **Port uniqueness** | Every GUI plugin needs a unique port | GUI: 5000, Timer: 7878, LikeGoal: 9797 |
| **Threading** | Flask must run in a thread so the window doesn't block | `daemon=True` is important |
| **SSE for live updates** | Server-Sent Events for continuous data | `/stream` for like counters |
| **CORS** | For browser sources: `Access-Control-Allow-Origin: *` required | Streaming software browser source |

### → Continue to [Communication & DCS](./ch04-04-Communication-and-DCS.md)
