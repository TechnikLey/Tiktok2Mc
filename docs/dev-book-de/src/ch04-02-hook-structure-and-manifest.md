# Hook-Struktur & Manifest

Jeder Hook lebt in einem eigenen Verzeichnis unter `src/hooks/<name>/`. Das `hook.json`-Manifest identifiziert ihn.

```
src/hooks/<name>/
├── hook.json          # Manifest (Pflicht)
├── main.py            # Hook-Code (Pflicht)
└── config.yaml        # Konfiguration (optional, wird automatisch erstellt)
```

## hook.json — Das Manifest

### Pflichtfelder

| Feld | Typ | Beschreibung | Beispiel |
|------|-----|--------------|----------|
| `name` | String | Eindeutiger Hook-Name (Kleinbuchstaben, Ziffern) | `"sprung"` |
| `version` | String | Semantische Version | `"1.0.0"` |
| `display_name` | String | Anzeigename | `"Supersprung"` |

### Wichtige optionale Felder

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `description` | String | Kurzbeschreibung |
| `author` | String | Entwickler-Name |
| `min_api_version` | String | Mindest-Hook-API-Version |
| `config_schema` | Objekt | Schema für die Hook-Konfiguration |
| `plugin` | String | Bei Plugin-gebündelten Hooks: der Plugin-Name |
| `enabled` | Boolean | Ob der Hook beim Start geladen wird (Default: `true`) |
| `update_url` | String | URL für Auto-Updates |

### Vollständiges Beispiel

```json
{
  "name": "sprung",
  "version": "1.0.0",
  "display_name": "Supersprung",
  "description": "Gibt allen Spieler Sprung-Boost",
  "author": "Dein Name",
  "min_api_version": "1.0.0",
  "enabled": true,
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "dauer",
        "type": "integer",
        "default": 10,
        "label": "Effektdauer (Sekunden)"
      }
    ]
  }
}
```

## main.py — Der Einstiegspunkt

Der Hook **muss** eine `register`-Funktion auf oberster Ebene exportieren:

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def handler(user, trigger, context):
        dauer = api.get_hook_config("sprung").get("dauer", 10)
        api.rcon_enqueue([f"effect give @a minecraft:jump_boost {dauer} 5 true"])

    api.register_action("superjump", handler)
```

### Wichtige Regeln

- Die Funktion **muss** `register` heißen (Groß-/Kleinschreibung beachten)
- Ohne `register` wird der Hook nicht geladen (Fehler: `HOOK_0007`)
- Erster `register_action`-Aufruf gewinnt — doppelte Namen überschreiben nicht
- Die Handler-Funktion muss drei Parameter akzeptieren: `(user, trigger, context)`

## Wie Hooks geladen werden

1. **Discovery**: `_discover_hook_dirs()` scannt `src/hooks/*/hook.json`
2. **Import-Prüfung**: AST-Check auf disallowed imports (siehe [Import-Beschränkungen](./ch04-05-import-restrictions.md))
3. **Import**: `importlib.import_module(module_name)` lädt die `main.py` des Hooks
4. **Register**: `module.register(api)` wird aufgerufen
5. **Flat vs. Tree**: Bei flachem Layout werden `src/hooks/` durchsucht; bei Tree-Layout auch Unterverzeichnisse

## Hooks aktivieren/deaktivieren

- **Über `config.yaml`**: Setze `enabled: false` im Hook-Verzeichnis
- **Über `hook.json`**: Setze `"enabled": false` im Manifest
- **Über die GUI**: Der API-Server steuert `data/hook_registry.json`

## Nächstes Kapitel

Die [Hook-API-Referenz](./ch04-03-hook-api.md) beschreibt alle verfügbaren Methoden.
