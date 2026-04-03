## GUI-Architektur: pywebview + Flask-Backend

### Concept: GUI vs DCS
- **DCS**: Reine HTTP-Server ohne GUI (Port-basiert)
- **GUI (ICS)**: Grafische Oberfläche in eigenem Fenster + HTTP-Backend
- Vorteil: Visuell intuitiv, einfache Konfiguration für Benutzer
- Technologie: **pywebview** (Electron-ähnlich) + **Flask** (Web-Framework)



```
┌─────────────────────────────────────┐
│   Streaming Tool GUI                │
│  ┌───────────────────────────────┐  │
│  │   pywebview Fenster           │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │   HTML/CSS/JavaScript   │  │  │
│  │  │   (Benutzeroberfläche)  │  │  │
│  │  └──────────┬──────────────┘  │  │
│  └─────────────┼─────────────────┘  │
│                │ (HTTP-Requests)    │
│  ┌─────────────▼──────────────────┐ │
│  │   Flask Server (Backend)       │ │
│  │  • /api/config (GET/POST)      │ │
│  │  • /api/status (GET)           │ │
│  │  • /api/save (POST)            │ │
│  │  • /stream (SSE)               │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Aufbau einer GUI-Plugin-Datei

**Dateistruktur eines GUI-Plugins:**
```
gui_plugin.py
├── Flask-App initialisieren
├── Route @app.route("/"): HTML-UI zurückgeben
├── Route @app.route("/api/config"): Konfiguration laden/speichern
├── Route @app.route("/stream"): Server-Sent Events (SSE)
└── main(): pywebview-Fenster öffnen
```

### Praktisches Beispiel: Einfaches GUI-Plugin

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
    <h2>Konfiguration</h2>
    <input type="text" id="config_input" placeholder="Wert eingeben">
    <button onclick="fetchConfig()">Laden</button>
    <button onclick="saveConfig()">Speichern</button>
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
    # Flask im Hintergrund starten
    from threading import Thread
    Thread(target=lambda: app.run(port=5001, debug=False, use_reloader=False), daemon=True).start()
    
    # pywebview-Fenster öffnen (zeigt localhost:5001)
    webview.create_window('GUI Plugin', 'http://localhost:5001')
    webview.start()

if __name__ == '__main__':
    main()
```

**Ablauf:**
1. pywebview öffnet ein Fenster
2. Fenster lädt HTML von `http://localhost:5001`
3. JavaScript sendet HTTP-Requests an Flask-Routes
4. Backend verarbeitet, speichert Config, sendet Antwort

### Kritische Aspekte

| Aspekt | Bedeutung | Beispiel |
|--------|-----------|----------|
| **Port Eindeutigkeit** | Jedes GUI-Plugin braucht eindeutigen Port | GUI: 5000, Timer: 7878, LikeGoal: 9797 |
| **Threading** | Flask muss in Thread laufen, damit Window nicht blockiert | `daemon=True` ist wichtig |
| **SSE für Live-Updates** | Server-Sent Events für kontinuierliche Daten | `/stream` für Like-Counter |
| **CORS** | Bei Browser-Quellen: `Access-Control-Allow-Origin: *` nötig | Streaming-Software Browser-Source |

### → Weiter zu [Kommunikation & DCS](./ch04-04-Communication-and-DCS.md)
