# Konfiguration

Jedes Plugin hat eine eigene Konfiguration in `config.yaml`. Das System stellt sicher, dass die Konfiguration immer gültig ist – selbst wenn die Datei fehlt oder beschädigt ist.

## Die config.yaml

Die `config.yaml` enthält alle benutzerspezifischen Einstellungen des Plugins:

```yaml
enabled: true
milestones:
  - 10
  - 50
  - 100
theme:
  background: "#000000"
  text: "#ff4444"
```

## Automatische Generierung

Wenn keine `config.yaml` existiert, aber ein `config_schema` in der `plugin.json` definiert ist, erzeugt das System automatisch eine Konfiguration mit den Standardwerten aus dem Schema.

Fehlende Felder werden ergänzt. Ungültige Werte werden durch die Standardwerte ersetzt ("Healing").

## Das Konfigurationsschema

Definiere in der `plugin.json` unter `config_schema`, welche Felder dein Plugin erwartet:

```json
{
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "milestones",
        "type": "array",
        "default": [],
        "item_schema": {
          "type": "integer",
          "min": 1
        },
        "label": "Milestones",
        "help": "Schwellenwerte für Meilenstein-Events",
        "category": "Events"
      },
      {
        "key": "theme.background",
        "type": "color",
        "default": "#000000",
        "label": "Hintergrundfarbe",
        "category": "Theme"
      }
    ]
  }
}
```

### Unterstützte Feldtypen

| Typ | Beschreibung |
|---|---|
| `boolean` | Wahr/Falsch-Wert |
| `integer` | Ganze Zahl (mit optionalem `min`, `max`) |
| `string` | Text |
| `color` | Hex-Farbe (z. B. `#ff4444`) |
| `select` | Auswahl aus einer Liste von Optionen |
| `array` | Liste von Elementen (mit `item_schema`) |

### Feld-Eigenschaften

| Eigenschaft | Beschreibung |
|---|---|
| `key` | Der Schlüssel in der Konfiguration (Punkte für Verschachtelung: `theme.background`) |
| `type` | Der Datentyp |
| `default` | Standardwert, falls nicht gesetzt |
| `label` | Anzeigename für Benutzeroberflächen |
| `help` | Hilfetext |
| `category` | Kategorie für die Gruppierung in der GUI |
| `advanced` | Bei `true` in der erweiterten Ansicht verstecken |

## Auf die Konfiguration zugreifen

Im Plugin-Code greifst du über die `config`-Eigenschaft auf die Konfiguration zu:

```python
cfg = self.config
milestones = cfg.get("milestones", [])
bg_color = cfg.get("theme", {}).get("background", "#000000")
```

> [!NOTE]
> Die `config`-Eigenschaft gibt eine **Kopie** der Konfiguration zurück. Änderungen daran wirken sich nicht auf die gespeicherte Konfiguration aus.
