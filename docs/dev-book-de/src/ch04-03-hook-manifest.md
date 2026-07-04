# Hook-Manifest

Die `hook.json` beschreibt den Hook vollständig. Sie wird vom System beim Start ausgelesen.

## Aufbau

```json
{
  "name": "mein-hook",
  "version": "1.0.0",
  "display_name": "Mein Hook",
  "description": "Eine kurze Beschreibung",
  "author": "Dein Name",
  "min_api_version": "1.0.0",
  "capabilities": [],
  "plugin": "",
  "update_url": "",
  "depends_on": [],
  "config_schema": {
    "version": 1,
    "fields": []
  }
}
```

## Felder

| Feld | Beschreibung |
|---|---|
| `name` | Eindeutiger Hook-Name (erforderlich) |
| `version` | Semantische Version |
| `display_name` | Anzeigename für Benutzeroberflächen |
| `description` | Kurzbeschreibung |
| `author` | Entwickler des Hooks |
| `min_api_version` | Mindestversion der Hook-API |
| `capabilities` | Liste von Fähigkeiten für das System |
| `plugin` | Wenn der Hook zu einem Plugin gehört, der Plugin-Name |
| `update_url` | GitHub-API-URL für automatische Updates |
| `depends_on` | Liste von anderen Hooks, die benötigt werden |
| `config_schema` | Schema für die Konfiguration (gleiches Format wie bei Plugins) |

## Beispiel mit Schema

```json
{
  "name": "random",
  "version": "1.0.0",
  "display_name": "Random Trigger",
  "description": "Wählt einen zufälligen Trigger aus",
  "author": "TikTok2Mc",
  "min_api_version": "1.0.0",
  "capabilities": ["hook:random"],
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
        "item_schema": { "type": "string" },
        "label": "Triggers",
        "category": "General"
      }
    ]
  }
}
```
