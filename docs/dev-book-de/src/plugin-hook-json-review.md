# Review: `plugin.json` und `hook.json` Dokumentation

Überprüft am: 2026-07-05
Quellen: `ch03-02-plugin-structure.md`, `ch03-03-configuration.md`, `ch04-02-hook-structure-and-manifest.md`, `PluginManifest`/`ConfigSchemaField` (models.py), `HookManifest` (hook_manifest.py), `create_plugin.py`, `create_hook.py`, 5 echte `plugin.json`-, 2 echte `hook.json`-Dateien

---

## Gesamturteil

**Schwere Mängel** – ein Entwickler, der nur die Dev-Book-Dokumentation verwendet, kann ohne Rücksprache mit dem Quellcode oder Bestandsdateien keine korrekte `plugin.json` oder `hook.json` erstellen. Es fehlen dokumentierte Felder, die Feld-Typ-Tabelle der `config_schema` ist unvollständig, und das `hook.json`-Beispiel enthält ein Feld (`enabled`), das vom System gar nicht ausgewertet wird.

---

## 1. `plugin.json` – Im Code vorhandene, aber undokumentierte Felder

Diese Felder sind im offiziellen `PluginManifest`-Pydantic-Modell (`src/core/api/models.py:56-103`) definiert, werden aber im Dev-Book nicht erwähnt:

| Fehlendes Feld | Typ / Default | Code-Stelle | Vorkommen in echten Plugins |
|---|---|---|---|
| `homepage` | `str = ""` | models.py:75 | Alle 5 Plugins |
| `max_api_version` | `Optional[str] = None` | models.py:78 | Keines (nur Framework) |
| `ics` | `bool = True` | models.py:95 | Keines sichtbar (Default) |
| `level` | `int = 4` (ge:1, le:4) | models.py:96 | Keines sichtbar (Default) |

### `homepage`
Fehlt in der Tabelle "Wichtige optionale Felder" (ch03-02-plugin-structure.md). Jedes echte Plugin setzt es auf die GitHub-URL. Ein Neuling weiß nicht, dass dieses Feld existiert, obwohl es in der `PluginRegistration`-API persistiert wird.

### `max_api_version`
Fehlt komplett. Wenn das System in Zukunft API-Inkompatibilitäten einführt, wird dieses Feld für Kompatibilitätsprüfungen benötigt. Sollte zumindest erwähnt werden.

### `ics` und `level`
Steuerungsfelder für das Interface Control System und die Sichtbarkeitsstufe. Werden im Plugin-Kontext nicht benötigt (Default-Werte reichen), sollten aber erwähnt werden, damit Entwickler nicht überrascht sind, wenn sie diese Felder in der API-Response sehen.

---

## 2. `config_schema.fields` – Fehlende Feldeigenschaften

Die Tabelle "Feldeigenschaften" in `ch03-03-configuration.md:79-87` ist unvollständig. Das `ConfigSchemaField`-Modell (models.py:10-27) definiert diese Felder, die in der Dokumentation fehlen:

| Fehlende Eigenschaft | Typ / Default | Beschreibung | Genutzt in echten Plugins? |
|---|---|---|---|
| `options` | `list[str] = []` | Erlaubte Werte für `type: select` | Timer, Spotify, WinCounter, DeathCounter |
| `min` / `max` | `Optional[int] = None` | Minimum/Maximum für `type: integer` | Timer (min, max), WinCounter (min) |
| `item_schema` | `Optional[dict] = None` | Schema für Array-Elemente | Timer, WinCounter, DeathCounter, Spotify |
| `required` | `bool = False` | Feld ist Pflicht | Keines sichtbar (Default) |
| `secret` | `bool = False` | Wert maskieren (Passwörter/Keys) | **Spotify** (`client_secret`: `secret: true`) |
| `widget` | `Optional[str] = None` | GUI-Widget-Hinweis | Keines sichtbar |

### Kritisch: `options`
Wird in der Typ-Tabelle ("Unterstützte Feldtypen") für `select` erwähnt, aber die eigentliche Feldeigenschaften-Tabelle führt `options` nicht auf. Ein Entwickler, der einen `select`-Typ definieren will, muss raten, wie `options` strukturiert wird.

### Kritisch: `item_schema`
Wird in der Typ-Tabelle für `array` erwähnt, aber nicht in den Feldeigenschaften. Die Dokumentation zeigt `"item_schema": {"type": "integer", "min": 1}` im Beispiel, aber erklärt nicht, welche Felder `item_schema` selbst haben kann (type, min, max, options usw.).

