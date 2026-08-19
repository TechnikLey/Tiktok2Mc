# Konfiguration

Jedes Plugin hat eine eigene Konfiguration in der `config.yaml`. Das System stellt sicher, dass die Konfiguration immer gültig ist — selbst wenn die Datei fehlt oder beschädigt ist.

## Die config.yaml

```yaml
schwellwert: 10
theme:
  background: "#000000"
  text: "#ff4444"
```

## Automatische Generierung

Wenn keine `config.yaml` existiert, aber ein `config_schema` in der `plugin.json` definiert ist, erzeugt das System automatisch eine Konfiguration mit den Standardwerten.

Fehlende Felder werden ergänzt. Ungültige Werte werden durch Standardwerte ersetzt ("Healing").

## Das Konfigurationsschema

Definiere in der `plugin.json` unter `config_schema`, welche Felder dein Plugin erwartet:

```json
{
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "schwellwert",
        "type": "integer",
        "default": 10,
        "min": 1,
        "label": "Schwellwert",
        "help": "Bei diesem Wert wird ein Event ausgelöst",
        "category": "Events"
      },
      {
        "key": "theme.background",
        "type": "color",
        "default": "#000000",
        "label": "Hintergrundfarbe",
        "category": "Theme"
      },
      {
        "key": "api_key",
        "type": "string",
        "default": "",
        "secret": true,
        "label": "API-Key",
        "help": "Wird in der GUI maskiert",
        "category": "Authentifizierung"
      },
      {
        "key": "modus",
        "type": "select",
        "default": "normal",
        "options": ["normal", "turbo", "langsam"],
        "label": "Modus",
        "category": "General"
      },
      {
        "key": "milestones",
        "type": "array",
        "default": [10, 50, 100],
        "item_schema": {"type": "integer", "min": 1},
        "label": "Milestones",
        "category": "Events"
      }
    ]
  }
}
```

### Unterstützte Feldtypen

| Typ | Beschreibung |
|-----|--------------|
| `boolean` | Wahr/Falsch |
| `integer` | Ganze Zahl (optional mit `min`, `max`) |
| `number` | Fließkommazahl (optional mit `min`, `max`) |
| `string` | Text (optional mit `pattern`-Regex) |
| `color` | Hex-Farbe, z. B. `#ff4444` |
| `select` | Auswahl aus `options`-Liste. Das Feld `options` ist ein Pflichtfeld für diesen Typ. |
| `array` | Liste von Elementen (mit `item_schema`). Das Feld `item_schema` definiert Typ und Validierung der enthaltenen Elemente. |
| `object` | Verschachteltes Objekt (mit `item_schema` für die Felddefinitionen) |

### Feldeigenschaften

| Eigenschaft | Typ | Beschreibung |
|-------------|-----|--------------|
| `key` | String | Schlüssel in der Config (Punkte für Verschachtelung: `theme.background`) |
| `type` | String | Datentyp (siehe unterstützte Typen oben) |
| `default` | Any | Standardwert, wenn das Feld in der Config fehlt |
| `label` | String | Anzeigename in der GUI |
| `help` | String | Hilfetext / Tooltip |
| `category` | String | Kategorie für GUI-Gruppierung (Standard: `"General"`) |
| `advanced` | Boolean | Bei `true` in der erweiterten Ansicht verstecken (Standard: `false`) |
| `required` | Boolean | Bei `true` muss das Feld gesetzt sein (Standard: `false`) |
| `secret` | Boolean | Bei `true` wird der Wert in der GUI maskiert (z. B. für API-Keys, Standard: `false`) |
| `min` | Integer | Minimalwert (nur für `integer`) |
| `max` | Integer | Maximalwert (nur für `integer`) |
| `options` | Array | Erlaubte Werte (nur für `select`) |
| `item_schema` | Objekt | Schema für Array-Elemente (nur für `array`). Unterstützt `type`, `min`, `max` und `options`. |
| `widget` | String | GUI-Widget-Hinweis, z. B. `"textarea"` oder `"color"` |

## Zugriff im Code

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        cfg = self.config

        self._schwellwert = cfg.get("schwellwert", 10)
        self._modus = cfg.get("modus", "normal")
        bg = cfg.get("theme", {}).get("background", "#000000")
```

> [!NOTE]
> `self.config` gibt eine **Kopie** der Konfiguration zurück. Änderungen wirken sich nicht auf die gespeicherte Datei aus.

## Plugin-Aktivierung

Ob ein Plugin läuft, wird über die GUI, die interaktive Konsole (`enable <name>` / `disable <name>`) bzw. `POST /api/v1/plugins/{name}/enable` / `disable` gesteuert und in `data/api_plugin_registry.json` gespeichert. Das Plugin aktiviert sich also nicht selbst über seine Config. Plugins sind standardmäßig deaktiviert und müssen vom Benutzer explizit aktiviert werden.

## Nächstes Kapitel

Die vollständige [Plugin-API-Referenz](./ch03-04-plugin-api.md) beschreibt alle Methoden von `BasePlugin`.
