# Dein erstes Plugin

In diesem Tutorial erstellst du dein erstes Plugin. Das Plugin wird auf TikTok-Follow-Events reagieren und eine Nachricht an Minecraft senden.

## Plugin erstellen

Das Projekt enthält ein Skript, das die Grundstruktur für ein Plugin erzeugt:

```bash
python create_plugin.py
```

Das Skript fragt nach:

- **Plugin-Name**: Nur Kleinbuchstaben und Ziffern, z. B. `hallo`
- **Update-URL**: Optional, für spätere Updates

Nach der Erstellung findest du dein Plugin unter `src/plugins/hallo/` mit folgender Struktur:

```
src/plugins/hallo/
├── plugin.json
├── main.py
├── config.yaml
├── version.txt
└── README.md
```

## Plugin-Code schreiben

Öffne `src/plugins/hallo/main.py` und ersetze den Inhalt:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class HalloPlugin(BasePlugin):
    PLUGIN_NAME = "hallo"

    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_tiktok_event)
        self._last_user = ""

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        if event_type == "tiktok.follow":
            self._last_user = user
            log.info(f"{user} folgt jetzt!")

    def get_overlay_html(self) -> str:
        return "<html><body>Hallo Plugin!</body></html>"

if __name__ == "__main__":
    HalloPlugin().run()
```

## Manifest anpassen

Öffne `src/plugins/hallo/plugin.json` und passe es an:

```json
{
  "name": "hallo",
  "version": "1.0.0",
  "entry_point": "src/plugins/hallo/main.py",
  "display_name": "Hallo Plugin",
  "description": "Mein erstes Plugin",
  "author": "Dein Name",
  "min_api_version": "1.0.0",
  "capabilities": [],
  "depends_on": [],
  "config_schema": {
    "version": 1,
    "fields": []
  }
}
```

## Plugin testen

Starte das System und aktiviere das Plugin:

1. Starte TikTok2Mc: `python run.py`
2. Das Plugin wird automatisch vom System erkannt.
3. Aktiviere es über die API oder warte, bis der Plugin-Watcher es registriert hat.
4. Sende einen Test-Trigger (siehe [Fehlerbehebung](./troubleshooting.md) im Anhang).

## Nächste Schritte

Herzlichen Glückwunsch! Du hast dein erstes Plugin erstellt. Im nächsten Kapitel lernst du die [Plugin-Struktur](./ch03-02-plugin-structure.md) im Detail kennen.
