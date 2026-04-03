# GUI mit Flask + pywebview

###  GUI = Backend + Frontend

Plugins mit Benutzer-Interface brauchen zwei Layer:
1. **Flask-Backend (Python)** → HTTP-Server, Verarbeitung, Daten
2. **HTML/CSS/JS Frontend** → User-Interface, Visuals

**pywebview**: Öffnet ein Desktop-Fenster, der dann Flask-UI lädt.

### Architektur

```
┌───────────────────────────────┐
│ pywebview Fenster             │
│ ┌─────────────────────────┐   │
│ │ HTML/CSS/JavaScript     │   │
│ │ (User sieht das)        │   │
│ └──────┬──────────────────┘   │
│        │ (HTTP GET/POST)      │
│ ┌──────▼──────────────────┐   │
│ │ Flask Backend           │   │
│ │ /api/status             │   │
│ │ /webhook                │   │
│ │ (Datenverarbeitung)     │   │
│ └─────────────────────────┘   │
└───────────────────────────────┘
     ↓ localhost:PORT
```

### Minimal GUI: Setup (3 Schritte)

**Schritt 1: HTML als String definieren**
```python
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Mein Plugin</title>
    <style>
        body { background: #000; color: #0f0; font-size: 16px; }
        #counter { font-size: 48px; text-align: center; }
        button { padding: 10px 20px; margin: 10px; }
    </style>
</head>
<body>
    <h1>Counter: <span id="counter">0</span></h1>
    <button onclick="increment()">+1</button>
    <script>
        let count = 0;
        function increment() {
            count++;
            document.getElementById('counter').innerText = count;
            fetch('/api/count', { method: 'POST', 
                body: JSON.stringify({value: count}),
                headers: {'Content-Type': 'application/json'} });
        }
    </script>
</body>
</html>
"""
```

**Schritt 2: Flask Route + HTML**
```python
from flask import Flask, render_template_string

app = Flask(__name__)

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/count', methods=['POST'])
def update_count():
    data = request.json
    print(f"Counter: {data.get('value')}")
    return {"status": "ok"}
```

**Schritt 3: pywebview starten**
```python
import webview
import threading

def start_server():
    app.run(port=8001, debug=False)

# Flask im Thread starten
flask_thread = threading.Thread(target=start_server, daemon=True)
flask_thread.start()

# pywebview öffnet Fenster (zeigt localhost:8001)
webview.create_window('Mein Plugin', 'http://localhost:8001', width=600, height=400)
webview.start()
```

### Komplettes Beispiel: Counter-GUI

```python
from flask import Flask, request, render_template_string
import webview
import threading
import json
from pathlib import Path

app = Flask(__name__)
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

state = {"counter": 0}

HTML_TEMPLATE = """
<html><head>
    <title>Counter</title>
    <style>
        body { background: #222; color: #fff; font-family: Arial; text-align: center; padding: 20px; }
        #display { font-size: 72px; font-weight: bold; margin: 20px 0; }
        button { padding: 15px 30px; font-size: 18px; cursor: pointer; }
    </style>
</head><body>
    <h1>Counter GUI</h1>
    <div id="display">0</div>
    <button onclick="send('/inc')">Increment</button>
    <button onclick="send('/dec')">Decrement</button>
    <script>
        function send(path) {
            fetch(path).then(r => r.json()).then(d => {
                document.getElementById('display').innerText = d.value;
            });
        }
        setInterval(() => send('/get'), 500);  // Sync every 500ms
    </script>
</body></html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/get')
def get_value():
    return {"value": state["counter"]}

@app.route('/inc')
def increment():
    state["counter"] += 1
    save_state()
    return {"value": state["counter"]}

@app.route('/dec')
def decrement():
    state["counter"] = max(0, state["counter"] - 1)
    save_state()
    return {"value": state["counter"]}

def save_state():
    with open(DATA_DIR / "counter.json", "w") as f:
        json.dump(state, f)

if __name__ == '__main__':
    # Flask im Thread
    threading.Thread(target=lambda: app.run(port=8001), daemon=True).start()
    
    # pywebview
    webview.create_window('Counter', 'http://localhost:8001', width=400, height=300)
    webview.start()
```

```
┌─────────────────────────────┐
│     pywebview-Fenster       │
│  (HTML/CSS/JS - Frontend)   │
└──────────────┬──────────────┘
               │ (JavaScript Bridge)
               │
┌──────────────▼──────────────┐
│  Flask oder FastAPI         │
│  (Python - Backend)         │
└─────────────────────────────┘
```

## Einfaches Fenster öffnen

