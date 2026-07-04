# Hook-Konfiguration

Konfiguration für Hooks wird in der `config.yaml` im Hook-Verzeichnis gespeichert und durch das `config_schema` in der `hook.json` definiert.

## Schema definieren

In der `hook.json` unter `config_schema`:

```json
{
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "dauer",
        "type": "integer",
        "default": 10,
        "label": "Effektdauer (Sekunden)",
        "help": "Wie lange der Effekt anhält",
        "category": "Effekte"
      },
      {
        "key": "farbe",
        "type": "color",
        "default": "#ff4444",
        "label": "Effektfarbe",
        "category": "Effekte"
      },
      {
        "key": "modus",
        "type": "select",
        "default": "normal",
        "options": ["normal", "verstärkt"],
        "label": "Modus",
        "category": "General"
      }
    ]
  }
}
```

Unterstützte Feldtypen: `boolean`, `integer`, `string`, `color`, `select`

## Automatische Generierung

Fehlt die `config.yaml`, wird sie beim ersten Start automatisch aus dem Schema generiert (mit Default-Werten). Fehlende oder ungültige Felder werden repariert ("Healing").

## Zugriff im Hook

```python
def register(api: HookAPI):
    def handler(user, trigger, context):
        cfg = api.get_hook_config("sprung")
        dauer = cfg.get("dauer", 10)
        modus = cfg.get("modus", "normal")

        if modus == "verstärkt":
            dauer *= 2

        api.rcon_enqueue([f"effect give @a jump_boost {dauer} 5 true"])

    api.register_action("superjump", handler)
```

## config.yaml Speicherort

```
src/hooks/<name>/config.yaml
```

Bei Plugin-gebündelten Hooks:

```
src/plugins/<plugin>/hooks/<name>/config.yaml
```

## Nächstes Kapitel

Lerne die [Import-Beschränkungen](./ch04-05-import-restrictions.md) für Hooks kennen.
