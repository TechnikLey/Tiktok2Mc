# Plugin-Struktur & Manifest

Jedes Plugin lebt in einem eigenen Verzeichnis unter `src/plugins/<name>/`. Das System erkennt es an der `plugin.json`.

## Verzeichnisstruktur

```
src/plugins/<name>/
├── plugin.json          # Manifest (Pflicht)
├── main.py              # Plugin-Code (Pflicht)
├── config.yaml          # Konfiguration (optional, wird automatisch erstellt)
├── hooks/               # Optional: Plugin-gebündelte Hooks
├── version.txt          # Optional: Vom Scaffolder erzeugt
└── README.md            # Optional: Dokumentation
```

## plugin.json — Das Manifest

Dies ist die Erkennungsdatei. Der `PluginWatcher` scannt beim Start `src/plugins/*/plugin.json`.

### Pflichtfelder

| Feld | Beschreibung | Beispiel |
|------|--------------|----------|
| `name` | Eindeutiger Name (Kleinbuchstaben, Ziffern, Bindestriche). Regex: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` | `"mein-plugin"` |
| `version` | Semantische Version | `"1.0.0"` |
| `entry_point` | Pfad zur `main.py` relativ zum Projektstamm | `"src/plugins/meinplugin/main.py"` |
| `display_name` | Anzeigename für die GUI | `"Mein Plugin"` |

### Wichtige optionale Felder

| Feld | Beschreibung |
|------|--------------|
| `description` | Kurzbeschreibung (1-2 Sätze) |
| `author` | Entwickler-Name |
| `min_api_version` | Mindestversion der Plugin-API. Bei Inkompatibilität wird das Plugin nicht gestartet. |
| `event_subscriptions` | Liste von TikTok-Event-Typen, die das Plugin empfangen will. **Ohne dieses Feld keine TikTok-Events.** |
| `depends_on` | Liste von Plugin-Namen, die aktiviert sein müssen |
| `capabilities` | Freie Schlagwörter für das System, z. B. `["timer:countdown"]` |
| `config_schema` | Schema für die Konfiguration (siehe [Konfiguration](./ch03-03-configuration.md)) |
| `comment_handler` | Deklaration, dass das Plugin auf TikTok-Kommentare reagiert |
| `update_url` | GitHub-API-URL für Auto-Updates |

### Vollständiges Beispiel

```json
{
  "name": "mein-plugin",
  "version": "1.0.0",
  "entry_point": "src/plugins/meinplugin/main.py",
  "display_name": "Mein Plugin",
  "description": "Reagiert auf Follows und Gifts",
  "author": "Dein Name",
  "min_api_version": "1.0.0",
  "event_subscriptions": ["tiktok.follow", "tiktok.gift"],
  "capabilities": ["mein-plugin:counter"],
  "depends_on": [],
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "schwellwert",
        "type": "integer",
        "default": 10,
        "label": "Schwellwert",
        "category": "Events"
      }
    ]
  }
}
```

## main.py — Der Einstiegspunkt

Das System startet den Subprozess mit: `python src/plugins/<name>/main.py`

Die Datei muss enthalten:

1. Eine Klasse, die von `BasePlugin` erbt
2. Das Attribut `PLUGIN_NAME` (muss mit `name` in `plugin.json` übereinstimmen)
3. Die Methode `get_overlay_html()`
4. Einen `if __name__ == "__main__"`-Block

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"

    def get_overlay_html(self) -> str:
        return "<html><body>Aktiv</body></html>"

if __name__ == "__main__":
    MeinPlugin().run()
```

**Ohne den `if __name__`-Block** würde der Subprozess nur die Klassendefinition lesen, keine Instanz erzeugen und sofort beenden.

## Namenskonventionen

| Element | Konvention | Beispiel |
|---------|------------|----------|
| `name` in `plugin.json` | Kebab-Case | `mein-plugin` |
| Verzeichnisname | Nur Kleinbuchstaben, Ziffern (keine Bindestriche) | `meinplugin` |
| `PLUGIN_NAME` in Python | Exakt wie `name` in plugin.json | `"mein-plugin"` |
| `entry_point` | Relativer Pfad | `src/plugins/meinplugin/main.py` |

**Konsequenz bei Abweichung**: Das Plugin wird zwar registriert, der Subprozess startet nicht korrekt.

## Wie das System die plugin.json verarbeitet

1. **Scan**: `PluginWatcher` scannt `src/plugins/*/plugin.json` (auch zur Laufzeit)
2. **Validierung**: JSON wird geparst, Pflichtfelder geprüft
3. **Registrierung**: Daten werden im API-Server in der `PluginRegistry` gespeichert (`data/api_plugin_registry.json`)
4. **Aktivierung**: Erst beim Enable (per API oder GUI) wird der Subprozess gestartet
5. **Signal-Datei**: Der API-Server schreibt `core/runtime/plugin_start_<name>`. Der Supervisor startet daraufhin den Prozess.

## Nächstes Kapitel

Im nächsten Kapitel lernst du die [Konfiguration](./ch03-03-configuration.md) im Detail.
