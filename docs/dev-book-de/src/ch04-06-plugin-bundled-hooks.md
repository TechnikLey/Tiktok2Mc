# Plugin-gebündelte Hooks

Hooks können im Bundle mit einem Plugin ausgeliefert werden. Dies ist nützlich, wenn ein Plugin `$`-Befehle bereitstellen möchte, die mit dem Plugin interagieren.

## Verzeichnisstruktur

```
src/plugins/<plugin>/
├── plugin.json
├── main.py
├── config.yaml
└── hooks/
    └── <hook-name>/
        ├── hook.json
        ├── main.py
        └── config.yaml
```

## Hook-Manifest für Plugin-Bundles

Setze das `plugin`-Feld in der `hook.json`:

```json
{
  "name": "spotify-control",
  "version": "1.0.0",
  "display_name": "Spotify Control",
  "plugin": "spotify",
  "min_api_version": "1.0.0",
  "config_schema": {
    "version": 1,
    "fields": []
  }
}
```

## Vorteile

- **Zusammengehörigkeit**: Plugin und Hook werden zusammen installiert und aktualisiert.
- **Integration**: Der Hook kann mit dem Plugin über die Event-API kommunizieren.
- **Einheitliche Versionierung**: Plugin und Hook teilen sich den Update-Zyklus.

## Kommunikation zwischen Hook und Plugin

Der Hook kann Events auslösen, die das Plugin über den Event-Command-Mapper empfängt:

```python
# Im Hook
api.rcon_enqueue([f"say Spotify-Befehl von {user}!"])

# Über den Hook wird ein Event ausgelöst, das der Event-Command-Mapper
# an das Plugin weiterleitet. Siehe [Event-Command-Mapper](./ch05-02-event-command-mapper.md) für Details.
```

## Erkennung

Das System erkennt Plugin-gebündelte Hooks automatisch. Sie werden im Verzeichnis `src/plugins/*/hooks/` gesucht und mit dem entsprechenden Plugin verknüpft.
