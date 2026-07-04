# Best Practices (Hook)

Dieses Kapitel fasst bewährte Verfahren und häufige Fehler bei der Hook-Entwicklung zusammen.

## Hook-Struktur

- **Eindeutige Namen**: Jeder Action-Name sollte innerhalb des Systems eindeutig sein.
- **Kurze Handler**: Halte Handler-Funktionen kurz und fokussiert.
- **Eine Sache pro Hook**: Ein Hook sollte genau eine Funktionalität abdecken.
- **register()-Funktion nicht vergessen**: Ohne `register(api)` wird der Hook nicht geladen.

## Handler schreiben

- **Signatur einhalten**: Handler müssen genau drei Parameter akzeptieren: `(user, trigger, context)`.
- **Keine schweren Operationen**: Hooks laufen im Bridge-Prozess. Blockierende oder schwere Operationen beeinträchtigen das gesamte System.
- **Fehler abfangen**: Das System fängt Fehler in Handlern, aber protokolliere wichtige Fehler selbst.

## Trigger-Verkettung

- **Keine Schleifen**: Rufe nicht `enqueue_trigger` mit dem Trigger auf, der den aktuellen Handler ausgelöst hat.
- **Eigene Trigger nutzen**: Definiere eigene Trigger-Namen in der `actions.mca` für Zwischenschritte.
- **Vorsicht mit Tiefe**: Maximal 3 Ketten-Schritte sind erlaubt.

## Konfiguration

- **Schema definieren**: Ein `config_schema` erleichtert die Konfiguration für Benutzer.
- **Standardwerte**: Setze sinnvolle Standardwerte für alle Felder.
- **Konfiguration lesen**: Verwende `api.get_hook_config(name)` statt auf die Datei direkt zuzugreifen.

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Hook wird nicht geladen | `register()`-Funktion fehlt | Füge `def register(api):` hinzu |
| Hook wird nicht ausgeführt | Action-Name in `actions.mca` falsch | Prüfe den Namen |
| Import-Fehler | Nicht erlaubtes Modul importiert | Verwende die Hook-API |
| `enqueue_trigger` tut nichts | Falscher Trigger-Name | Übergib einen gültigen Trigger (links vom `:` in `actions.mca`) |
| Duplikat-Warnung | Action-Name bereits registriert | Wähle einen eindeutigen Namen |
