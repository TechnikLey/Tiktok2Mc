# Glossar

## A

**actions.mca**
Konfigurationsdatei, die TikTok-Trigger auf Minecraft-Aktionen abbildet. Definiert, was passiert, wenn ein bestimmtes Event eintrifft.

**API-Server**
Zentraler HTTP-Server (Port 29185), der die Kommunikation zwischen Plugins, Hooks und dem Hauptsystem verwaltet.

## B

**Bridge-Prozess**
Der Hauptprozess (`src/python/main.py`), der die TikTok-Verbindung verwaltet, Events empfängt und an das System weiterleitet. Importiert Module aus `src/core/` — beide Verzeichnisse teilen denselben PYTHONPATH, daher funktioniert `from core.*` im Bridge-Prozess.

## C

**config.yaml**
Konfigurationsdatei. Jedes Plugin und jeder Hook hat eine eigene. Die globale `config.yaml` enthält systemweite Einstellungen.

**config_schema**
JSON-Schema in der `plugin.json` oder `hook.json`, das die erwartete Konfigurationsstruktur definiert.

## E

**Event**
Eine Nachricht im System, die über den EventBus verteilt wird. Events haben einen Typ (z. B. `tiktok.gift`) und Daten.

**EventBus**
Zentrales Publish/Subscribe-System für die Verteilung von Ereignissen an alle interessierten Komponenten.

**Event-Command-Mapper**
Dienst, der Events aus dem EventBus auf Plugin-Befehle abbildet, basierend auf der `event_commands.yaml`.

## H

**Hook**
Leichte, prozessinterne Erweiterung für `$`-Befehle in der `actions.mca`. Läuft im Bridge-Prozess.

**hook.json**
Manifest-Datei eines Hooks. Enthält Metadaten und Konfigurationsschema.

**HookAPI**
Die Programmierschnittstelle, die Hooks für die Interaktion mit dem Hauptsystem zur Verfügung steht.

## P

**Plugin**
Eigenständiges Programm, das als separater Subprozess läuft und über HTTP mit dem API-Server kommuniziert.

**plugin.json**
Manifest-Datei eines Plugins. Enthält Metadaten, Einstiegspunkt, Abhängigkeiten und Konfigurationsschema.

**Plugin-Registry**
Zentrale Datenbank (in `data/api_plugin_registry.json`), die alle registrierten Plugins mit ihrem Zustand verwaltet.

## R

**RCON (Remote Console)**
Netzwerkprotokoll zum Senden von Befehlen an einen Minecraft-Server.

## S

**SSE (Server-Sent Events)**
Technologie für Echtzeit-Updates vom Server zum Client. Wird für Overlay-Updates verwendet.

## T

**Trigger**
Ein Eintrag in der `actions.mca`, der ein TikTok-Event (oder einen benutzerdefinierten Namen) auf Aktionen abbildet.
