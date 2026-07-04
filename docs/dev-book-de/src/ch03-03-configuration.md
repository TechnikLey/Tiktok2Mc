# Konfiguration

Jedes Plugin hat eine eigene Konfiguration in der `config.yaml`. Das System stellt sicher, dass die Konfiguration immer gültig ist — selbst wenn die Datei fehlt oder beschädigt ist.

## Die config.yaml

```yaml
enabled: true
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
| `string` | Text (optional mit `pattern`-Regex) |
| `color` | Hex-Farbe, z. B. `#ff4444` |
| `select` | Auswahl aus `options`-Liste |
| `array` | Liste von Elementen (mit `item_schema`) |

### Feldeigenschaften

| Eigenschaft | Beschreibung |
|-------------|--------------|
| `key` | Schlüssel in der Config (Punkte für Verschachtelung: `theme.background`) |
| `type` | Datentyp |
| `default` | Standardwert |
| `label` | Anzeigename |
| `help` | Hilfetext |
| `category` | Kategorie für GUI-Gruppierung |
| `advanced` | Bei `true` in erweiterter Ansicht verstecken |

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

## Besonderes Feld: `enabled`

Das Feld `enabled` in der `config.yaml` steuert, ob das Plugin beim Systemstart automatisch aktiviert wird. Es wird vom System ausgewertet, nicht vom Plugin-Code.

## Nächstes Kapitel

Die vollständige [Plugin-API-Referenz](./ch03-04-plugin-api.md) beschreibt alle Methoden von `BasePlugin`.
