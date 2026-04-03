# Events empfangen: Webhook-System

###  Event-Datenfluss

Wenn in Minecraft etwas passiert (Spieler stirbt, Login, etc.), sendet das Spiel-Plugin einen **HTTP-POST-Request** an dein Plugin. Das nennt sich **Webhook**.

**Flow:**
```
Minecraft Event (player_death)
        ↓
Minecraft-Plugin prüft configServerAPI.yml
        ↓
Sendet HTTP-POST → http://localhost:PORT/webhook
        ↓
Dein Plugin (@app.route("/webhook")) empfängt
        ↓
Dein Plugin verarbeitet & reagiert
```

### Verfügbare Events

> [!NOTE]
> Eine **Komplette Liste aller Events** findest du in der `configServerAPI.yml` im Projekt.
Hier ein paar Beispiele:

* `player_death`
* `player_respawn`
* `player_join`
* `player_quit`
* `block_break`
* `entity_death`

### Webhook-Implementation: 3 Schritte

**1. Flask Server starten (im Main Thread)**
```python
from flask import Flask, request
app = Flask(__name__)

def start_server():
    app.run(host="127.0.0.1", port=8001, debug=False, threaded=True)

import threading
srv = threading.Thread(target=start_server, daemon=True)
srv.start()
```

**2. /webhook Endpoint definieren**
```python
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        data = request.json
        event_type = data.get("event")
        
        if event_type == "player_death":
            print(f"Spieler gestorben: {data.get('player')}")
        elif event_type == "block_break":
            print(f"Block abgebaut: {data.get('block')}")
        
        return {"status": "ok"}, 200
    except Exception as e:
        print(f"Webhook-Fehler: {e}")
        return {"status": "error"}, 500
```

**3. In config.yaml registrieren**
```yaml
MyPlugin:
  Enable: true
  WebServerPort: 8001
```

und in der `configServerAPI.yml`:
```yaml
  urls:
    - "http://localhost:7777/webhook"
    - "http://localhost:7878/webhook"
    - "http://localhost:7979/webhook"
    - "http://localhost:8080/webhook"
    - "http://localhost:8001/webhook" # Dein webhook
```

### Komplettes Beispiel: DeathCounter

```python
from flask import Flask, request
import json
from pathlib import Path

app = Flask(__name__)
DATA_DIR = Path(".") / "data"
DEATHS_FILE = DATA_DIR / "deathcount.json"

# Zähler laden
if DEATHS_FILE.exists():
    with open(DEATHS_FILE) as f:
        death_count = json.load(f).get("count", 0)
else:
    death_count = 0

@app.route("/")
def index():
    return f"<h1>Tod-Zähler: {death_count}</h1>"

@app.route("/webhook", methods=['POST'])
def webhook():
    global death_count
    data = request.json
    
    if data.get("event") == "player_death":
        death_count += 1
        # Speichern
        with open(DEATHS_FILE, "w") as f:
            json.dump({"count": death_count}, f)
        print(f"[+] Tode: {death_count}")
    
    return {"status": "ok"}, 200

if __name__ == '__main__':
    import threading
    threading.Thread(target=lambda: app.run(port=8001), daemon=True).start()
    input("Server läuft. Enter zum Stoppen...")
```

## Webhook in dein Plugin integrieren

Um Webhooks zu empfangen, brauchst du einen HTTP-Server in deinem Plugin. **Flask** ist dafür perfekt geeignet:

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    event_data = request.json
    event_type = event_data.get("event")
    
    if event_type == "player_death":
        print("Spieler ist gestorben!")
    elif event_type == "player_respawn":
        print("Spieler ist respawnt!")
    
    return "OK", 200
```

Das ist das Minimum. Dein Plugin muss:
1. **Flask starten** und auf Port X lauschen
2. **Den `/webhook` Endpoint** bereitstellen
3. **Den POST-Request verarbeiten** und reagieren

### Praktisches Beispiel: Der Timer

Der Timer-Plugin reagiert auf zwei Events:

```python
@app.route('/webhook', methods=['POST'])
def webhook():
    ev = request.json.get("event")
    if ev == "player_death":
        window.evaluate_js("resetTimer(); setPaused(true);")
    elif ev == "player_respawn":
        window.evaluate_js("setPaused(false);")
    return "OK"
```

Wenn ein Spieler stirbt:
- Timer wird zurückgesetzt
- Timer wird pausiert

Wenn ein Spieler respawnt:
- Timer läuft weiter

## Die Event-Payload verstehen

Wenn ein Event ankommt, sieht der Request so aus:

```json
{
    "load_type": "INGAME_GAMEPLAY",
    "event": "player_death",
    "message": "Player died from fall damage"
}
```

Je nach `load_type` kannst du unterschiedliche Verhaltensweisen programmieren:

- **`INGAME_GAMEPLAY`**: Das Event ist vom laufenden Spiel
- **`STARTUP`**: Das Event ist beim Server-Start
- Andere: siehe `configServerAPI.yml`

## Webhook-URL konfigurieren

Dein Plugin muss in der `config.yaml` eine Port-Einstellung haben. Die `configServerAPI.yml` ruft dann diese URL auf:

```yaml
# config.yaml
MinecraftServerAPI:
  WebServerPortDeathCounter: 7979
  WebServerPortTimer: 7878
```

Die Webhook-URLs werden dann so konfiguriert:

```yaml
# configServerAPI.yml
webhooks:
  urls:
    - "http://localhost:7979/webhook"    # DeathCounter
    - "http://localhost:7878/webhook"    # Timer
```

> [!IMPORTANT]
> Der Port muss eindeutig sein! Kein anderes Plugin darf den gleichen Port nutzen.

## Threading: Flask im Hintergrund starten

Ein wichtiger Punkt: Dein Plugin läuft nach der Registrierung weiter. Wenn du Flask direkt mit `app.run()` aufrufst, blockiert das alles danach.

Die Lösung: Flask in einem **Thread** starten:

```python
import threading

def start_flask_server():
    app.run(host='127.0.0.1', port=7878, debug=False)

# Im Hauptprogramm:
flask_thread = threading.Thread(target=start_flask_server, daemon=True)
flask_thread.start()

# Dein restlicher Code läuft parallel weiter...
```

Mit `daemon=True` wird der Thread automatisch beendet, wenn dein Plugin beendet wird.

## Fehlerbehandlung

Nicht immer funktioniert alles. Ein paar wichtige Punkte:

1. **Webhook funktioniert nicht?**
   - Prüf, dass dein Port in `config.yaml` eingestellt ist
   - Prüf, dass die URL in `configServerAPI.yml` korrekt ist
   - Schau in deine Log-Datei

2. **Port schon in Verwendung?**
   - Wähle einen anderen Port oder beende das andere Programm

---

## Zusammenfassung

- Webhooks sind HTTP POST-Requests von Minecraft zu deinem Plugin
- Flask macht die Implementierung einfach
- Der `/webhook` Endpoint verarbeitet eingehende Events
- Der Port muss in `config.yaml` und `configServerAPI.yml` synchronisiert sein
- Threading ist wichtig, damit der Flask-Server nicht alles blockiert

**Nächstes Kapitel:** [Konfiguration und Datenspeicherung](./ch02-03-configuration-and-data-storage.md)
