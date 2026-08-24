# Hook-Entwicklung

Hooks sind eine leichte Alternative zu Plugins. Sie laufen direkt im Bridge-Prozess und reagieren auf `$`-Befehle, die in der `actions.mca` definiert sind. Hooks eignen sich besonders für einfache, reaktive Erweiterungen.

In diesem Kapitel lernst du, wie du Hooks erstellst, konfigurierst und in das System integrierst.

## Aufbau des Kapitels

1. [Dein erster Hook](./ch04-01-your-first-hook.md) – Erstelle in wenigen Minuten deinen ersten Hook
2. [Hook-Struktur & Manifest](./ch04-02-hook-structure-and-manifest.md) – Verzeichnisstruktur und hook.json
3. [Hook-API-Referenz](./ch04-03-hook-api.md) – Alle verfügbaren Hook-API-Methoden
4. [Konfiguration](./ch04-04-hook-configuration.md) – Per-Hook-Konfiguration
5. [Import-Beschränkungen](./ch04-05-import-restrictions.md) – Gültige Imports und Einschränkungen
6. [Plugin-gebündelte Hooks](./ch04-06-plugin-bundled-hooks.md) – Hooks im Bundle mit einem Plugin

## Wann ein Hook, wann ein Plugin?

| Aspekt | Hook | Plugin |
|--------|------|--------|
| Ausführungsort | Läuft **direkt im Bridge-Prozess** | Eigener Subprozess |
| Kommunikation | **Direkter Funktionsaufruf** | HTTP-API (`send_command`) |
| Latenz | Millisekunden | Höher (Polling-Intervall 1s) |
| Komplexität | Einfach, eine Funktion | Vollständige Klasse mit Threads |
| Anwendungsfall | Einfache `$`-Befehle | Komplexe Logik, GUI, Zustand |
| Lebenszyklus | Wird beim Start geladen | Wird als Subprozess gestartet/gestoppt |

## Hooks aktualisieren

Eigenständige Hooks unterstützen denselben Update-Mechanismus wie Plugins:

- `update_url` in der `hook.json` deklarieren (GitHub-Releases-API-URL
  oder direkter Link). Die Aktion *Nach Updates suchen* im Dashboard
  fragt sie ab und bietet die Installation zusammen mit Tool- und
  Plugin-Updates an.
- **Nur eigenständige Hooks** — Hooks im Haupt-Hooks-Verzeichnis.
  Plugin-gebündelte Hooks (`plugins/<name>/hooks/`) werden gemeinsam
  mit ihrem Plugin aktualisiert.
- Die Update-Quelle muss eine SHA-256-Prüfsumme bereitstellen
  (`.sha256` oder `.checksum` neben dem Archiv); ungeprüfte Archive
  werden abgelehnt.
- Die `config.yaml` des Nutzers bleibt über ein Update hinweg erhalten.
  Neue Schlüssel einer neueren Version werden beim nächsten Laden aus
  den `config_schema`-Defaults des Manifests ergänzt.
- Installierter Code wird aktiv, sobald die Bridge die Hooks neu lädt
  (Neustart oder Reload-Signal mit `hooks: true`).
