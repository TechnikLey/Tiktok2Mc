# Debugging & Troubleshooting

Du hast dein Plugin geschrieben, aber es funktioniert nicht wie erwartet? Hier lernst du, Fehler zu finden, zu verstehen und zu beheben.

---

## Arten von Fehlern

Bevor wir debuggen, sollten wir wissen, welche Fehlerklassen es gibt:

| Fehlertyp | Symptom | Beispiel |
|-----------|---------|---------|
| **Syntax-Fehler** | Programm startet gar nicht | `def foo(` - fehlende Klammer |
| **Import-Fehler** | `ModuleNotFoundError` | Abhängigkeit nicht installiert |
| **Runtime-Fehler** | Programm crasht während Ausführung | Division durch 0 |
| **Logic-Fehler** | Programm läuft, macht aber Falsches | `if x = 5:` statt `if x == 5:` |
| **Configuration-Fehler** | Settings sind falsch | `config.yaml` hat ungültige YAML |

---

## Werkzeug 1: Logs (Das wichtigste!)

### Wo sind die Logs?

```
build/release/logs/
├── debug.log          # Allgemeine Debug-Logs
├── error.log          # Nur Fehler
├── plugin_timer.log   # Plugin-spezifische Logs
└── ...
```

### Log-Levels verstehen

In der `config.yaml`:

```yaml
log_level: 2
```

> [!TIP]
> Für Entwicklung Level auf `4` setzen:

```yaml
log_level: 4
```

### Log-Output in deinem Plugin

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug-Info für Entwickler")
logger.info("Allgemeine Information")
logger.warning("Warnung – könnte Probleme verursachen")
logger.error("Ein Fehler ist aufgetreten")
logger.critical("KRITISCHER Fehler – Programm might crashed")
```

**Beispiel:**

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info(f"Webhook empfangen: {request.json}")
    
    try:
        process_event(request.json)
        logger.info("Event erfolgreich verarbeitet")
    except Exception as e:
        logger.error(f"Fehler im Event-Processing: {e}", exc_info=True)
        return {"error": str(e)}, 500
```

---

## Werkzeug 2: Print-Debugging

Für schnelle Tests kannst du auch `print()` nutzen:

```python
def on_gift(event):
    print(f"[DEBUG] Gift empfangen: {event.gift.name}")
    print(f"[DEBUG] User: {event.user.nickname}")
    print(f"[DEBUG] Count: {event.repeat_count}")
```

**Aber Achtung:** `print()` ist **nicht** produktionsreif. Nutze `logging` für echte Anwendungen.

---

## Werkzeug 3: Try-Except Blöcke

Fehler abfangen und verstehen:

```python
try:
    result = 10 / number  # Könnte Division-by-Zero sein
except ZeroDivisionError:
    print("FEHLER: Division durch 0!")
    return None
except Exception as e:
    print(f"Unerwarteter Fehler: {e}")
    return None
```

**Mit traceback() für Details:**

```python
import traceback

try:
    process_data(data)
except Exception as e:
    print(f"FEHLER: {e}")
    traceback.print_exc()  # Zeigt den kompletten Error-Stack
    logger.error(f"Fehler: {e}", exc_info=True)
```

---

## Werkzeug 4: Der Debugger (VS Code)

Visual Studio Code hat einen **eingebauten Debugger**:

### Breakpoints setzen

1. Öffne deine Python-Datei
2. Klick links neben die Zeile → roter Punkt (Breakpoint)
3. Starte das Programm mit `F5` (Debug-Modus)
4. Wenn die Zeile erreicht wird → Programm pausiert
5. Inspiziere Variablen, steps durch den Code

### Debug-Controls

- `F10` – Nächste Zeile (Step Over)
- `F11` – In Funktion gehen (Step Into)
- `Shift+F11` – Aus Funktion gehen
- `F5` – Weiter bis nächster Breakpoint
- `Shift+F5` – Debuggen beenden

### Watch-Variablen

Rechts im Debug-Panel:

```
VARIABLES
├─ request
│   ├─ method: "POST"
│   ├─ json: {...}
│   └─ ...
├─ event
│   ├─ gift: {...}
│   └─ ...
```

Du kannst hier Variablen inspizieren, ohne zu tippen!

---

## Häufige Fehler & Lösungen

### 1. "ModuleNotFoundError: No module named 'TikTokLive'"

**Ursache:** Abhängigkeit nicht installiert.

**Lösung:**
```bash
pip install -r requirements.txt
```

oder

```bash
pip install TikTokLive Flask pywebview pyyaml
```

---

### 2. "Config-Fehler bei Laden"

**Ursache:** `configuration.yaml` ist keine gültige YAML.

**Test:**
```bash
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

Wenn Fehler → YAML-Syntax überprüfen (Einrückung, Doppelpunkte, etc.)

---

### 3. "Port schon in Verwendung"

**Fehler:** `Address already in use :8080`

**Ursache:** Ein anderes Programm nutzt den Port.

**Lösung:**

**Windows:**
```powershell
netstat -ano | findstr :8080
taskkill /PID <pid_nummer> /F
```

**macOS/Linux:**
```bash
lsof -i :8080
kill -9 <pid>
```

**Oder:** Port in `config.yaml` ändern:

```yaml
Timer:
  WebServerPort: 8081  # Statt 8080
```

---

### 4. "TikTok-Verbindung schlägt fehl"

**Fehler:** Client kann sich nicht mit TikTok verbinden.

**Diagnostik:**

```python
# In main.py testen
client = TikTokLiveClient(unique_id="mein_username")
try:
    asyncio.run(client.connect())
    print("✓ Verbindung erfolgreich!")
