# Glossar

Ein komplettes Nachschlagewerk aller Fachbegriffe und Konzepte. Wenn du auf einen unbekannten Begriff stößt, findest du hier eine schnelle Erklärung.

---

## A

### Aktion / Action
Eine Operation, die das System ausführt (z.B. "sende Command an Minecraft"). Actions werden durch Events ausgelöst und sind in der `actions.mca` konfiguriert.

**Beispiel:** Das Gift-Event "Rose" triggert die Action "play_sound".

### Async / Asynchrone Programmierung
Programmierung, bei der mehrere Aufgaben nicht nacheinander, sondern parallel laufen. Ein Prozess muss nicht warten, bis ein anderer fertig ist.

**In diesem Projekt:** TikTok-Events ankommen (Async 1) während der Main-Loop Minecraft-Commands verarbeitet (Async 2).

### API (Application Programming Interface)
Eine Schnittstelle, über die zwei Programme miteinander kommunizieren.

**In diesem Projekt:** Wir nutzen die TikTokLive API (um Events zu empfangen) und die RCON API (um Commands an Minecraft zu senden).

---

## C

### Combo-Gift
Ein Gift, das mehrfach hintereinander gesendet werden kann. Der Nutzer sieht eine Animation mit den Gesamtzahl der Gifts.

**Beispiel:** Jemand sendet dieselbe Rose 5-mal → der Nutzer sieht "Rose ×5".

**Im Code:** `event.gift.combo == True` und `event.repeat_count == 5`

### CORS (Cross-Origin Resource Sharing)
Ein Sicherheits-Mechanismus in Webserver, der bestimmt, welche externe Websites Anfragen senden dürfen.

**In diesem Projekt:** Unser Flask-Server nutzt CORS, um Plugin-GUIs Zugriff auf die APIs zu geben.

### Command-Line Argument / Flag
Ein Wert, den man beim Starten eines Programms übergibt.

**Beispiel:** 
```bash
python main.py --gui-hidden --register-only
```

Hier sind `--gui-hidden` und `--register-only` Flags.

---

## D

### DCS (Direct Control System)
Ein Kommunikations-Protokoll, bei dem Daten direkt via HTTP übertragen werden.

**Vorteil:** Schnell & zuverlässig.  
**Nachteil:** Erfordert offene HTTP-Ports.

**Alternative:** ICS (Interface Control System).

### Dekorator
Ein Python-Feature (@...), das eine Funktion mit zusätzlichem Verhalten "verziert".

**Beispiel:**
```python
@client.on(GiftEvent)
def handle_gift(event):
    pass
```

Das `@client.on(...)` Dekorator registriert diese Funktion als Event-Handler.

### Dependency (Abhängigkeit)
Ein externes Paket, das dein Projekt braucht.

**In diesem Projekt:**
- `TikTokLive` - Abhängigkeit
- `Flask` - Abhängigkeit
- All sind in `requirements.txt` aufgelistet.

---

## E

### Event
Ein Ereignis, das im System passiert.

**Beispiele:**
- Jemand sendet ein Gift
- Jemand folgt
- Ein Spieler stirbt in Minecraft
- Der Server startet

Alle Events haben Eigenschaften (Daten), z.B. `event.user`, `event.gift.name`.

### Event-Handler
Eine Funktion, die auf ein Event reagiert.

**Beispiel:**
```python
@client.on(GiftEvent)
def on_gift(event):
    print(f"Gift empfangen: {event.gift.name}")
```

`on_gift` ist der Event-Handler für GiftEvents.

---

## F

### Flask
Ein Python-Webframework zum Erstellen von Webservern.

**Verwendung in unserem Projekt:**
- Webhooks (Empfang von Minecraft-Events)
- GUIs (pywebview nutzt Flask für die Backend-API)

**Nicht zu verwechseln mit:** Django (anderes Framework), FastAPI (neuer Standard).

### Function
Siehe Handler/Funktion.

---

## G

### Glossar
Dieses Dokument! Ein Nachschlagewerk von Fachbegriffen.

---

## H

### Handler
Siehe Event-Handler.

### HTTP / HTTPS
Netzwerk-Protokolle zum Übertragen von Daten über das Internet / Netzwerk.

**HTTP** = unsicher (aber schneller)  
**HTTPS** = verschlüsselt (aber komplexer)

**In diesem Projekt:** Wir nutzen HTTP lokal (nicht über Internet).

---

## I

