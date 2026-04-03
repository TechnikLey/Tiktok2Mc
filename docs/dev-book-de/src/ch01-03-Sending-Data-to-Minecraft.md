# Daten an Minecraft senden (Phase 3)

Jetzt kommt die Aktion: Das Event ist verarbeitet, und jetzt muss Minecraft es ausführen. Wie funktioniert diese Kommunikation?

---

## Das Problem: Wie sagen wir Minecraft, was es tun soll?

Minecraft ist ein Spiel auf einem Server. Wir sind ein Python-Programm. **Wie kommunizieren wir?**

Optionen:
- ✗ Direkt in den Spiele-Code schreiben? (Zu kompliziert, tausende Zeilen Code nötig)
- ✗ Chat-Nachrichten? (Funktioniert technisch nicht)
- ✓ **Commands / Befehle!** (Das ist die Lösung)

Minecraft hat eine **Console**, wo man Befehle eingeben kann:

```
/say "Hallo Welt!"
/give @s diamond 5
/function my_namespace:special_event
/tp @a 100 64 200
```

Wir müssen diese Befehle nur **remote** (von außen) ausführen können. Dafür gibt es **RCON**.

---

## Lösung: RCON (Remote Console)

### Was ist RCON?

**RCON** = Remote Console – eine Art "Fernbedienung" für Minecraft-Server.

```
┌─────────────────────────────┐
│  Unser Python-Programm      │
│  "Mach /say Danke!"         │
└──────────────┬──────────────┘
               │ RCON-Befehl über Netzwerk
               ↓
┌──────────────────────────────┐
│  Minecraft-Server            │
│  Console empfängt Befehl     │
│  Führt /say aus              │
│  Result: Chat zeigt "Danke!" │
└──────────────────────────────┘
```

### Wie RCON funktioniert

1. **Verbindung aufbauen**
   ```
   Programm → "Ich bin Admin, hier ist das Passwort"
   Server → Authentifizierung OK, Verbindung offen
   ```

2. **Befehl schicken**
   ```
   Programm → "/say User XY hat gefolgt!"
   Server → Befehl wird ausgeführt (im Spiel sichtbar)
   ```

3. **Bestätigung** (optional)
   ```
   Server → Kurze Antwort (normalerweise leer oder "ok")
   Programm → Befehl verarbeitet
   ```

> [!NOTE]
> **Vereinfachte Darstellung!**
> 
> Die obige Erklärung ist zur Veranschaulichung vereinfacht. In der Realität:
> - RCON sendet **keine aussagekräftigen Antworten** wie "5 Spieler haben eine Nachricht bekommen"
> - Die Antwort ist normalerweise **leer**
> - Wir wissen nicht, ob etwas Ausgeführt wurde
> - Wir wissen nicht, *welcher Fehler* auftrat, wenn der Befehl fehlschlägt
> 
> Das ist eine Limitation von RCON. Für die Praxis: Wir senden den Befehl, hoffen, dass es funktioniert.

### RCON ist TCP/IP

RCON nutzt das **TCP/IP-Protokoll** – das ist das Internet-Protokoll, das auch E-Mail, Webseiten, etc. nutzen.

```
Unser Programm      Netzwerk          Minecraft-Server
(Port XYZ)  ←------TCP/IP----→  (üblicherweise Port 25575)
```

**Wichtige Details:**

- **Standardverhalten:** RCON verbindet sich normalerweise für **jeden Befehl einzeln** – Verbindung auf, Befehl senden, Verbindung zu.
- **Das Streaming Tool:** Verwendet eine **persistent Connection** – die Verbindung bleibt offen. Das muss aber speziell eingerichtet werden und ist nicht der Standard.
- **Zuverlässigkeit:** RCON ist nicht garantiert zuverlässig. Befehle können verloren gehen, Verbindungen können abbrechen. Das ist eine bekannte Limitation.

> [!WARNING]
> **RCON hat Limitations:**
> - Nicht garantiert zuverlässig (Befehle können verloren gehen)
> - Persistent connections müssen manuell implementiert werden
> - Keine aussagekräftigen Fehler-Responses
> - Wenn ein Befehl fehlschlägt, wissen wir es oft nicht
> 
> Das Streaming Tool handhabt das durch:
> - Eigenes persistentes Connection Management
> - Logging und Retry-Mechanismen
> - Hoffen, dass es funktioniert

---

## Von Event zu Minecraft-Befehl

### Beispiel: User sendet 5 Gifts

