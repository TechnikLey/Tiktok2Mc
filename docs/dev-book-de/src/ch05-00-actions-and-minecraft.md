# Aktionen & Minecraft

Dieses Kapitel beschreibt, wie TikTok-Events in Minecraft-Aktionen umgesetzt werden. Es behandelt die `actions.mca`, den Event-Command-Mapper, RCON und das Overlay-System.

## Zwei Ebenen der Aktionsausführung

| Ebene | Beschreibung | Zielgruppe |
|-------|--------------|------------|
| **actions.mca** | Direkte, benutzerkonfigurierbare Abbildung von Events auf Aktionen | Endbenutzer |
| **Event-Command-Mapper** | Programmgesteuerte lose Kopplung zwischen Komponenten via EventBus | Plugin-Entwickler |

Beide können parallel verwendet werden. Die `actions.mca` ist für einfache, direkte Aktionen gedacht, der Event-Command-Mapper für komplexe Workflows zwischen Plugins.

## Aufbau des Kapitels

1. [Actions.mca Referenz](./ch05-01-actions-mca-overview.md) – Format, Aktionstypen, Kommentare
2. [Event-Command-Mapper](./ch05-02-event-command-mapper.md) – Lose Kopplung zwischen Plugins
3. [RCON & Minecraft](./ch05-03-rcon-and-minecraft.md) – Verbindung zum Minecraft-Server
4. [Overlay-System](./ch05-04-overlay-system.md) – Text und Grafiken im Live-Stream