### ICS (Interface Control System)
Ein Kommunikations-Protokoll, bei dem Daten via GUI/Screen-Capture übertragen werden.

**Vorteil:** Funktioniert überall (auch mit TikTok Live Studio).  
**Nachteil:** Langsamer & komplexer.

**Alternative:** DCS (Direct Control System).

### Import
Das Laden von externem Code in dein Programm.

**Beispiel:**
```python
from core import load_config
```

Das lädt die `load_config`-Funktion aus dem `core`-Modul.

---

## J

### JSON
Ein Datenformat zum speichern & übertragen von strukturierten Daten.

**Format:**
```json
{
    "name": "John",
    "age": 30,
    "gifts": ["Rose", "Diamond"]
}
```

**In diesem Projekt:** Wird für Konfigurationen, Window-States und Daten verwendet.

---

## L

### Logging / Logs
Das Speichern von Programmierungsvorgängen in eine Datei oder als Output.

**Zweck:** Debuggen & Monitoring.

**Beispiel:**
```python
logging.info("Gift received")
logging.error("Connection failed")
```

Logs landen dann in `logs/debug.log`.

---

## M

### main.py
Die Haupt-Programmdatei des Projekts. Sie verbindet TikTok mit dem Rest des Systems.

### Middleware
Software, die zwischen zwei anderen Systemen vermittelt.

**In unserem Projekt:** `main.py` enthält den Webhook-Endpunkt und ist Middleware zwischen Minecraft und den Plugins. `server.py` hingegen startet den Minecraft-Server selbst.

### Migration
Der Prozess, Daten von alt zu neu zu übertragen.

**In diesem Projekt:**
- Config-Migration: Alte `config.yaml` wird auf neue Struktur aktualisiert
- Siehe [Config](./config.md) für Details.

### Module
Wiederverwendbare Code-Bausteine, die andere Dateien/Projekte nutzen können.

**In diesem Projekt:**
- `core/models.py` - Datenstrukturen-Module
- `core/paths.py` - Pfad-Module
- Immer im `src/core/` Ordner.

---

## O

### Overlay
Eine visuelle Element, die über den Stream / Screen gelegt wird.

**Beispiel:** Ein Counter zeigt auf dem Screen "Deaths: 5", "Likes: 200".

**In diesem Projekt:** Plugins nutzen Overlays um Daten visuell darzustellen.

---

## P

### Parameter
Ein Wert, der an eine Funktion übergeben wird.

**Beispiel:**
```python
def create_client(user):  # 'user' ist der Parameter
    ...

create_client("my_streamer")  # 'my_streamer' wird übergeben
```

### Path / Pfad
Ein Dateipfad im Dateisystem.

**Windows:** `C:\Users\...\config\config.yaml`  
**Linux:** `/home/.../config/config.yaml`

### Plugin
Ein eigenständiges Program, das sich ins Streaming Tool einfügt.

**Beispiele:**
- Timer (Countdown-Timer)
- DeathCounter (Zählt Tode)
- Dein Custom-Plugin

### Port
Ein virtueller "Hafen", über den ein Server Verbindungen akzeptiert.

**Beispiel:** `http://localhost:8080` - Port ist `8080`.

**Config:** Alle Ports sind in der `config.yaml` konfigurierbar.

### Pseudo-Code
Vereinfachter Code, der nicht syntax-korrekt ist, aber die Logik zeigt.

**Beispiel:**
```
1. Wenn Gift kommt
2. Finde Konfiguration
3. Führe Action aus
```

---

## Q

### Queue / Warteschlange
Eine Datenstruktur, die Elemente in der Reihenfolge speichert, in der sie hinzugefügt wurden (FIFO: First-In-First-Out).

**In unserem Projekt:**
- `trigger_queue`: Speichert die zu verarbeitenden Trigger
- `like_queue`: Speichert Like-Updates für das Overlay

---

## R

### Race Condition
Ein Bug, der auftritt, wenn zwei Threads gleichzeitig auf die gleiche Ressource zugreifen.

**Beispiel:** Thread 1 liest `event.total`, Thread 2 ändert es → Inkonsistenz!

**Lösung:** Lock (Mutex) - nur ein Thread darf gleichzeitig zugreifen.

### Registry / Registrierung
Eine Zentrale Verwaltungs-Datei oder -System.

**In diesem Projekt:** `PLUGIN_REGISTRY` registriert alle Module & Plugins mit ihren Einstellungen.

### RCON (Remote Console)
Ein Protokoll & Server, über den man Minecraft-Commands remote senden kann.

