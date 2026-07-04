# Plugin-Manifest

Die `plugin.json` ist das Herzstück jedes Plugins. Sie beschreibt das Plugin vollständig und wird vom System beim Start ausgewertet.

## Aufbau

```json
{
  "name": "mein-plugin",
  "version": "1.0.0",
  "entry_point": "src/plugins/meinplugin/main.py",
  "display_name": "Mein Plugin",
  "description": "Eine kurze Beschreibung",
  "author": "Dein Name",
  "homepage": "https://github.com/...",
  "min_api_version": "1.0.0",
  "capabilities": ["mein-plugin:feature"],
  "depends_on": [],
  "auto_enable": false,
  "update_url": "https://api.github.com/.../releases/latest",
  "comment_handler": {
    "prefix": "$",
    "enabled": false
  },
  "config_schema": {
    "version": 1,
    "fields": []
  }
}
```

## Pflichtfelder

| Feld | Beschreibung |
|---|---|
| `name` | Eindeutiger Plugin-Name in Kebab-Case. Erlaubt: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` |
| `version` | Semantische Version des Plugins |
| `entry_point` | Pfad zur `main.py` relativ zum Projektstamm |
| `display_name` | Anzeigename für Benutzeroberflächen |
| `min_api_version` | Mindestversion der Plugin-API, die das Plugin benötigt |

## Optionale Felder

| Feld | Beschreibung |
|---|---|
| `description` | Kurzbeschreibung des Plugins |
| `author` | Name des Entwicklers |
| `homepage` | Projekt-Website oder Repository |
| `capabilities` | Liste von Fähigkeiten für EventBus-Routing |
| `depends_on` | Liste von Plugin-Namen, die aktiviert sein müssen |
| `auto_enable` | Bei `true` wird das Plugin automatisch aktiviert |
| `update_url` | GitHub-API-URL für automatische Updates |
| `comment_handler` | Chat-Command-Konfiguration für TikTok-Kommentare |
| `config_schema` | Schema für die Konfigurationsoberfläche |

## Abhängigkeiten (`depends_on`)

Wenn dein Plugin andere Plugins benötigt, liste sie hier auf:

```json
{
  "depends_on": ["timer", "win-counter"]
}
```

Das System startet Plugins in der richtigen Reihenfolge und verhindert die Aktivierung eines Plugins, wenn seine Abhängigkeiten nicht erfüllt sind.

## Capabilities

Capabilities sind frei definierbare Schlagwörter, die das Event-Routing unterstützen:

```json
{
  "capabilities": ["death-counter:count", "death-counter:milestones"]
}
```

## Event-Subscriptions

Um TikTok-Events zu empfangen, musst du im Manifest deklarieren, welche Events du abonnieren möchtest:

```json
{
  "event_subscriptions": ["tiktok.gift", "tiktok.*"]
}
```

Wildcards werden unterstützt: `tiktok.*` abonniert alle TikTok-Events.

## Comment Handler

Falls dein Plugin auf TikTok-Kommentare mit einem bestimmten Präfix reagiert:

```json
{
  "comment_handler": {
    "prefix": "$",
    "enabled": true
  }
}
```

## Konfigurationsschema

Das `config_schema`-Feld definiert die erwartete Konfigurationsstruktur und wird im nächsten Kapitel [Konfiguration](./ch03-04-configuration.md) ausführlich behandelt.
