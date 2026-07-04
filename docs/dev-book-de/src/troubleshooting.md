# Fehlerbehebung

Dieses Kapitel hilft dir bei häufigen Problemen während der Plugin- und Hook-Entwicklung.

## Plugin wird nicht erkannt

**Symptom**: Das Plugin taucht nicht in der Plugin-Liste auf.

**Mögliche Ursachen**:

1. **plugin.json fehlt oder ist ungültig** – Prüfe, ob die `plugin.json` im Plugin-Verzeichnis existiert und gültiges JSON enthält.
2. **Falscher Pfad** – Der `entry_point` in der `plugin.json` muss relativ zum Projektstamm korrekt sein.
3. **Plugin-Watcher läuft nicht** – Starte das System neu.

## Plugin startet nicht

**Symptom**: Das Plugin wird angezeigt, startet aber nicht.

**Mögliche Ursachen**:

1. **Abhängigkeit nicht erfüllt** – Ein in `depends_on` aufgeführtes Plugin ist nicht aktiviert.
2. **Import-Fehler** – Prüfe die Logs auf Import-Fehler.

## Hook wird nicht geladen

**Symptom**: Der `$`-Befehl funktioniert nicht.

**Mögliche Ursachen**:

1. **register()-Funktion fehlt** – Jeder Hook benötigt `def register(api):` auf oberster Ebene.
2. **Import nicht erlaubt** – Verwende nur erlaubte Module (siehe [Import-Beschränkungen](./ch04-06-import-restrictions.md)).
3. **Action-Name falsch** – Der Name in `api.register_action()` muss mit dem `$`-Befehl in der `actions.mca` übereinstimmen.

## Events kommen nicht an

**Symptom**: Ein Plugin empfängt keine TikTok-Events.

**Mögliche Ursachen**:

1. **Event-Subscriptions fehlen** – Deklariere `event_subscriptions` in der `plugin.json`.
2. **Falscher Handler-Name** – Registriere den Handler für `"tiktok_event"`.
3. **TikTok nicht verbunden** – Stelle sicher, dass die TikTok-Verbindung aktiv ist.

## Overlay wird nicht angezeigt

**Symptom**: Das Overlay zeigt nichts an oder bleibt schwarz.

**Mögliche Ursachen**:

1. **get_overlay_html() nicht implementiert** – Diese Methode muss überschrieben werden.
2. **Falsche URL** – Prüfe die Overlay-URL in OBS.
3. **SSE-Verbindung unterbrochen** – Der SSE-Client sollte automatisch neu verbinden. Prüfe die Browser-Konsole auf Fehler.

## Trigger testen ohne TikTok

Du kannst Trigger ohne TikTok-Verbindung testen:

```bash
# Einen einzelnen Follow-Event senden
python tests/send_trigger.py --event tiktok.follow --user TestUser

# Alle verfügbaren Optionen anzeigen
python tests/send_trigger.py --help
```

Das Skript sendet einen simulierten TikTok-Event über die API an den EventBus. Dein Plugin muss aktiviert sein und die entsprechende `event_subscription` deklarieren.

Oder über die Trigger-Tester-Oberfläche in der GUI.

## Logs prüfen

Die Logs des Systems geben Aufschluss über die meisten Probleme:

- **Plugin-Logs**: Werden im `logs/`-Verzeichnis gespeichert.
- **Konsolenausgabe**: Zeigt Fehler beim Laden von Plugins und Hooks.
- **Health Monitor**: Zeigt den Gesundheitszustand aller Komponenten.

## Häufige Fehlermeldungen

| Meldung | Bedeutung |
|---|---|
| `[HOOK] has no register() function — skipped` | Dem Hook fehlt die `register()`-Funktion |
| `[HOOK] Duplicate action 'name' — first registration kept` | Der Action-Name ist bereits vergeben |
| `[HOOK] enqueue_trigger() blocked — chain depth exceeds maximum` | Endlosschleife erkannt, Trigger gesperrt |
| `[HOOK] Error in action 'name': ...` | Fehler in der Handler-Funktion |
