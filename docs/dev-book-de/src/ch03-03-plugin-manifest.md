# Plugin-Manifest

Die `plugin.json` ist die Identität deines Plugins. Ohne sie wird dein Plugin nicht erkannt. Sie beschreibt, was dein Plugin ist, was es kann und wie es gestartet wird.

## Vollständiges Beispiel

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
  "event_subscriptions": ["tiktok.*"],
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

| Feld | Beschreibung | Beispiel |
|---|---|---|
| `name` | Eindeutiger Plugin-Name in Kebab-Case. Wird für API-Endpunkte und Subprozess-Identifikation verwendet. | `"mein-plugin"` |
| `version` | Semantische Version des Plugins. | `"1.0.0"` |
| `entry_point` | Pfad zur `main.py` relativ zum Projektstamm. Das System startet diesen Pfad als `python <entry_point>`. | `"src/plugins/meinplugin/main.py"` |
| `display_name` | Anzeigename für Benutzeroberflächen. | `"Mein Plugin"` |
| `min_api_version` | Mindestversion der Plugin-API. Bei Inkompatibilität wird das Plugin nicht gestartet. | `"1.0.0"` |

### `name` – Der Plugin-Name

Der Name wird verwendet für:

- **API-Endpunkte**: `/api/v1/plugins/{name}/...`
- **Subprozess-Identität**: Der Subprozess meldet sich unter diesem Namen an
- **Plugin-Registry**: Der Name ist der Primärschlüssel in der Registry

Das System erlaubt: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`. Also: Kleinbuchstaben, Ziffern und Bindestriche, aber nicht am Anfang oder Ende.

### `entry_point` – Der Einstiegspunkt

Der Pfad wird relativ zum Projektstamm angegeben. Das System baut daraus den Befehl:

```
python src/plugins/meinplugin/main.py
```

Der Befehl wird als Subprozess gestartet. Python führt dann `main.py` aus, die `if __name__ == "__main__"`-Zeile wird aktiv und `PluginInstanz().run()` gestartet.

Bei kompilierten Builds kann der `entry_point` auch auf eine `.exe`- oder `.bin`-Datei verweisen.

## Optionale Felder

### `description`

Kurzbeschreibung (1-2 Sätze). Wird in der Plugin-Liste angezeigt.

### `author`

Name des Entwicklers. Wird im Plugin-Manager angezeigt.

### `homepage`

URL zur Projektseite oder zum Repository.

### `capabilities`

Eine Liste von Fähigkeiten, die das Plugin bietet. Capabilities sind **frei definierbare Schlagwörter** – sie haben keine festgelegte Bedeutung im System, können aber von anderen Komponenten für das Event-Routing verwendet werden.

```json
{
  "capabilities": ["death-counter:count", "death-counter:milestones"]
}
```

**Konvention**: `plugin-name:feature` (Kebab-Case, Doppelpunkt, Kebab-Case).

Das System speichert Capabilities in der Plugin-Registry, aber die Interpretation liegt bei den Komponenten, die sie lesen.

### `depends_on`

Liste von anderen Plugin-Namen, die aktiviert sein müssen, bevor dieses Plugin startet.

```json
{
  "depends_on": ["timer", "win-counter"]
}
```

**Was passiert, wenn eine Abhängigkeit fehlt?** Das System verhindert die Aktivierung. Der `enable`-Aufruf schlägt fehl mit einer Meldung wie: "Plugin 'mein-plugin' depends on unregistered plugin(s): timer". Die Abhängigkeiten werden beim Registrieren geprüft.

Das System garantiert **keine** Startreihenfolge – es prüft nur, ob die Abhängigkeiten zum Zeitpunkt der Aktivierung vorhanden und aktiv sind.

### `event_subscriptions`

Liste von TikTok-Event-Typen, die dein Plugin empfangen möchte. Ohne dieses Feld liefert die Event-Bridge **keine** Events an dein Plugin.

```json
{
  "event_subscriptions": ["tiktok.gift", "tiktok.follow"]
}
```

**Wildcard**: `"tiktok.*"` abonniert alle TikTok-Events (`gift`, `follow`, `like`, `join`, `comment`, `share`).

Siehe [Events & Subscriptions](./ch03-06-events-and-subscriptions.md) für Details.

### `update_url`

GitHub-API-URL für automatische Updates. Format:

```
https://api.github.com/repos/<owner>/<repo>/releases/latest
```

Das System prüft diese URL in regelmäßigen Abständen auf neue Versionen.

### `comment_handler`

Deklariert, dass das Plugin auf TikTok-Kommentare mit einem bestimmten Präfix reagiert. Die Konfiguration beeinflusst, wie der `$`-Befehl-Parser im Bridge-Prozess arbeitet.

```json
{
  "comment_handler": {
    "prefix": "$",
    "enabled": true
  }
}
```

| Unterfeld | Beschreibung |
|---|---|
| `prefix` | Das Zeichen, das einen `$`-Befehl einleitet. Standard: `$` |
| `enabled` | Ob der Handler aktiv ist. Bei `false` werden Kommentare mit dem Präfix ignoriert. |

Dieses Feld ist rein deklarativ – es informiert das System darüber, dass das Plugin einen Kommentar-Handler bereitstellt. Die eigentliche Implementierung liegt im Plugin-Code.

### `config_schema`

Definiert die erwartete Konfigurationsstruktur. Wird für automatische Generierung und Validierung der `config.yaml` verwendet.

Siehe [Konfiguration](./ch03-04-configuration.md) für das vollständige Format.

## Wie das System die plugin.json verarbeitet

1. **Scan**: Der Plugin-Watcher scannt beim Start `src/plugins/*/plugin.json`
2. **Validierung**: JSON wird geparst. Pflichtfelder werden geprüft. Ungültige Dateien werden mit einer Fehlermeldung übersprungen.
3. **Registrierung**: Die Daten werden per `POST /api/v1/plugins/register` an den API-Server gesendet und dort in der Plugin-Registry gespeichert (`data/api_plugin_registry.json`)
4. **Bereitstellung**: Das Plugin ist jetzt im System bekannt und kann über die API aktiviert werden
5. **Enable**: Erst beim Enable wird der Subprozess gestartet. Vorher existiert nur der Registry-Eintrag.

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Plugin wird nicht erkannt | JSON-Syntaxfehler | Validiere mit `python -m json.tool plugin.json` |
| Plugin startet nicht | `entry_point` existiert nicht | Prüfe den Pfad relativ zum Projektstamm |
| Plugin stürzt sofort ab | `PLUGIN_NAME` weicht von `name` ab | Korrigiere `PLUGIN_NAME` in `main.py` |
| Events kommen nicht an | `event_subscriptions` fehlt | Füge die gewünschten Events hinzu |
| Abhängigkeits-Fehler | Plugin in `depends_on` existiert nicht | Prüfe die Plugin-Namen |
