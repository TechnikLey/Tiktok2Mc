# Grundkonzepte

Dieses Kapitel vermittelt die grundlegenden Konzepte, die du für die Entwicklung von Plugins und Hooks benötigst. Es beschreibt die Architektur auf hoher Ebene und erklärt, wie die einzelnen Komponenten zusammenarbeiten.

## Systemübersicht

TikTok2Mc verbindet TikTok-Live-Events mit Minecraft. Die Daten durchlaufen dabei mehrere Stationen:

```
TikTok Live → Bridge-Prozess → EventBus → Plugins / Hooks → Minecraft (RCON)
```

1. **TikTok Live**: Eingehende Events (Gifts, Follows, Likes, Comments, Shares, Joins) werden vom TikTokLive-Client empfangen.
2. **Bridge-Prozess** (`src/python/main.py`): Der zentrale Hauptprozess des Systems. Er startet den API-Server, verwaltet die TikTok-Verbindung, lädt Hooks, empfängt TikTok-Events und leitet sie in den EventBus weiter. Der Bridge-Prozess läuft durchgehend und koordiniert alle Komponenten.
3. **EventBus**: Ein zentrales Publish/Subscribe-System, das Ereignisse an alle interessierten Komponenten (Plugins, Hooks, Event-Command-Mapper) verteilt.
4. **Plugins & Hooks**: Diese Komponenten reagieren auf Ereignisse und führen Aktionen aus. Plugins laufen als separate Prozesse, Hooks laufen direkt im Bridge-Prozess.
5. **Minecraft**: Über RCON (Remote Console) werden Befehle an den Minecraft-Server gesendet.

## API-Server

Der API-Server ist ein HTTP-Server, der unter `http://127.0.0.1:29185/api/v1/` läuft und die gesamte Kommunikation zwischen Plugins, Hooks und dem Hauptsystem vermittelt. Er wird vom Bridge-Prozess gestartet und bietet:

- **Plugin-Registrierung**: Plugins melden sich über `POST /api/v1/plugins/register` an
- **EventBus-Zugriff**: Komponenten können Events über `POST /api/v1/events` veröffentlichen
- **Overlay-Auslieferung**: Overlay-HTML und SSE-Updates werden über den API-Server bereitgestellt

Ein Plugin kommuniziert **ausschließlich** über den API-Server mit dem Rest des Systems – es gibt keine direkte Verbindung zwischen Plugins oder zum Bridge-Prozess.

## Plugins vs. Hooks

TikTok2Mc bietet zwei Erweiterungsmechanismen, die für unterschiedliche Anwendungsfälle optimiert sind:

### Plugins

- **Separater Prozess**: Jedes Plugin läuft in einem eigenen Subprozess.
- **API-Kommunikation**: Plugins kommunizieren über HTTP mit dem zentralen API-Server.
- **Sandboxing**: Plugins können über Betriebssystem-Ressourcenlimits isoliert werden.
- **GUI-Unterstützung**: Plugins können eigene Overlay-Fenster mit pywebview erstellen.
- **Zustandsverwaltung**: Plugins haben einen eigenen Zustand und können Overlay-HTML registrieren.
- **Geeignet für**: Komplexe Erweiterungen mit GUI, eigenem Zustand oder speziellen Ressourcenanforderungen.

### Hooks

- **Im Prozess**: Hooks laufen direkt im Bridge-Prozess, ohne eigenen Subprozess.
- **Direkte Funktionen**: Hooks registrieren Handler-Funktionen für `$`-Befehle in der `actions.mca`.
- **Leichtgewichtig**: Kein Overhead durch Prozessverwaltung oder HTTP-Kommunikation.
- **Import-Beschränkungen**: Hooks haben eingeschränkte Importmöglichkeiten (Sicherheit).
- **Geeignet für**: Einfache, reaktive Erweiterungen, die auf TikTok-Events mit Minecraft-Befehlen reagieren.

### Wann Plugin, wann Hook?

| Kriterium | Plugin | Hook |
|---|---|---|
| Komplexität | Hoch | Niedrig |
| GUI benötigt | Ja | Nein |
| Eigenständiger Zustand | Ja | Nein |
| Ressourcenintensiv | Ja | Nein |
| Einfache Reaktion auf Events | Möglich | Optimal |

## Events & Trigger

### Events

Events sind die grundlegende Nachrichteneinheit im System. Sie werden über den EventBus verteilt:

- **TikTok-Events**: `tiktok.gift`, `tiktok.follow`, `tiktok.like`, `tiktok.join`, `tiktok.comment`, `tiktok.share`
- **Plugin-Events**: Von Plugins ausgelöst, z. B. `timer.zero`, `death.milestone`
- **Minecraft-Events**: `minecraft.player_death` (über Webhook)
- **System-Events**: `server.started`, `server.stopping`

### Trigger

Trigger sind die Einträge in der `actions.mca`, die TikTok-Ereignisse auf Aktionen abbilden. Ein Trigger kann sein:

- Ein Event-Name: `follow`, `like`, `join`, `comment`, `share`
- Eine Gift-ID: `5655` (für eine Rose)
- Ein Eigenname: Ein benutzerdefinierter Name für die Trigger-Verkettung

Jeder Trigger kann mehrere Aktionen auslösen: Vanilla-Befehle, RCON-Befehle, Hook-`$`-Befehle, Overlay-Text oder Shell-Befehle.

## Event-Command-Mapper

Der Event-Command-Mapper ist ein zentraler Bestandteil, der EventBus-Ereignisse auf Plugin-Befehle abbildet. Er liest die Datei `event_commands.yaml` und leitet Befehle an die entsprechenden Plugins weiter. Dies ermöglicht lose Kopplung zwischen Komponenten – Plugins müssen nichts voneinander wissen.

## Nächstes Kapitel

Im nächsten Kapitel beginnst du mit der [Plugin-Entwicklung](./ch03-00-plugins.md) und erstellst dein erstes Plugin.
