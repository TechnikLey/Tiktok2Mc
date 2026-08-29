# Grundkonzepte

Dieses Kapitel erklärt die Architektur und die wichtigsten Komponenten, die du als Entwickler kennen musst.

## Systemarchitektur

```
┌─────────────────────────────────────────────────────────┐
│                    Supervisor (start.py)                │
│  Startet und überwacht alle Komponenten                 │
└─────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│  API-Server      │  │  Bridge (main.py)│  │  Minecraft      │
│  (FastAPI)       │  │  TikTok-Client   │  │  Server         │
│  Port 29185      │  │  EventBus        │  │  (RCON)         │
│                  │  │  Hook-Loader     │  │                 │
│  Plugin-Watcher  │  │  RCON-Worker     │  │                 │
│  CommandQueue    │  │  Event-Bridge    │  │                 │
│  Event-Command-  │  │  Trigger-Worker  │  │                 │
│  Mapper          │  │                  │  │                 │
└────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘
         │                     │                     │
         │   HTTP (POST/GET)   │   asyncio.Queue     │   RCON
         ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│  Plugins (Subprozesse)                                   │
│  python src/plugins/*/main.py                            │
│  Kommunizieren per HTTP mit API-Server                   │
└──────────────────────────────────────────────────────────┘
```

### Supervisor (`src/python/start.py`)

Der Supervisor ist der Lebenszyklus-Manager. Er startet API-Server, Bridge-Prozess, Minecraft-Server und GUI, überwacht ihre Gesundheit und startet sie bei Bedarf neu.

### API-Server (`src/core/api/server.py`)

Zentraler HTTP-Server (FastAPI) auf Port 29185. Stellt bereit:

- **Plugin-Registrierung und -Verwaltung** — `PluginWatcher` scannt `src/plugins/` und registriert Plugins
- **CommandQueue** — Speichert eingehende Befehle pro Plugin (Long-Polling über `?wait=1`)
- **Event-Command-Mapper** — Leitet EventBus-Ereignisse an Plugin-Commands weiter
- **Overlay-Auslieferung** — HTML und SSE-Updates für OBS/Browser
- **Plugin-Signale** — Signal-Dateien in `core/runtime/` steuern Plugin-Start/Stopp

### Bridge-Prozess (`src/python/main.py`)

Der TikTok→Minecraft-Bridge-Prozess. Enthält:

- **TikTokLive-Client** — Empfängt Live-Events (Gift, Follow, Like, Comment, Join, Share)
- **EventBus** — In-Memory Publish/Subscribe (asyncio.Queue-basiert, max. 2000 Events pro Queue)
- **Event-Bridge Worker** — Leitet TikTok-Events an Plugins mit passenden `event_subscriptions` weiter
- **Trigger-Worker** — Verarbeitet die `actions.mca` und führt Aktionen aus
- **RCON-Worker** — Sendet Minecraft-Befehle an den Server (mit Wiederholungslogik)
- **Hook-Loader** — Lädt und initialisiert Hooks aus `src/hooks/`

## Projektverzeichnis: `src/core/` vs. `src/python/`

Das Projekt hat zwei Python-Quellverzeichnisse mit unterschiedlichen Rollen:

| Verzeichnis | Rolle | Python-Paket |
|-------------|-------|-------------|
| `src/core/` | **API-Server, Infrastruktur, geteilte Module** (`BasePlugin`, `EventBus`, `config`, `backup`, `health`, `error_codes`, usw.) | Kann via `PYTHONPATH` oder `pip install -e .` als Paket `core` importiert werden |
| `src/python/` | **Startpunkte und Subprozesse** (`start.py` = Supervisor, `main.py` = Bridge, `send_trigger.py`, `spotify_setup.py`, usw.) | Kein eigenes Paket — importiert `core.*` aus dem Schwesterverzeichnis |

**Warum zwei Verzeichnisse?** `src/core/` enthält die gemeinsame Logik, die von allen Komponenten genutzt wird — inklusive Plugins (`from core.base_plugin import BasePlugin`). `src/python/` enthält ausführbare Einstiegspunkte, die als separate Prozesse laufen (Supervisor, Bridge). Beide teilen sich denselben `PYTHONPATH`, daher funktioniert `from core.*` in beiden Verzeichnissen.

**Für Plugin-Entwickler relevant**: Dein Plugin lebt in `src/plugins/<name>/`, importiert aber `BasePlugin` aus `src/core/`. Der Subprozess (`python src/plugins/<name>/main.py`) findet `core` über den `PYTHONPATH`, der vom Supervisor gesetzt wird.

## Zwei Wege der Event-Zustellung

```
TikTok-Event
    │
    ├──→ EventBus (Bridge-Prozess)
    │       │
    │       ├──→ Event-Bridge Worker → CommandQueue → Plugin-Polling
    │       │      (Filtert nach event_subscriptions)
    │       │
    │       ├──→ Event-Command-Mapper → CommandQueue → Plugin-Polling
    │       │      (Abbildung via event_commands.yaml)
    │       │
    │       └──→ Trigger-Worker → execute_global_command()
    │              (Führt actions.mca aus: RCON, Scripts, Overlays, Shell)
    │
    └──→ TikTok-Client Callback → Trigger-Queue (direkt für actions.mca-Triggernamen)
```

## Plugins vs. Hooks

| Kriterium | Plugin | Hook |
|-----------|--------|------|
| Ausführung | Eigener Subprozess (python .../main.py) | Im Bridge-Prozess (direkter Aufruf) |
| Kommunikation | HTTP (POST/GET zum API-Server) | Funktionsaufruf (über HookAPI) |
| GUI | pywebview-Fenster oder OBS-Overlay | Keine GUI |
| Zustand | Eigener State (per `push_state()`) | Kein Zustand |
| Latenz | ~1s (Polling-Intervall) | Millisekunden |
| Komplexität | Vollständige Klasse mit Threads | Einfache Funktion |
| Anwendungsfall | Komplexe Logik, GUI, Timer | Einfache `$`-Befehle für Minecraft |

## Kommunikationswege

```
Plugin A ──send_command("B", "start", {})──→ API-Server ──→ Plugin B (CommandQueue)
Plugin A ──api_post("/events", ...)─────────→ EventBus ──→ Event-Command-Mapper ──→ Plugin B
Plugin A ──api_post("/events", ...)─────────→ EventBus ──→ Event-Bridge ──→ Plugin B
Hook ──────api.rcon_enqueue([...])──────────→ RCON-Queue ──→ Minecraft-Server
Hook ──────api.enqueue_trigger("name", user)→ Trigger-Queue ──→ execute_global_command()
```

## Nächstes Kapitel

Ab jetzt geht es in die Praxis. Im [nächsten Kapitel](./ch03-00-plugins.md) entwickelst du dein erstes vollständiges Plugin.
