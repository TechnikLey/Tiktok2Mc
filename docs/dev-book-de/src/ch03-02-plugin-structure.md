# Plugin-Struktur

Jedes Plugin lebt in einem eigenen Verzeichnis unter `src/plugins/<name>/`. Das System erkennt ein Plugin an der Datei `plugin.json` und startet den in `entry_point` angegebenen Subprozess.

## Verzeichnisstruktur

```
src/plugins/<name>/
├── plugin.json          # Manifest (Pflicht)
├── main.py              # Plugin-Code (Pflicht)
├── config.yaml          # Konfiguration (Pflicht)
├── hooks/               # Optional: Eigene Hooks im Plugin
├── version.txt          # Optional: Versionsinformationen
└── README.md            # Optional: Dokumentation
```

## Pflichtdateien im Detail

### `plugin.json` – Das Manifest

Dies ist die Erkennungsdatei des Plugins. Das System scannt beim Start `src/plugins/*/plugin.json` und registriert jedes gefundene Plugin.

Ohne diese Datei wird dein Plugin **nicht erkannt** – das System weiß nicht, dass es existiert.

Die `plugin.json` enthält:

- **Metadaten**: Name, Version, Autor, Beschreibung
- **Einstiegspunkt**: Welche Datei wo gestartet werden soll (`entry_point`)
- **API-Version**: Welche Plugin-API das Plugin erwartet (`min_api_version`)
- **Abhängigkeiten**: Welche anderen Plugins aktiviert sein müssen (`depends_on`)
- **Konfigurationsschema**: Welche Konfigurationsfelder erwartet werden (`config_schema`)
- **Event-Abonnements**: Welche TikTok-Events empfangen werden sollen (`event_subscriptions`)

Siehe [Plugin-Manifest](./ch03-03-plugin-manifest.md) für das vollständige Format.

### `main.py` – Der Einstiegspunkt

Diese Datei wird als Subprozess gestartet: `python src/plugins/<name>/main.py`. Sie muss enthalten:

1. Eine Klasse, die von `BasePlugin` erbt
2. Das Klassenattribut `PLUGIN_NAME`
3. Die Methode `get_overlay_html()`
4. Einen `if __name__ == "__main__"`-Block, der `run()` aufruft

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"

    def get_overlay_html(self) -> str:
        return "<html><body>Hallo</body></html>"

if __name__ == "__main__":
    MeinPlugin().run()
```

**Warum `if __name__ == "__main__"`?** Das System startet diese Datei als Subprozess. Python führt die Datei dann von oben nach unten aus. Ohne diesen Block würde nur die Klassendefinition gelesen, aber niemals eine Instanz erzeugt oder `run()` aufgerufen. Der Subprozess würde einfach beenden und das Plugin wäre sofort tot.

### `config.yaml` – Die Konfiguration

Enthält alle benutzerspezifischen Einstellungen des Plugins. Wird automatisch aus dem `config_schema` in der `plugin.json` befüllt, falls nicht vorhanden oder wenn Felder fehlen (Healing).

```yaml
enabled: true
milestones:
  - 10
  - 50
theme:
  background: "#000000"
  text: "#ff4444"
```

Zugriff im Code über `self.config` (siehe [Konfiguration](./ch03-04-configuration.md)).

## Optionale Dateien

### `hooks/` – Plugin-gebündelte Hooks

Ein Verzeichnis für Hooks, die zusammen mit dem Plugin ausgeliefert werden. Das System erkennt sie automatisch unter `src/plugins/<name>/hooks/*/hook.json`.

Siehe [Plugin-gebündelte Hooks](./ch04-07-plugin-bundled-hooks.md).

### `version.txt` – Versionsinformationen

Wird von `create_plugin.py` erzeugt, enthält die Tool-Version und die Update-URL:

```
version: 1.0.0
update_url: https://api.github.com/repos/.../releases/latest
```

### `README.md` – Dokumentation

Eine lesbare Beschreibung des Plugins für Benutzer. Wird nicht vom System ausgewertet.

## Namenskonventionen

| Element | Konvention | Beispiel | Erklärung |
|---|---|---|---|
| Plugin-Name (`plugin.json` `name`) | Kebab-Case | `mein-plugin` | Wird für API-Endpunkte und Identifikation verwendet |
| Verzeichnisname | Kebab-Case ohne Bindestriche oder Kleinbuchstaben | `meinplugin` | Sollte dem Plugin-Namen ähneln, aber ohne Bindestriche (Vereinfachung) |
| `PLUGIN_NAME` (Python) | String, exakt wie `name` | `"mein-plugin"` | Muss mit `plugin.json`-Namen übereinstimmen |
| `entry_point` | Relativer Pfad | `src/plugins/meinplugin/main.py` | Wird als `python <entry_point>` gestartet |
| `display_name` | Titel | `"Mein Plugin"` | Anzeigename für Benutzeroberflächen |

**Konsequenz bei falschen Namen**: Wenn `PLUGIN_NAME` in `main.py` vom `name`-Feld in `plugin.json` abweicht, wird das Plugin zwar registriert, aber der Subprozess startet nicht korrekt. Das System erwartet, dass der Subprozess sich als `PLUGIN_NAME` authentifiziert.

## Beziehung zwischen den Dateien

```
plugin.json (name: "mein-plugin")  ←  main.py (PLUGIN_NAME = "mein-plugin")
       │                                     │
       │ entry_point:                         │ run() registriert
       │ "src/plugins/meinplugin/main.py"     │ Overlay per API
       │                                     │
       ▼                                     ▼
System startet:                       Plugin startet Polling
python src/plugins/meinplugin/main.py  und wartet auf Befehle
       │
       │ config_schema definiert Format
       ▼
config.yaml (wird automatisch validiert/repariert)
```

Die drei Dateien (`plugin.json`, `main.py`, `config.yaml`) sind die Mindestausstattung. Ohne eine davon funktioniert das Plugin nicht.