**Beispiel:** Statt direkt in der Minecraft Console zu tippen, sendet das Tool via RCON den Command `/say "Hey!"`.

### Reverse Engineering
Das Nachbauen eines Systems, indem man sein Verhalten von außen beobachtet.

**In diesem Projekt:** Die TikTokLive API basiert auf Reverse Engineering (nicht offiziell von TikTok).

---

## S

### Streak / Steigerung
Ein Combo, das mehrfach hintereinander aktiviert wird.

**Beispiel:** Dieselbe Rose wird 5-mal hintereinander gesendet → "Streak: 5".

### SQL / Datenbank
Ein System zur strukturierten Datenspeicherung (in diesem Projekt nicht zentral relevant).

---

## T

### Thread / Threading
Ein eigenständiger Ausführungs-Fluss innerhalb eines Programms.

**Analoge:** Ein Programm mit 2 Threads is wie ein Streamer mit 2 Mikrophonen – beide können gleichzeitig sprechen.

**Gefahr:** Racing Conditions (zwei Threads ändern Daten parallel).

### Trigger
Eine Bedingung, die eine Action ausführt.

**Beispiel:** 
- `gift_1001` ist ein Trigger (wenn dieses Gift kommt)
- `follow` ist ein Trigger (wenn jemand folgt)
- Wenn Trigger ausgelöst → Action wird ausgeführt

### TikTokLive API
Die externe Bibliothek, über die wir TikTok Live-Streams erreichen.

**Basiert auf:** Reverse Engineering (nicht offiziell).

**Nutzen:** `from TikTokLive import TikTokLiveClient`

---

## U

### Update
Ein neuer Release / eine neue Version des Projekts.

**Prozess:**
1. Neue Version wird auf GitHub hochgeladen  
2. Nutzer startet das Programm
3. Update-Script laden neue Version
4. Alte Daten bleiben erhalten (`config/`, `data/`  überschrieben nicht)

**Details:** Siehe [Update](./update.md).

---

## V

### Validator
Ein Modul, das überprüft, ob Daten korrekt sind.

**Beispiel:** `validator.py` prüft, ob `config.yaml` valides YAML ist.

### Variable
Ein benanntes Behältnis für Daten.

**Beispiel:** `gift_name = event.gift.name` - `gift_name` ist die Variable.

---

## W

### Webhook
Ein Mechanismus, bei dem ein System automatisch Daten an ein anderes sendet, wenn etwas passiert.

**Im Projekt:**
- Minecraft Server sendet Webhook an unser Tool (wenn Player stirbt, spawnt, etc.)
- Unser Tool verarbeitet dann den Webhook

**Format:** Normalerweise HTTP POST mit JSON-Daten.

---

## X

### (keine gängigen Begriffe)

---

## Y

### YAML
Ein Datenformat zum Speichern von strukturierten Daten (ähnlich JSON, aber lesbar-freundlicher).

**Format:**
```yaml
timer:
  enable: true
  start_time: 10
  max_time: 60
```

**In diesem Projekt:** `config.yaml` ist in YAML geschrieben.

---

## Z

### Zentralisierung
Das Konzept, alles an einem Ort zu verwalten.

**Im Projekt:** `PLUGIN_REGISTRY` ist zentrale Verwaltung aller Plugins.

---

## Schnell-Index nach Kategorie

### **Event-System**
- Event, Event-Handler, Trigger, Action
- Webhook, RCON

### **Technik**
- API, HTTP/HTTPS, Port
- Thread/Threading, Race Condition
- Async, Middleware

### **Python & Code**
- Import, Module, Decorator
- Parameter, Variable, Handler
- Function, Logging

### **Datenformate**
- JSON, YAML, Datenbank

### **Struktur & Organisation**
- Registry, Migration
- Queue, Warteschlange
- Path / Pfad

### **Control & Kommunikation**
- DCS, ICS, Flask
- CORS

### **Debugging & Entwicklung**
- Logging, Validator
- Pseudo-Code, Reverse Engineering

---

## "Ich verstehe den Begriff XYZ immer noch nicht!"

Das ist OK. Hier sind Optionen:

1. **Re-read** Lesse es einfach nochmal
2. **Context:** Suche nach dem Begriff in der Dokumentation – der Kontext hilft
3. **Code lesen:** Schau dir an, wie der Begriff im echten Code verwendet wird
4. **Frag:** Andere Entwickler oder eine KI um Hilfe