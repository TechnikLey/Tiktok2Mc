# Erste Schritte

Dieses Kapitel führt dich durch die ersten Schritte mit TikTok2Mc. Du lernst, wie du die Entwicklungsumgebung einrichtest, das System startest und die grundlegende Projektstruktur verstehst.

## Voraussetzungen

Stelle sicher, dass folgende Komponenten installiert sind:

- **Python 3.12 oder höher**
- **Git** (zum Klonen des Repositories)
- **Minecraft Java Edition** (für die Minecraft-Integration)
- Ein **TikTok-Konto** mit Live-Streaming-Zugang (für den Live-Betrieb)

## Installation

Klone das Repository und installiere die Abhängigkeiten:

```bash
git clone https://github.com/TechnikLey/Tiktok2Mc.git
cd Tiktok2Mc
pip install -r requirements.txt
```

## Projektstruktur

Die wichtigsten Verzeichnisse und Dateien im Überblick:

| Verzeichnis/Datei | Zweck |
|---|---|
| `src/core/` | Hauptsystem – API-Server, Plugin- und Hook-Verwaltung |
| `src/plugins/` | Enthält alle Plugins (ein Ordner pro Plugin) |
| `src/hooks/` | Enthält alle Hooks (ein Ordner pro Hook) |
| `src/python/` | Startskripte und Hilfsprogramme |
| `data/` | Laufzeitdaten, Konfiguration und persistierte Zustände |
| `defaults/` | Standardkonfigurationen (`actions.mca`, `event_commands.yaml`) |
| `config.yaml` | Hauptkonfigurationsdatei |
| `create_plugin.py` | Skript zum Erstellen neuer Plugins |
| `create_hook.py` | Skript zum Erstellen neuer Hooks |
| `run.py` | Startet das gesamte System |
| `build.py` | Erstellt eine ausführbare Distribution |

## Erster Start

Starte das System mit folgendem Befehl:

```bash
python run.py
```

Beim ersten Start werden die benötigten Verzeichnisse und Standardkonfigurationen angelegt. Das System startet den API-Server und wartet auf eine TikTok-Verbindung.

## Konfiguration

Die Hauptkonfiguration befindet sich in `config.yaml` im Projektstamm. Hier werden globale Einstellungen wie RCON-Verbindungsdaten und TikTok-Benutzername festgelegt.

Plugins verwalten ihre eigene Konfiguration in `config.yaml` innerhalb ihres Plugin-Ordners. Hooks haben ebenfalls eine eigene `config.yaml` in ihrem Hook-Ordner.

## Nächste Schritte

Sobald das System läuft, kannst du mit den [Grundkonzepten](./ch02-00-core-concepts.md) vertraut machen. Danach geht es direkt zur [Plugin-Entwicklung](./ch03-00-plugins.md) oder [Hook-Entwicklung](./ch04-00-hooks.md).
