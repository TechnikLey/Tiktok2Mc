# Quickstart

In 5 Minuten erstellst du dein erstes Plugin und siehst, wie es im System lebt.

## Voraussetzungen

- Python 3.12+ installiert
- TikTok2Mc geklont: `git clone https://github.com/TechnikLey/Tiktok2Mc.git`
- Abhängigkeiten installiert: `pip install -r requirements.txt`

> [!NOTE]
> **Linux**: Für den Build mit PyInstaller muss `binutils` installiert sein:
>
> ```bash
> sudo apt install binutils   # Debian / Ubuntu
> sudo pacman -S binutils     # Arch
> sudo dnf install binutils   # Fedora
> ```

## 1. Plugin erstellen

```bash
python create_plugin.py
```

Das Skript fragt nach einem Namen (a-z, 0-9, Bindestriche). Beispiel: `mein-plugin`

Nach der Erstellung liegt das Plugin unter `src/plugins/mein-plugin/`:

```
src/plugins/mein-plugin/
├── plugin.json         # Manifest
├── main.py             # Einstiegspunkt
├── config.yaml         # Konfiguration
├── version.txt         # Version
└── README.md           # Dokumentation
```

## 2. Plugin-Code schreiben

Ersetze den Inhalt von `src/plugins/mein-plugin/main.py`:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"

    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_tiktok_event)

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        if event_type == "tiktok.follow":
            log.info(f"{user} folgt jetzt!")

    def get_overlay_html(self) -> str:
        return "<html><body>Mein Plugin läuft!</body></html>"

if __name__ == "__main__":
    MeinPlugin().run()
```

**Wichtig**: Der Subprozess startet `main.py` als Python-Datei. Der `if __name__`-Block sorgt dafür, dass `run()` aufgerufen wird — ohne ihn beendet sich der Prozess sofort.

## 3. Event-Abonnement eintragen

Füge in `src/plugins/mein-plugin/plugin.json` das Feld `event_subscriptions` hinzu:

```json
{
  "name": "mein-plugin",
  "event_subscriptions": ["tiktok.follow", "tiktok.gift"]
}
```

Ohne diese Deklaration erhält dein Plugin keine TikTok-Events.

## 4. System starten

```bash
python run.py
```

Startet den API-Server unter `http://127.0.0.1:29185`. Der Plugin-Watcher registriert automatisch alle Plugins aus `src/plugins/`.

## 5. Plugin aktivieren

```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/mein-plugin/enable
```

Der Supervisor startet daraufhin den Subprozess: `python src/plugins/mein-plugin/main.py`

Bestätigung in der Konsole: Das Plugin loggt, dass es gestartet ist.

## 6. Test-Event senden

```bash
python tests/send_trigger.py --event tiktok.follow --user TestUser
```

In der Konsole sollte erscheinen: `TestUser folgt jetzt!`

## 7. Plugin deaktivieren

```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/mein-plugin/disable
```

Das System beendet den Subprozess.

## Fehler beheben

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Plugin nicht erkannt | `plugin.json` fehlt oder ungültig | JSON-Syntax prüfen |
| Plugin startet nicht | `entry_point` falsch | Pfad in `plugin.json` prüfen |
| Events kommen nicht an | `event_subscriptions` fehlt | Feld in `plugin.json` ergänzen |
| `PLUGIN_NAME` falsch | Stimmt nicht mit `name` überein | Beide auf gleichen Wert setzen |

## Nächste Schritte

Du hast dein erstes Plugin in Betrieb. Lies [Grundkonzepte](./ch02-00-core-concepts.md) für die Architektur oder steige direkt in die [Plugin-Entwicklung](./ch03-00-plugins.md) ein.
