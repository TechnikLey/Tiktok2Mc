# Konfiguration

Hooks können eine eigene Konfiguration haben, die im gleichen Format wie bei Plugins definiert wird.

## Konfigurationsdatei

Die `config.yaml` liegt im Hook-Verzeichnis:

```yaml
enabled: true
mode: deny-all
triggers:
  - "follow"
  - "like"
```

## Schema definieren

Definiere das Schema in der `hook.json`:

```json
{
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "mode",
        "type": "select",
        "default": "deny-all",
        "options": ["deny-all", "allow-only"],
        "label": "Filter Mode",
        "category": "General"
      },
      {
        "key": "triggers",
        "type": "array",
        "default": [],
        "item_schema": {
          "type": "string"
        },
        "label": "Triggers",
        "category": "General"
      }
    ]
  }
}
```

## Auf die Konfiguration zugreifen

Im Hook-Code greifst du über die API auf die Konfiguration zu:

```python
def register(api):
    cfg = api.get_hook_config("mein-hook")
    modus = cfg.get("mode", "deny-all")
    triggers = cfg.get("triggers", [])
```

## Automatische Generierung

Wie bei Plugins erzeugt das System automatisch eine `config.yaml` mit Standardwerten, wenn keine Datei existiert aber ein Schema definiert ist. Fehlende Felder werden ergänzt, ungültige Werte geheilt.
