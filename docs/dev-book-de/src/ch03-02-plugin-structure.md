# Plugin-Struktur & Manifest

Jedes Plugin lebt in einem eigenen Verzeichnis unter `src/plugins/<name>/`. Das System erkennt es an der `plugin.json`.

## Verzeichnisstruktur

```
src/plugins/<name>/
├── plugin.json          # Manifest (Pflicht)
├── main.py              # Plugin-Code (Pflicht)
├── config.yaml          # Konfiguration (optional, wird automatisch erstellt)
├── hooks/               # Optional: Plugin-gebündelte Hooks
├── version.txt          # Optional: Vom Scaffolder erzeugt
└── README.md            # Optional: Dokumentation
```

## plugin.json — Das Manifest

Dies ist die Erkennungsdatei. Der `PluginWatcher` scannt beim Start `src/plugins/*/plugin.json`.

### Pflichtfelder

| Feld | Beschreibung | Beispiel |
|------|--------------|----------|
| `name` | Eindeutiger Name (Kleinbuchstaben, Ziffern, Bindestriche). Regex: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` | `"mein-plugin"` |
| `version` | Semantische Version | `"1.0.0"` |
| `entry_point` | Pfad zur `main.py` relativ zum Projektstamm | `"src/plugins/mein-plugin/main.py"` |
| `display_name` | Anzeigename für die GUI | `"Mein Plugin"` |

### Wichtige optionale Felder

| Feld | Beschreibung |
|------|--------------|
| `description` | Kurzbeschreibung (1-2 Sätze) |
| `author` | Entwickler-Name |
| `homepage` | Projekt-URL (z. B. GitHub-Repository) |
| `min_api_version` | Mindestversion der Plugin-API (aktuell `1.0.0`, siehe `src/core/version.py`). Bei Inkompatibilität wird das Plugin nicht gestartet. |
| `max_api_version` | Höchste unterstützte API-Version. Fehlt das Feld oder ist es `null`, gibt es keine Obergrenze. |
| `event_subscriptions` | Liste von Event-Typen, die das Plugin über den EventBus empfangen will. Unterstützt exakte Typen (`"tiktok.gift"`), Prefix-Wildcards (`"tiktok.*"`, `"minecraft.*"`) und den Catch-all `"*"`. TikTok-Events kommen als `tiktok_event` an, alle anderen Quellen als `bus_event`. **Ohne dieses Feld werden keine Events zugestellt.** |
| `depends_on` | Liste von Plugin-Namen, die aktiviert sein müssen. Sind Abhängigkeiten nicht aktiv oder nicht registriert, schlägt das Aktivieren fehl (HTTP 422). |
| `capabilities` | Liste von Fähigkeiten, die das Plugin bereitstellt. Wird vom System zur Discovery verwendet, z. B. `["timer:countdown"]`. Andere Plugins können per API nach Plugins mit bestimmten Capabilities suchen. |
| `permissions` | **Pflichtfeld**: Deklaration der gesperrten API-Familien, die das Plugin nutzt: `["store", "network", "plugins", "events"]`. Nicht deklarierte Familien werden standardmäßig abgelehnt (`PLUGIN-0020`, sicherer Fallback) — gleiche Semantik wie Hook-`permissions`. Siehe [Permissions](./ch03-04-plugin-api.md#permissions-opt-in). |
| `config_schema` | Schema für die Konfiguration (siehe [Konfiguration](./ch03-03-configuration.md)) |
| `comment_handler` | Objekt mit `prefix` (String) und `enabled` (Boolean). Deklariert, dass das Plugin auf TikTok-Kommentare mit einem bestimmten Prefix reagiert (z. B. `"$"`). Siehe [Events empfangen](./ch03-05-events-and-subscriptions.md). |
| `update_url` | URL für Auto-Updates, z. B. `"https://api.github.com/repos/TechnikLey/Tiktok2Mc/releases/latest"`. Bei leerem String keine Update-Prüfung. |
| `platform` | Zielplattform: `"all"` (Standard), `"linux"` oder `"windows"`. Inkompatible Plugins können nicht über die GUI oder API aktiviert werden. |
| `dashboard_ui` | `true`, wenn das Plugin eine Dashboard-Seite bereitstellt (Override `get_dashboard_html()` in der Plugin-Klasse). Das Web-Dashboard zeigt dann einen Tab mit der Plugin-Seite. Siehe [Plugin-API](./ch03-04-plugin-api.md#dashboard-seiten). |
| `queries` | Liste von Query-Namen, die das Plugin per `on_query()` beantwortet (Request/Response-Kanal), z. B. `["top", "stats"]`. Unbekannte Queries bekommen sofort einen 404; ohne dieses Feld wird jeder Name versucht. Siehe [Plugins abfragen](./ch03-04-plugin-api.md#plugins-abfragen-requestresponse). |
| `sandbox_profile` | `"light"`, `"moderate"` oder `"strict"` — überschreibt das globale Sandbox-Profil für den Prozess dieses Plugins. Wirkt nur, wenn Sandboxing in der `config.yaml` aktiviert ist (`plugin_sandbox.enabled`). Siehe [Sandbox-Profile](#sandbox-profile). |
| `icon` | Emoji, das in der GUI angezeigt wird (Reactions-Tab). Standard `"🔌"`. |
| `emitted_events` | Liste von Events, die dieses Plugin an den EventBus sendet. Jeder Eintrag: `key` (Event-ID, z. B. `"mein-plugin.thing"`), `name`, `desc`, `icon`. Optional: `name_i18n`/`desc_i18n` für lokalisierte Anzeige. **Payload-Vertrag:** `version` (Ganzzahl, Standard `1` — bei Breaking-Änderungen am Payload erhöhen) und `data_schema` — Liste deklarierter Felder `{key, type, desc, required}` mit `type` aus `string`, `number`, `boolean`, `object`, `array`, `any`. Deklarierte Events werden **erzwungen**: Wer den Typ mit fehlenden Pflichtfeldern oder falschen Typen publiziert, erhält `422 API-0010`. Das Schema ist über `GET /api/v1/reactions/catalog` abrufbar. |
| `accepted_commands` | Objekt mit Kommandos, die dieses Plugin über die CommandQueue akzeptiert. Jedes Kommando: `name`, `desc`, `args` (Objekt aus Argument-Schemas mit `type`, `label`, `default`, `min`, `max`, `options`, `placeholder`, `hint`). Diese erscheinen als Aktions-Optionen im „Create Reaction"-Wizard der GUI. Optional: `name_i18n`, `desc_i18n` für lokalisierte Anzeige. |

> [!NOTE]
> Die internen Felder `ics` (Boolean, Standard `true`) und `level` (Integer 1–4, Standard `4`) werden automatisch gesetzt. In der Regel musst du sie nicht in der `plugin.json` angeben.

### Sandbox-Profile

Plugin-Subprozesse lassen sich mit Ressourcenlimits einschränken
(`plugin_sandbox.enabled: true` in der `config.yaml`). Statt Rohwerte zu
tunen, wählst du ein **Built-in-Profil** über `plugin_sandbox.profile`:

| Profil | RAM | CPU-Zeit | Dateien | Prozesse | Priorität |
|--------|-----|----------|---------|----------|-----------|
| `light` | 1 GB | unbegrenzt | 256 | 64 | below normal |
| `moderate` *(Standardwerte)* | 512 MB | 1 h | 256 | 32 | below normal |
| `strict` | 256 MB | 15 min | 128 | 8 | idle |

Einzelne Plugins können das globale Profil pro Prozess überschreiben, indem
sie `"sandbox_profile": "strict"` in ihre `plugin.json` aufnehmen.
Unbekannte Namen fallen auf die globale Konfiguration zurück. Hinweis:
RAM-Limits greifen unter Linux direkt und unter Windows über ein Job
Object; CPU-/Datei-/Prozess-Limits sind nur Linux.

### Vollständiges Beispiel

```json
{
  "name": "mein-plugin",
  "version": "1.0.0",
  "entry_point": "src/plugins/mein-plugin/main.py",
  "display_name": "Mein Plugin",
  "description": "Reagiert auf Follows und Gifts",
  "author": "Dein Name",
  "homepage": "https://github.com/DeinName/Tiktok2Mc",
  "min_api_version": "1.0.0",
  "event_subscriptions": ["tiktok.follow", "tiktok.gift"],
  "capabilities": ["mein-plugin:counter"],
  "depends_on": [],
  "update_url": "https://api.github.com/repos/DeinName/Tiktok2Mc/releases/latest",
  "icon": "⚡",
  "platform": "all",
  "emitted_events": [
    {
      "key": "mein-plugin.thing",
      "name": "Ding passiert",
      "desc": "Feuert, wenn das Ding des Plugins passiert",
      "icon": "✨"
    }
  ],
  "accepted_commands": {
    "do_thing": {
      "name": "Ding auslösen",
      "desc": "Löst das Ding aus",
      "args": {
        "count": { "type": "number", "label": "Wie viele", "default": 1, "min": 1 }
      }
    }
  },
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "schwellwert",
        "type": "integer",
        "default": 10,
        "min": 1,
        "label": "Schwellwert",
        "category": "Events"
      }
    ]
  }
}
```

> [!NOTE]
> Die Felder `emitted_events` und `accepted_commands` versorgen den **Reactions-Tab** im Dashboard. Die GUI lädt sie über `GET /api/v1/reactions/catalog`, das die Deklarationen aller Plugins mit den eingebauten Core-Events (TikTok, Minecraft, Server) zusammenführt. Plugin-Events werden im „Create Reaction"-Wizard automatisch unter dem Plugin-Namen gruppiert – ein neues Plugin erscheint ohne GUI-Code ändern zu müssen.
>
> **Nutzung bei der Zustellung:** Die Deklarationen werden auch zur Laufzeit verwendet. Subscriptions in `event_subscriptions` werden gegen den vereinheitlichten Event-Katalog geprüft (Core-Events + alle `emitted_events`) — ein exakter Event-Name, den niemand deklariert, erzeugt eine Warnung im API-Log (Tippfehler-Schutz; Wildcards werden nie markiert). Ebenso wird ein über `POST /plugins/{name}/command` zugestelltes Kommando, das nicht in `accepted_commands` steht, als Warnung geloggt, aber trotzdem zugestellt. Die Katalog-Antwort trägt ein `version`-Feld, damit Werkzeuge Schema-Änderungen erkennen können.

> [!NOTE]
> **Sprache von Plugin-Inhalten:** Die Anwendungsoberfläche ist auf Deutsch und Englisch verfügbar. Von Plugins bereitgestellte Texte (Event-Namen, Beschreibungen, Befehlsbezeichnungen, Konfigurationshilfen, Overlay-Inhalte) können jedoch in der Sprache des Plugin-Autors erscheinen, wenn diese nicht übersetzt wurden. Plugin-Autoren können optional lokalisierte Strings über `name_i18n` / `desc_i18n`-Felder in `emitted_events` und `accepted_commands` bereitstellen, dies ist aber nicht verpflichtend. Wenn keine Übersetzung für die gewählte Sprache verfügbar ist, wird der Originaltext des Plugins angezeigt.

## main.py — Der Einstiegspunkt

Das System startet den Subprozess mit: `python src/plugins/<plugin-dir>/main.py`

Die Datei muss enthalten:

1. Eine Klasse, die von `BasePlugin` erbt
2. Das Attribut `PLUGIN_NAME` (muss mit `name` in `plugin.json` übereinstimmen)
3. Die Methode `get_overlay_html()`
4. Einen `if __name__ == "__main__"`-Block

```python
from core.base_plugin import BasePlugin

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"

    def get_overlay_html(self) -> str:
        return "<html><body>Aktiv</body></html>"

