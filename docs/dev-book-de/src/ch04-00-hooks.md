# Hook-Entwicklung

Hooks sind eine leichte Alternative zu Plugins. Sie laufen direkt im Bridge-Prozess und reagieren auf `$`-Befehle, die in der `actions.mca` definiert sind. Hooks eignen sich besonders für einfache, reaktive Erweiterungen.

In diesem Kapitel lernst du, wie du Hooks erstellst, konfigurierst und in das System integrierst.

## Aufbau des Kapitels

1. [Dein erster Hook](./ch04-01-your-first-hook.md) – Erstelle in wenigen Minuten deinen ersten Hook
2. [Hook-Struktur](./ch04-02-hook-structure.md) – Verzeichnisstruktur und Dateien
3. [Hook-Manifest](./ch04-03-hook-manifest.md) – Die `hook.json` im Detail
4. [Hook-API](./ch04-04-hook-api.md)
5. [Konfiguration](./ch04-05-configuration.md)
6. [Import-Beschränkungen](./ch04-06-import-restrictions.md) – Gültige Imports und Einschränkungen
7. [Plugin-gebündelte Hooks](./ch04-07-plugin-bundled-hooks.md) – Hooks im Bundle mit einem Plugin
8. [Fortgeschrittene Features](./ch04-08-advanced-features.md) – Trigger-Verkettung und komplexe Muster
9. [Best Practices](./ch04-09-best-practices.md) – Bewährte Verfahren und häufige Fehler
