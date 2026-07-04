# Plugin-Struktur

Jedes Plugin lebt in einem eigenen Verzeichnis unter `src/plugins/<name>/`. Die folgende Struktur ist verbindlich:

## Verzeichnisstruktur

```
src/plugins/<name>/
├── plugin.json          # Manifest (Pflicht)
├── main.py              # Plugin-Code (Pflicht)
├── config.yaml          # Konfiguration (Pflicht)
├── hooks/               # Optional: Eigene Hooks im Plugin
└── README.md            # Optional: Dokumentation
```

### Pflichtdateien

**`plugin.json`** – Das Manifest. Es enthält Metadaten, die Einstiegspunkt-Definition, Abhängigkeiten und das Konfigurationsschema. Das System erkennt Plugins anhand dieser Datei.

**`main.py`** – Der Einstiegspunkt. Enthält die Plugin-Klasse, die von `BasePlugin` erbt. Das System startet diese Datei als Subprozess.

**`config.yaml`** – Die Konfiguration. Enthält alle benutzerspezifischen Einstellungen für das Plugin. Wird automatisch aus dem Schema in `plugin.json` befüllt, falls nicht vorhanden.

### Optionale Dateien

**`hooks/`** – Ein Verzeichnis für Hooks, die im Bundle mit dem Plugin ausgeliefert werden. Siehe [Plugin-gebündelte Hooks](./ch04-07-plugin-bundled-hooks.md).

**`README.md`** – Eine lesbare Beschreibung des Plugins. Wird nicht vom System ausgewertet.

## Namenskonventionen

- Der Plugin-Name in `plugin.json` (Feld `name`) verwendet **Kebab-Case**: `mein-plugin`
- Der Verzeichnisname sollte dem Plugin-Namen entsprechen (ohne Bindestriche, z. B. `meinplugin`)
- Der `entry_point` in `plugin.json` zeigt auf die `main.py` relativ zum Projektstamm