if __name__ == "__main__":
    MeinPlugin().run()
```

**Ohne den `if __name__`-Block** würde der Subprozess nur die Klassendefinition lesen, keine Instanz erzeugen und sofort beenden.

## Namenskonventionen

| Element | Konvention | Beispiel |
|---------|------------|----------|
| `name` in `plugin.json` | Kebab-Case (Kleinbuchstaben, Ziffern, Bindestriche) | `mein-plugin` |
| Verzeichnisname | Identisch mit `name` | `mein-plugin` |
| `PLUGIN_NAME` in Python | Exakt wie `name` in plugin.json | `"mein-plugin"` |
| `entry_point` | Relativer Pfad | `src/plugins/mein-plugin/main.py` |

**Konsequenz bei Abweichung**: Das Plugin wird zwar registriert, der Subprozess startet nicht korrekt.

## Wie das System die plugin.json verarbeitet

1. **Scan**: `PluginWatcher` scannt `src/plugins/*/plugin.json` (auch zur Laufzeit)
2. **Validierung**: JSON wird geparst, Pflichtfelder geprüft
3. **Registrierung**: Daten werden im API-Server in der `PluginRegistry` gespeichert (`data/api_plugin_registry.json`)
4. **Aktivierung**: Erst beim Enable (per API oder GUI) wird der Subprozess gestartet
5. **Signal-Datei**: Der API-Server schreibt `core/runtime/plugin_start_<name>`. Der Supervisor startet daraufhin den Prozess.

## version.txt

Das Scaffolding-Skript erzeugt eine `version.txt` im YAML-Format:

```
version: v1.0.0
update_url: https://api.github.com/repos/...
```

Wird vom System für Update-Prüfungen verwendet.

## Nächstes Kapitel

Im nächsten Kapitel lernst du die [Konfiguration](./ch03-03-configuration.md) im Detail.
