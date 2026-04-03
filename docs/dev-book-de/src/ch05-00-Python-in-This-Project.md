# Python in diesem Projekt

Python ist die zentrale Sprache dieses Projekts. In diesem Kapitel lernst du, wie das Projekt organisiert ist und welche Teile zusammenspielen.

---

## Warum Python?

Python wurde für dieses Projekt gewählt, weil es:

- **Schnell zu entwickeln** ist (wenig Boilerplate-Code)
- **Gutes Ökosystem** für Web (Flask), Async (asyncio), und APIs (TikTokLive) hat
- **Lesbar und wartbar** bleibt, es auch selbst wenn es komplex wird
- **Cross-Platform** funktioniert (Windows, macOS, Linux)

---

## Die Hauptkomponenten

### 1. **main.py** – Das Herzstück

```python
# Vereinfachtes Schema
def main():
    1. Config laden
    2. TikTok Client einrichten
    3. Event-Handler registrieren
    4. Client verbinden (parallel)
    5. Startup-Services starten (Server, GUI, Plugins)
    6. Event-Queue verarbeiten (Hauptloop)
```

Diese Datei verbindet TikTok mit dem Rest des Systems.

### 2. **core/** – Wiederverwendbare Module

**Was darin ist:**

| Modul | Zweck |
|-------|-------|
| `models.py` | Datenstrukturen (AppConfig, PluginInfo, etc.) |
| `cli.py` | Command-Line Argumente parsen |
| `paths.py` | Pfad-Funktionen (ROOT_DIR, BASE_DIR, etc.) |
| `utils.py` | Helferfunktionen (Strings bereinigen, etc.) |
| `validator.py` | Config validieren |

Diese Module kannst du überall im Projekt importieren:

```python
from core import load_config, register_plugin, get_root_dir
```

### 3. **server.py** – Minecraft-Server-Starter

Startet den Minecraft-Server als Subprocess:

```
config.yaml
    ↓ (Xms, Xmx, Port, RCON)
server.py
    ↓ java -jar server.jar
Minecraft Server läuft
```

> [!NOTE]
> Der Webhook-Endpunkt (`/webhook`) befindet sich in **main.py**, nicht in server.py.

### 4. **registry.py** – Plugin-Verwaltung

Lädt und verwaltet alle Plugins:

```python
# Vereinfacht
PLUGIN_REGISTRY = [
    {"name": "App", "path": ..., "enable": True, ...},
    {"name": "Timer", "path": ..., "enable": True, ...},
    # Mehr Plugins...
]
```

### 5. **plugins/** – Frei erweiterbar

Hier schreibst du deine eigenen Plugins:

```
src/plugins/
├── timer/
│   ├── main.py        # Timer-Logik
│   ├── README.md
│   └── version.txt
│
├── my_custom_plugin/  # Dein Plugin!
│   ├── main.py
│   ├── README.md
│   └── version.txt
```

---

## Der Datenfluss (Vereinfacht)

```
TikTok Live Stream
    ↓
TikTokLive API (WebSocket)
    ↓
main.py (empfängt Events)
    ↓
Event-Handler registriert (z.B. on_gift, on_follow)
    ↓
Trigger finden + in Queue legen
    ↓
Main-Loop verarbeitet Queue
    ↓
RCON → Minecraft Server
    ↓
Minecraft Server führt Command aus
```

**Wichtig:** Das ist NICHT synchron. Events warten in einer Queue, bis sie verarbeitet werden können.

---

## Importe verstehen

Wenn du Python-Dateien im Projekt öffnest, siehst du Importe wie:

```python
from TikTokLive import TikTokLiveClient, TikTokLiveConnection
from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent
```

Das sind **externe Bibliotheken** (nicht eingebaut in Python):

| Bibliothek | Zweck |
|-----------|-------|
| `TikTokLive` | Verbindung zu TikTok Live |
| `Flask` | Web-Framework für Webhooks |
| `pywebview` | Desktop-GUI Fenster |
| `pyyaml` | Config-Dateien lesen |
| `asyncio` | Asynchrone Programmierung |

Alle sind in `requirements.txt` aufgelistet.

---

## Threading & Asynchronität (kurz angerissen)

Das Projekt nutzt **Threading** an mehreren Stellen:

```
TikTok Event empfangen (Thread 1)
    ↓
Queue füllen
    ↓
Main-Loop verarbeiten (Thread 2)
    ↓
Minecraft-Command senden
```

Warum? Weil TikTok Events nicht warten können. Wenn der Main-Loop gerade Minecraft bedient, müssen neue Events dennoch ankommen können.

Threading können kompliziert sein, deshalb behandeln wir das später genauer in [Threading-and-Queues](./ch05-08-Threading-and-Queues.md).

---

## Welche Dateien brauchst du zum Verstehen?

Wir konzentrieren uns auf diese Dateien:

1. **main.py** – Wie Daten hereinkommen
2. **server.py** – Wie der Minecraft-Server gestartet wird
3. **registry.py** – Wie Plugins geladen werden
4. **core/** – Hilfsfunktionen

Für Plugin-Entwicklung:
- **src/plugins/timer/main.py** – Gutes Beispiel
- **config.yaml** – Plugin-Konfiguration

**Nicht relevant fürs erste Verständnis:**
- Build-Skripte (build.ps1, upload.ps1)
- Migrations-Code für config
- templatefiles

---

## Nächster Schritt

Jetzt verstehst du die grobe Struktur. Der nächste Teil taucht tiefer ein.

**→ [Die main.py Datei](./ch05-01-The-main.py-File.md)**

Dort sehen wir, wie die Hauptdatei aufgebaut ist und welche Aufgaben sie erfüllt.