except Exception as e:
    print(f"✗ Verbindung fehlgeschlagen: {e}")
```

**Häufige Ursachen:**
- TikTok-User existiert nicht (falsch geschrieben)
- Internet down
- TikTok API hat sich geändert

---

### 5. "Plugin wird nicht geladen"

**Fehler:** Plugin ist in `src/plugins/` aber wird nicht verwendet.

**Debugging:**

1. **Check:** Plugin in `PLUGIN_REGISTRY` registriert?
   ```python
   # In start.py / registry.py
   {"name": "MyPlugin", "path": ..., "enable": True, ...}
   ```

2. **Check:** Plugin hat `main.py`?
   ```
   src/plugins/my_plugin/
   ├── main.py       # Muss existieren!
   ├── README.md
   └── version.txt
   ```

3. **Check:** Plugin kann importieren?
   ```bash
   python src/plugins/my_plugin/main.py --register-only
   ```
   Wenn Fehler → Importe überprüfen

---

### 6. "Webhook wird nicht empfangen"

**Fehler:** Minecraft sendet Event, aber dein Plugin empfängt es nicht.

**Debugging:**

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info(f"Webhook empfangen: {request.json}")
    print(f"[WEBHOOK] {request.json}")  # Zusätzlich printen
    return {"success": True}, 200
```

**Checks:**

1. **Flask läuft?** 
   ```bash
   curl http://localhost:7878/webhook -X POST -d "{}"
   ```

2. **Firewall erlaubt Port?** Port muss offen sein.

3. **Config stimmt?** Port in `config.yaml` muss mit Flask-Port übereinstimmen.

---

### 7. "Queue läuft über" oder "Performance-Probleme"

**Fehler:** Viele Events → System wird langsam.

**Debugging:**

```python
import asyncio

# In Haupt-Loop
while True:
    size = trigger_queue.qsize()
    if size > 100:
        logger.warning(f"Queue größe: {size} – könnte eng werden!")
    
    event = trigger_queue.get()
    process(event)
```

**Optimierung:**

- Batch-Processing verwenden (mehrere Events auf einmal verarbeiten)
- Threading nutzen (mehrere Worker pro Queue)
- Events filtern (nicht alle verarbeiten)

---

### 8. "Thread-Safety Fehler" / "Race Condition"

**Fehler:** Sporadische, nicht-reproduzierbare Fehler (manchmal funktioniert's, manchmal nicht).

**Ursache:** Zwei Threads ändern gleichzeitig die Daten.

**Lösung – Lock verwenden:**

```python
from threading import Lock

counter_lock = Lock()
counter = 0

def increment():
    global counter
    with counter_lock:  # Nur ein Thread auf einmal!
        counter += 1
        logger.debug(f"Counter: {counter}")
```

---

## Performance-Profiling

Falls das Programm langsam ist:

### 1. Wo ist der Bottleneck?

```python
import time

start = time.time()
result = process_large_data()
elapsed = time.time() - start

logger.info(f"process_large_data() brauchte {elapsed:.2f}s")
```

### 2. Profiler nutzen

```bash
python -m cProfile -s cumtime main.py
```

Das zeigt, welche Funktionen am meisten Zeit verbrauchen.

---

## Debugging-Checkliste

Wenn etwas nicht funktioniert:

- [ ] Sind die **Logs** lesbar?
- [ ] **Try-Except** Blöcke um kritische Teile?
- [ ] **Imports** korrekt? (`pip install` alle Abhängigkeiten?)
- [ ] **Config valide**? (YAML, Ports, etc.)
- [ ] **Breakpoints** gesetzt und durch den Code gelaufen?
- [ ] **Umgebungs-Variablen** korrekt?
- [ ] **Andere Prozesse** blocken Ressourcen? (Ports, Dateien)
- [ ] **Datentyp-Fehler**? (String statt Integer, etc.)
- [ ] **Off-by-one Fehler**? (Index-Fehler)
- [ ] **Race Conditions**? (Threading-Probleme)

---

## Hilfe holen

### 1. Beschreibe dein Problem präzise

**Schlecht:**
> "Mein Plugin funktioniert nicht!"

**Gut:**
> "Mein Plugin Timer startet nicht. Fehler: `ModuleNotFoundError: No module named 'requests'`. Ich habe `pip install -r requirements.txt` ausgeführt, aber es funktioniert nicht."

### 2. Code-Snippet teilen

```python
# Mein on_gift Handler
@client.on(GiftEvent)
def on_gift(event):
    trigger_queue.put_nowait((event.gift.name, event.user.nickname))
    # Fehler hier?
```

### 3. Logs teilen

```
[ERROR] Fehler im Event-Handler:
Traceback (most recent call last):
  File "main.py", line 123, in on_gift
    ...
KeyError: 'gift_id'
```

### 4. Dein Umgebung beschreiben

- OS: Windows / macOS / Linux
- Python: 3.8 / 3.9 / 3.10 / 3.11 / 3.12
- Streaming Tool Version: v1.0 / dev / etc.

---

## Zusammenfassung

Gutes Debugging folgt diesem Flow:

```
Fehler bemerken
    ↓
Logs anschauen (Werkzeug 1)
    ↓
Mit Print debuggen (Werkzeug 2)
    ↓
Try-Except nutzen (Werkzeug 3)
    ↓
VS Code Debugger (Werkzeug 4)
    ↓
Fehler gefunden!
    ↓
Fix implementieren
```

Mit etwas Übung wirst du Fehler schnell finden können.