# Best Practices (Plugin)

Dieses Kapitel fasst bewährte Verfahren und häufige Fehler zusammen, die dir bei der Plugin-Entwicklung begegnen können.

## Plugin-Struktur

- **Eindeutige Plugin-Namen**: Verwende Kebab-Case (`mein-plugin`) und stelle sicher, dass der Name in `plugin.json` und `PLUGIN_NAME` übereinstimmen.
- **Eindeutige Ports**: Jedes Plugin braucht einen eigenen Port. Vermeide Konflikte mit den Built-in-Plugins (Bereich `29189`–`29194`).
- **Vollständiges Manifest**: Gib immer `min_api_version`, `author` und `description` an.

## Konfiguration

- **Schema definieren**: Ein `config_schema` in der `plugin.json` stellt sicher, dass die Konfiguration immer gültig ist.
- **Standardwerte setzen**: Jedes Feld im Schema sollte einen sinnvollen Standardwert haben.
- **Theme nutzen**: Verwende `self.theme_style` für konsistente Overlay-Gestaltung.
- **Keine harten Pfade**: Verwende `self._data_dir` für Daten und `self._plugin_dir` für Plugin-Dateien.

## Event-Handling

- **Handler registrieren**: Verwende `register_handler()` statt `on_command()` zu überschreiben, wo möglich.
- **Events dokumentieren**: Gib bei `api_post("/events", ...)` aussagekräftige Event-Typen wie `mein-plugin.ereignis`.
- **Event-Check vor Verarbeitung**: Prüfe in `_on_tiktok_event` den `event_type` vor der Verarbeitung.

## Fehlerbehandlung

- **Handler-Fehler abfangen**: Die Basisklasse fängt Fehler in Handlern. Protokolliere sie trotzdem mit `log.exception()`.
- **API-Fehler erwarten**: `api_post` und `api_get` geben bei Fehlern `False` bzw. `None` zurück – prüfe die Rückgabewerte.
- **Keine Endlosschleifen**: Vermeide es, Events auszulösen, die wiederum dein eigenes Plugin triggern.

## Overlay

- **SSE für Updates**: Nutze Server-Sent Events statt Polling für Echtzeit-Updates.
- **Wiederverbindung**: Der SSE-Client sollte eine automatische Wiederverbindung implementieren (`setTimeout(connect, 2000)` bei Fehlern).
- **Leichtes HTML**: Halte das Overlay-HTML schlank, da es bei jedem Start neu geladen wird.

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Plugin wird nicht erkannt | `plugin.json` fehlt oder ist ungültig | Prüfe das Manifest auf Gültigkeit |
| Plugin startet nicht | Port-Konflikt | Wähle einen anderen Port |
| Events kommen nicht an | Falsche Event-Subscriptions | Prüfe `event_subscriptions` im Manifest |
| `get_overlay_html()` fehlt | Methode nicht überschrieben | Implementiere `get_overlay_html()` |
| `PLUGIN_NAME` falsch | Stimmt nicht mit `plugin.json` überein | Korrigiere den Namen |
| GUI-Fenster öffnet nicht | pywebview nicht installiert | Installiere pywebview oder nutze die Browser-URL |
