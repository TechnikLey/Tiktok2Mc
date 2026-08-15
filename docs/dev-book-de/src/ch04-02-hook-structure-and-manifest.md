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
| `name` | String | Eindeutiger Hook-Name (Kleinbuchstaben, Ziffern, Bindestriche, Unterstriche) | `"sprung"` |
| `version` | String | Semantische Version | `"1.0.0"` |
| `display_name` | String | Anzeigename | `"Supersprung"` |

### Wichtige optionale Felder

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `description` | String | Kurzbeschreibung |
| `author` | String | Entwickler-Name |
| `min_api_version` | String | Mindest-Hook-API-Version (aktuell `1.0.0`, siehe `src/core/version.py`) |
| `capabilities` | Array | Liste von Fähigkeiten, z. B. `["hook:random"]` |
| `depends_on` | Array | Liste von Plugin-Namen, die aktiviert sein müssen |
| `plugin` | String | Bei Plugin-gebündelten Hooks: der Plugin-Name |
| `config_schema` | Objekt | Schema für die Hook-Konfiguration (siehe [Konfiguration](./ch03-03-configuration.md)) |
| `update_url` | String | URL für Auto-Updates, z. B. `"https://api.github.com/repos/TechnikLey/Tiktok2Mc/releases/latest"` |

### Vollständiges Beispiel

```json
{
  "name": "sprung",
  "version": "1.0.0",
  "display_name": "Supersprung",
  "description": "Gibt allen Spieler Sprung-Boost",
  "author": "Dein Name",
  "min_api_version": "1.0.0",
  "capabilities": ["hook:jump"],
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "dauer",
        "type": "integer",
        "default": 10,
        "min": 1,
        "max": 300,
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

    api.register_action("sprung", handler)
```

### Wichtige Regeln

- Die Funktion **muss** `register` heißen (Groß-/Kleinschreibung beachten)
- Ohne `register` wird der Hook nicht geladen (Fehler: `HOOK-0007`)
- Erster `register_action`-Aufruf gewinnt — doppelte Namen überschreiben nicht
- Die Handler-Funktion muss drei Parameter akzeptieren: `(user, trigger, context)`

## Wie Hooks geladen werden

1. **Discovery**: `_discover_hook_dirs()` scannt `src/hooks/*/hook.json`
2. **Import-Prüfung**: AST-Check auf disallowed imports (siehe [Import-Beschränkungen](./ch04-05-import-restrictions.md))
3. **Import**: Der Hook wird über `importlib.util.spec_from_file_location()` + `module_from_spec()` geladen (nicht `importlib.import_module`), was direkte Dateipfad-Importe ohne Paketstruktur erlaubt.
4. **Register**: `module.register(api)` wird aufgerufen
5. **Flat vs. Tree**: Bei flachem Layout werden `src/hooks/` durchsucht; bei Tree-Layout auch Unterverzeichnisse

## Hooks aktivieren/deaktivieren

- **Über die GUI**: Der API-Server steuert `data/hook_registry.json`
- **Über die API**: `POST /api/v1/hooks/<name>/enable` bzw. `.../disable`

## Nächstes Kapitel

Die [Hook-API-Referenz](./ch04-03-hook-api.md) beschreibt alle verfügbaren Methoden.