```python
import webview
import threading

HTML = """
<html>
    <body style="background: #000; color: #0f0; font-size: 24px;">
        <h1>Mein Plugin</h1>
        <p>Dies ist eine einfache GUI</p>
    </body>
</html>
"""

def start_gui():
    webview.create_window('Mein Plugin', html=HTML)
    webview.start()

# Im Hauptprogramm:
gui_thread = threading.Thread(target=start_gui, daemon=True)
gui_thread.start()
```

## Flask + pywebview kombinieren

Die meisten Plugins kombinieren **Flask** (für REST-Endpoints) mit **pywebview** (für die GUI). Das Frontend und Backend können dann kommunizieren:

```python
from flask import Flask, render_template_string
import webview
import threading

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { background: #000; color: #0f0; margin: 0; }
        #counter { font-size: 72px; text-align: center; }
        button { padding: 10px 20px; margin: 10px; }
    </style>
</head>
<body>
    <h1>Counter</h1>
    <div id="counter">0</div>
    <button onclick="add()">+1</button>
    <script>
        let count = 0;
        function add() {
            count++;
            document.getElementById('counter').innerText = count;
            fetch('/api/count?value=' + count);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/count')
def update_count():
    value = request.args.get('value')
    # Speichere oder verarbeite den neuen Wert
    return "OK"

def start_flask():
    app.run(host='127.0.0.1', port=7777, debug=False)

def start_gui():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    webview.create_window('Counter Plugin', 'http://127.0.0.1:7777')
    webview.start()

# Im Hauptprogramm:
gui_thread = threading.Thread(target=start_gui, daemon=True)
gui_thread.start()
```

## Praktisches Beispiel: DeathCounter

Der DeathCounter zeigt die Anzahl der Tode in Echtzeit an. Das funktioniert übers **Server-Sent Events (SSE)**:

```python
@app.route('/stream')
def stream():
    def event_stream():
        while True:
            yield f'data: {{"deaths": {death_manager.count}}}\n\n'
            time.sleep(0.5)
    
    return Response(stream(), mimetype='text/event-stream')
```

Das Frontend abonniert den Stream:

```javascript
const es = new EventSource("/stream");
es.onmessage = (e) => {
    const deaths = JSON.parse(e.data).deaths;
    document.getElementById('counter').innerText = deaths;
};
```

So wird die GUI automatisch aktualisiert, wenn sich die Zahl ändert.

## Fenster-Position und -Größe speichern

Nutzer mögen es, wenn ihre Fenster wieder an der gleichen Position entstehen:

```python
import json

STATE_FILE = DATA_DIR / "window_state.json"

def load_win_size():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r") as f:
                return json.load(f)
        except:
            pass
    return {"x": 100, "y": 100, "width": 600, "height": 400}

@app.route('/save_dims', methods=['POST'])
def save_dims():
    data = request.json
    with STATE_FILE.open("w") as f:
        json.dump(data, f)
    return "OK"
```

Das Frontend speichert nach jeder Größenänderung:

```javascript
window.addEventListener('resize', () => {
    fetch('/save_dims', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            width: window.innerWidth,
            height: window.innerHeight
        })
    });
});
```

## Python ↔ JavaScript Kommunikation

Mit pywebview kannst du auch direkt Python-Funktionen aus JavaScript aufrufen:

```python
api = webview.api

class API:
    def set_brightness(self, level):
        print(f"Helligkeit auf {level} gesetzt")
        return f"OK: {level}"

webview.create_window('Plugin', 'index.html', js_api=API())
```

Im Frontend:

```javascript
async function changeBrightness() {
    const result = await pywebview.api.set_brightness(50);
    console.log(result); // "OK: 50"
}
```

## CSS für Streaming-Overlays

Wenn dein Plugin in OBS eingebettet wird (Browser-Source), brauchst du spezielle CSS:

```css
/* Transparenter Background */
body {
    background: transparent !important;
    margin: 0;
    padding: 0;
}

/* Font für hohe Auflösungen */
* {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
}

/* Keine Rahmen/Scrollbars */
::-webkit-scrollbar {
    display: none;
}
```

---

## Zusammenfassung

- **pywebview:** GUI mit HTML/CSS/JavaScript + Python
- **Flask:** REST-API für Frontend-Backend-Kommunikation
- **Server-Sent Events:** Für Echtzeit-Updates vom Backend
- **State persistieren:** Fenster-Position und -Größe speichern
- **Threading:** GUI läuft in seperatem Thread

**Nächstes Kapitel:** [Plugins kommunizieren miteinander](./ch02-05-inter-plugin-communication.md)
