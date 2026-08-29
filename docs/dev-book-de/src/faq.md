# FAQ

## Allgemein

### Kann ich ein Plugin in einer anderen Sprache als Python schreiben?

Ja, Plugins können in jeder Sprache geschrieben werden, solange sie als eigenständiger Prozess laufen und die HTTP-API des Systems ansprechen können. Der Aufwand ist jedoch deutlich höher, da du die gesamte Kommunikation selbst implementieren musst. Diese Dokumentation beschreibt nur die Python-API über `BasePlugin` — für andere Sprachen musst du die HTTP-Endpunkte aus dem Quellcode ermitteln.

### Was ist der Unterschied zwischen einem Plugin und einem Hook?

Ein Plugin ist ein separater Prozess mit eigener GUI, Zustandsverwaltung und Sandboxing. Ein Hook ist eine leichte, prozessinterne Erweiterung, die nur für `$`-Befehle in der `actions.mca` gedacht ist. Details findest du in [Grundkonzepte](./ch02-00-core-concepts.md).

### Kann ich mehrere Hooks in einer Datei haben?

Jeder Hook hat seine eigene Datei `main.py` und sein eigenes Verzeichnis. Eine einzelne `main.py` kann aber beliebig viele Aktionen registrieren.

## Entwicklung

### Mein Plugin wird nicht in der Liste angezeigt. Was tun?

Prüfe, ob die `plugin.json` existiert und gültig ist. Der `entry_point` muss korrekt sein. Starte das System neu, damit der Plugin-Watcher erneut scannt.

### Mein Hook wird nicht geladen. Was tun?

Prüfe, ob die `register()`-Funktion existiert und ob alle Importe erlaubt sind. Prüfe die Logs auf Fehlermeldungen.

### Kann ich externe Bibliotheken in Hooks verwenden?

Nein. Hooks dürfen nur die erlaubten Module importieren (siehe [Import-Beschränkungen](./ch04-05-import-restrictions.md)). Wenn du externe Bibliotheken benötigst, erstelle ein Plugin.

## Events

### Wie empfange ich TikTok-Events in meinem Plugin?

Deklariere `event_subscriptions` in der `plugin.json` und registriere einen Handler für `"tiktok_event"`. Siehe [Events & Subscriptions](./ch03-05-events-and-subscriptions.md).

### Wie sende ich ein Event von meinem Plugin?

Verwende `self.api_post("/events", {"type": "mein.event", "data": {...}})`. Das Event wird dann über den EventBus verteilt.

### Was ist der Event-Command-Mapper?

Der Event-Command-Mapper leitet Events aus dem EventBus an Plugins weiter, basierend auf der Konfiguration in `event_commands.yaml`. Siehe [Event-Command-Mapper](./ch05-02-event-command-mapper.md).

## Minecraft

### Wie sende ich Minecraft-Befehle aus einem Hook?

Verwende `api.rcon_enqueue([...])`. Siehe [Hook-API](./ch04-03-hook-api.md).

### Wie sende ich Minecraft-Befehle aus einem Plugin?

Plugins kommunizieren indirekt über den [Event-Command-Mapper](./ch05-02-event-command-mapper.md) oder über `send_command()` an spezialisierte Komponenten. Siehe [Plugin-übergreifende Kommunikation](./ch03-06-cross-plugin-communication.md).

### Kann ich Befehle von Minecraft-Server-Plugins (Bukkit/Paper) senden?

Ja, RCON kann sowohl Vanilla-Befehle als auch Plugin-Befehle senden. Der Minecraft-Server behandelt sie wie Eingaben aus der Konsole.

## Overlay

### Wie zeige ich Text im Overlay an?

In Hooks mit `api.send_overlay_text()`. In Plugins mit `get_overlay_html()` und `push_state()`.

### Wie binde ich ein Plugin-Overlay in OBS ein?

Verwende die URL `http://127.0.0.1:29185/api/v1/plugins/<plugin-name>/overlay` als Browser-Quelle.