```
1. PHASE 1: Event kommt an
   TikTok: "User 'Streamer_Fan_123' hat 5x Gift gesendet"
   
   ↓
   
2. PHASE 2: Event wird verarbeitet
   System: "Das ist ein Gift-Event, 5x"
   Daten extrahiert: User = "Streamer_Fan_123", Menge = 5
   In Queue gelegt → Wartet bis es dran ist
   
   ↓
   
3. PHASE 3: Befehl wird an Minecraft gesendet
   System: "Welcher Befehl soll für 5x Gift ausgelöst werden?"
   (aus `actions.mca` nachschlagen)
   
   Befehl: /say "Danke an Streamer_Fan_123 für 5x Gift! "
   
   RCON: Befehl an Minecraft senden
   
   ↓
   
4. RESULT: Minecraft führt aus
   Server: Chat zeigt "Danke an Streamer_Fan_123 für 5x Gift! "
   Alle Spieler sehen es
```

---

## Der interne Ablauf: Wie Befehle abgearbeitet werden

```
1. EVENT AUS QUEUE NEHMEN
   Gift-Event von Streamer_Fan_123
   
   ↓
   
2. ACTION NACHSCHLAGEN
   "Was soll bei einem Gift passieren?"
   → actions.mca Datei prüfen
   → Befehl: /say "Danke für Gift!"
   
   ↓
   
3. RCON-VERBINDUNG PRÜFEN
   Passwort: OK
   Port 25575: Erreichbar
   Server: Erreichbar
   
   ↓
   
4. BEFEHL SENDEN
   Befehl: /say "Danke für Gift!"
   
   ↓
   
5. HOFFEN DAS BEFEHL ANKOMMT
   Server: ...
   
   ↓
   
6. LOGGING & ABSCHLUSS
   Log: "Gift-Event verarbeitet, Befehl erfolgreich"
   Event ist erledigt
```

---

## Fehlerszenarien: Was kann schiefgehen?

| Problem | Folge | Lösung |
|---------|--------|--------|
| **RCON-Server nicht erreichbar** | Befehle können nicht gesendet werden | Minecraft-Server prüfen, Firewall-Einstellungen |
| **Falsches Passwort** | Authentifizierung fehlgeschlagen | Passwort in config.yaml überprüfen |
| **Falscher Port** | Verbindung schlägt fehl | Standard: 25575, in config.yaml überprüfen |
| **Befehl syntaktisch falsch** | Minecraft lehnt ab | Befehl in actions.mca überprüfen |
| **Zu viele Befehle pro Sekunde** | Minecraft kann nicht alle abarbeiten | Backlog aufgebaut, Spieler sieht zeitverzögerte Reaktion |
| **Minecraft-Server crasht** | RCON-Verbindung bricht ab | Auto-Reconnect nach Neustart |

---

## Zusammenfassung Phase 3

**Was passiert hier:**
- Event wird aus der Queue genommen
- Passender Minecraft-Befehl wird ermittelt
- Befehl wird über RCON an Minecraft gesendet
- Minecraft führt den Befehl aus
- Befehle werden **nacheinander** abgearbeitet (nicht parallel)

**Was nicht passiert hier:**
- Wir ändern den Spiele-Code (würde nicht funktionieren)
- Wir speichern Events (das ist eine separate Komponente)
- Wir zeigen etwas in der TikTok-App (das ist nicht möglich)

> [!NOTE]
> RCON ist synchron und blockiert. Bei vielen Befehlen pro Sekunde kann es zu Bottlenecks kommen. Deshalb verwenden manche Tools Minecraft-Funktionen (.mcfunction) für Batch-Operationen.
> (Macht das Streaming Tool auch kommen wir später drauf zu sprechen) 

---

## Das ganze System zusammen

Die 3 Phasen funktionieren nur zusammen:

```
Phase 1           Phase 2              Phase 3
EMPFANGEN    →   VERARBEITEN     →    AUSFÜHREN
  ↓                 ↓                    ↓
TikTokLive       Queue-System         RCON-Befehle
  ↓                 ↓                    ↓
Events rein      Events sortieren     Minecraft reagiert
```

**Wenn eine Phase ausfällt:**
- Keine Phase 1 → Keine Events
- Keine Phase 2 → Befehle sind falsch
- Keine Phase 3 → Minecraft reagiert nicht

> [!TIP]
> Wenn du verstehst, wie diese 3 Phasen zusammenhängen, verstehst du das ganze System. Die Details (wie RCON genau funktioniert, wie man Befehle schreibt, etc.) lernst du in den nächsten Kapiteln.

---

**Nächstes Kapitel:** [Python in diesem Projekt](./ch05-00-Python-in-This-Project.md) – Jetzt schauen wir, wie der Code diese 3 Phasen umsetzt.