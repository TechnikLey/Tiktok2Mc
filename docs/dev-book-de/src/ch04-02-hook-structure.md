# Hook-Struktur

Jeder Hook lebt in einem eigenen Verzeichnis. Es gibt zwei mögliche Speicherorte:

- **Hauptverzeichnis**: `src/hooks/<name>/`
- **Plugin-gebündelt**: `src/plugins/<plugin>/hooks/<name>/`

## Verzeichnisstruktur

```
<hooks-verzeichnis>/<name>/
├── hook.json          # Manifest (Pflicht)
├── main.py            # Hook-Code mit register()-Funktion (Pflicht)
└── config.yaml        # Konfiguration (optional, wird automatisch erstellt)
```

### hook.json

Das Manifest mit Metadaten. Wird vom System beim Start ausgewertet. Siehe [Hook-Manifest](./ch04-03-hook-manifest.md).

### main.py

Der Einstiegspunkt. Muss eine `register(api)`-Funktion auf oberster Ebene definieren.

### config.yaml

Die Konfiguration. Wird automatisch aus dem `config_schema` in der `hook.json` erstellt, falls nicht vorhanden.

## Namenskonventionen

- Der Hook-Name in `hook.json` (Feld `name`) verwendet **Kebab-Case** oder einen einzelnen Begriff
- Der Action-Name für `$`-Befehle sollte kurz und beschreibend sein
- Actions werden über `api.register_action(name, handler)` registriert

## Unterschied zu Plugins

| Aspekt | Hook | Plugin |
|---|---|---|
| Prozess | Läuft im Bridge-Prozess | Eigener Subprozess |
| Schnittstelle | `register(api)`-Funktion | Klasse, die von `BasePlugin` erbt |
| Kommunikation | Direkter Funktionsaufruf | HTTP-API |
| Konfiguration | Über `api.get_hook_config()` | Über `self.config` |
| Anwendungsfall | Einfache `$`-Befehle | Komplexe Erweiterungen mit GUI |