### Kritisch: `secret`
Wird live im Spotify-Plugin verwendet (`client_secret`). Ein Plugin-Entwickler, der OAuth-Credentials speichern will, kann nicht aus der Doku ableiten, dass `secret: true` den Wert in der GUI maskiert.

### `min` / `max`
Die Typ-Tabelle sagt "optional mit `min`, `max`" für `integer`, aber die Feldeigenschaften-Tabelle zeigt diese Optionen nicht. Ein Entwickler muss raten, ob `min` und `max` auf Feldebene oder Typebene definiert werden.

---

## 3. `hook.json` – Dokumentationsfehler und Lücken

### 3.1 `"enabled": true` – FALSCHES Feld im Beispiel

Das vollständige Beispiel in `ch04-02-hook-structure-and-manifest.md:35-56` enthält:
```json
"enabled": true,
```

**Dieses Feld wird von `HookManifest` (hook_manifest.py:19-30) nicht ausgewertet.** Der Hook-aktiv/deaktiviert-Status wird über `config.yaml` (`enabled: bool`) oder `data/hook_registry.json` gesteuert (dokumentiert in "Hooks aktivieren/deaktivieren"), **nicht** über ein `enabled`-Feld in `hook.json`.

Ein Entwickler, der diesem Beispiel folgt, fügt ein inertes Feld hinzu, das das System ignoriert.

### 3.2 Fehlende Felder in `hook.json`-Dokumentation

| Fehlendes Feld | Typ / Default | Code-Stelle | Genutzt von |
|---|---|---|---|
| `capabilities` | `list[str] = []` | hook_manifest.py:26 | `random`-Hook, `example_hook` |
| `depends_on` | `list[str] = []` | hook_manifest.py:30 | Keiner |

`capabilities` wird sowohl vom Code aus `hook.json` gelesen als auch von realen Hooks verwendet. Ein Entwickler kann nicht aus der Doku ableiten, wie er Capabilities für seinen Hook deklariert.

### 3.3 Name-Validierung: Dokumentation ≠ Realität

- **Dokumentation**: "Kleinbuchstaben, Ziffern" (ch04-02:18)
- **Scaffold (`create_hook.py`)**: `re.match(r'^[a-z0-9]+$', name)` – nur a-z und 0-9, **keine Unterstriche**
- **Real existierender Hook**: `example_hook` verwendet **Unterstriche** (`example_hook`)

Das ist ein Widerspruch: Die Dokumentation widerspricht dem Scaffold, und das mitgelieferte Beispiel `example_hook` verletzt die Validierungsregel des Scaffolds. Der Scaffold erlaubt `^[a-z0-9]+$`, aber `src/hooks/example_hook/hook.json` hat `"name": "example_hook"`. Dieser Hook kann nicht über den Scaffold erstellt werden.

---

## 4. Unklare / unvollständige Dokumentation bestehender Felder

### 4.1 `depends_on` – Runtime-Verhalten nicht spezifiziert

> "Liste von Plugin-Namen, die aktiviert sein müssen"

Was passiert, wenn eine Abhängigkeit nicht aktiviert ist?
- Plugin startet nicht? (Fehler: PLUGIN-0005?)
- Abhängigkeit wird automatisch aktiviert?
- Timeout bis Abhängigkeit bereit?
- Nur Warnung?

Das Verhalten ist entscheidend für die Plugin-Entwicklung, aber nicht dokumentiert.

### 4.2 `capabilities` – Kein Namensschema

> "Wird vom System zur Discovery verwendet, z. B. `["timer:countdown"]`"

Das Beispiel zeigt `namespace:feature`, aber es gibt keine Spezifikation:
- Muss der Namensraum dem Plugin-Namen entsprechen?
- Wie werden Capabilities per API abgefragt?
- Sind Capabilities versioniert?

### 4.3 `event_subscriptions` – Keine vollständige Liste der Event-Typen

> "Wildcard `"tiktok.*"` abonniert alle TikTok-Events"

Es wird nie dokumentiert, **welche** Event-Typen es gibt:
- `tiktok.gift`, `tiktok.follow`, `tiktok.comment`, `tiktok.like`, `tiktok.join`, `tiktok.share` (aus ch03-05)
- Können Plugins auch Nicht-TikTok-Events abonnieren? (z. B. `minecraft.player_death`)
- Sind benutzerdefinierte Event-Namespaces erlaubt?

### 4.4 `update_url` – Format nicht spezifiziert

> "GitHub-API-URL für Auto-Updates"

Die Scaffolds zeigen: `https://api.github.com/repos/{owner}/{repo}/releases/latest`
Aber die Doku spezifiziert nicht:
- Welches Format wird erwartet?
- Was passiert bei leerem String?
- Ist ein direkter Download-Link erlaubt?

### 4.5 `comment_handler` – Kein Verweis auf Comment-Handler-Mechanismus

Das Feld ist jetzt dokumentiert (`prefix` + `enabled`), aber der Querverweis in ch03-02:41 verweist auf ch03-05 ("Events empfangen"), das den `comment_handler` nicht erklärt. Es gibt kein Kapitel, das beschreibt, wie Kommentar-Handler funktionieren.

---

## 5. Inkonsistenzen zwischen Dokumentation und echten Dateien

| Aspekt | Dokumentation | Echte Dateien | Problem |
|---|---|---|---|
| `plugin.json` Felder | 4 Pflichtfelder, 8 optionale | Enthält auch `homepage` (alle), `level`/`ics` (Default) | Fehlende Felder |
| `config_schema` Eigenschaften | 7 Eigenschaften | Code definiert 14 Eigenschaften | 7 fehlen |
| Hook-Name Zeichensatz | a-z, Ziffern | `example_hook` mit `_` | Widerspruch |
| `hook.json` `enabled` | Im Beispiel enthalten | HookManifest ignoriert es | Falsches Feld |
| `ports` | Nicht erwähnt | `test/plugin.json` enthält `ports` | Legacy-Feld? |

---

## 6. Empfehlungen nach Schweregrad

### Kritisch (muss sofort korrigiert werden)

1. **`hook.json`-Beispiel**: `"enabled": true` entfernen – das Feld wird von `HookManifest` nicht ausgewertet
2. **Feldeigenschaften-Tabelle**: `options`, `min`, `max`, `item_schema`, `secret`, `required`, `widget` ergänzen (ch03-03-configuration.md)
3. **Hook-Namenskonvention**: Entweder `create_hook.py` auf `^[a-z0-9_]+$` erweitern oder `example_hook` in `examplehook` umbenennen

### Hoch (sollte in nächster Revision korrigiert werden)

1. **`homepage`** als optionales Feld in der Plugin-Tabelle ergänzen (ch03-02)
2. **`max_api_version`**, **`ics`**, **`level`** zumindest in Fußnote erwähnen (ch03-02)
3. **`depends_on`** Runtime-Verhalten dokumentieren: Was passiert bei fehlender Abhängigkeit?
4. **`event_subscriptions`** vollständige Event-Typ-Liste dokumentieren

### Mittel (für Folgeversion)

1. **`capabilities`** Namenskonvention und API-Endpunkt dokumentieren
2. **`update_url`** Format spezifizieren (nicht nur "GitHub-API")
3. **`comment_handler`** eigenes Kapitel oder Abschnitt, das beschreibt, wie der Mechanismus funktioniert
4. **`item_schema`** Sub-Schema dokumentieren (welche Felder erlaubt)
5. **`ports`** in `test/plugin.json` entweder entfernen (Legacy) oder dokumentieren

---

## 7. Quellennachweise

| Fundstelle | Datei | Zeilen |
|---|---|---|
| PluginManifest (alle Felder) | `src/core/api/models.py` | 56-103 |
| ConfigSchemaField (alle Eigenschaften) | `src/core/api/models.py` | 10-27 |
| Plugin-JSON-Template (Scaffold) | `create_plugin.py` | 54-81 |
| HookManifest (alle Felder) | `src/core/hook_manifest.py` | 19-31 |
| Hook-JSON-Template (Scaffold) | `create_hook.py` | 41-66 |
| Hook-Name-Validierung | `create_hook.py` | 83 |
| Plugin-Dokumentation | `docs/dev-book-de/src/ch03-02-plugin-structure.md` | 21-43 |
| Config-Schema-Dokumentation | `docs/dev-book-de/src/ch03-03-configuration.md` | 66-88 |
| Hook-Dokumentation | `docs/dev-book-de/src/ch04-02-hook-structure-and-manifest.md` | 14-56 |
| Events-Dokumentation | `docs/dev-book-de/src/ch03-05-events-and-subscriptions.md` | 1-190 |
| Beispiel: spotify/plugin.json | `src/plugins/spotify/plugin.json` | 1-120 |
| Beispiel: example_hook/hook.json | `src/hooks/example_hook/hook.json` | 1-10 |
| Beispiel: random/hook.json | `src/hooks/random/hook.json` | 1-35 |

---

*Erstellt auf Basis des echten Source-Codes (Pydantic-Modelle, HookManifest), der Scaffolding-Skripte und aller existierenden plugin.json-/hook.json-Dateien.*
