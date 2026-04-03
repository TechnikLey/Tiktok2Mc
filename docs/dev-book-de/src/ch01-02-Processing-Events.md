# Events verarbeiten (Phase 2)

Jetzt sind die Rohdaten angekommen. Aber sind sie auch nutzbar? In diesem Kapitel lernst du, wie das System Events "versteht" und für die nächste Phase vorbereitet.

---

## Das Problem: Daten sind roh

Von Phase 1 bekommen wir Rohdata von TikTok:

```
{
  "type": "gift",
  "user": { "id": 12345, "name": "xyz" },
  "gift": { "id": 5, "count": 10, "repeatCount": 1 },
}
```

**Fragen, die wir beantworten müssen:**

- ✓ "Was ist das für ein Event?" (Gift / Follow / Like?)
- ✓ "Von wem kommt es?" (Welcher User?)
- ✓ "Wie viel ist es?" (Wert, Anzahl, Menge?)
- ✓ "Ist es wichtig?" (Sollte das Spiel reagieren?)
- ✓ "Was ist die nächste Aktion?" (Welcher Befehl soll an Minecraft?)

---

## Lösung: Das Event-Processing-System

### Schritt 1: Klassifizieren

Das Programm sortiert das Event in eine Kategorie:

```
Rohdaten ankommen
    ↓
"Ist das ein Gift?"
    ↓
"Ja → Das ist die 'Gift'-Kategorie"
    ↓
Event wird als "GiftEvent" registriert
```

Das System kennt verschiedene Typen:

| Typ | Beispiel |
|-----|----------|
| **Gift** | User sendet 5x Gifts |
| **Follow** | User folgt dem Kanal |
| **Like** | User liked einen Stream |
| **Share** | User teilt den Stream |
| **Comment** | User kommentiert |

### Schritt 2: Daten extrahieren

Aus den Rohdata werden die wichtigen Informationen herausgezogen:

```
Rohdaten: {
  "type": "gift",
  "user": { "id": 12345, "name": "streamer_fan_xyz", ... },
  "gift": { "id": 5, "count": 3, ... }
}

        ↓ [EXTRAHIERT]

Strukturierte Daten:
├─ Event-Typ: "gift"
├─ User-Name: "streamer_fan_xyz"
├─ Gift-Anzahl: 3
```

Nur die Daten, die interessant sind, werden behalten.

### Schritt 3: In Warteschlange legen

**Das Problem:** Wenn 100 Zuschauer gleichzeitig Gifts senden, können nicht alle gleichzeitig an Minecraft gehen.

**Die Lösung:** Eine **Queue (Warteschlange)** – wie schon in [Grundkonzepte](./ch00-00-Fundamentals-and-Concepts.md) erklärt.

Die Queue sorgt dafür, dass alles der Reihe nach verarbeitet wird – fair und ordentlich.

---

## Der interne Ablauf: Wie Events verarbeitet werden

```
1. EVENT ANKOMMT von Phase 1
   ↓
2. KLASSIFIZIEREN
   "Das ist ein Gift"
   ↓
3. DATEN EXTRAHIEREN
   User = "xyz", Anzahl = 5
   ↓
4. IN QUEUE ENQUEUE
   Eintrag in der Warteschlange
   ↓
5. QUEUE ARBEITET AB
   Ein Event nach dem anderen
   ↓
6. AN PHASE 3 WEITERGEBEN
   "Gift von xyz, 5x → Minecraft!"
```

---

## Mehrere Events gleichzeitig (Concurrency)

Das System muss mit vielen Events gleichzeitig umgehen. Die Queue ist die Lösung.

Die Queue ist normalerweise sehr klein – Events werden sofort weiterverarbeitet. Sie ist kein Speicher, sondern eine **Warteschlange**.

---

## Spezial-Filter: Nicht alle Events sind gleich

Das System kann Events priorisieren – Gifts sind wichtiger als Likes, zum Beispiel.

Diese Prioritäten werden in der **Konfiguration** festgelegt, nicht im Code.

---

## Fehlerszenarien: Was kann schiefgehen?

| Problem | Folge | Lösung |
|---------|--------|--------|
| **Event-Struktur unbekannt** | Klassifizierung fehlgeschlagen | Error-Log, Event wird verworfen |
| **Queue läuft über** | Speicher-Problem (sehr selten) | Ältere Events löschen |
| **Zu viele Events pro Sekunde** | Backlog aufgebaut | Minecraft braucht länger zu reagieren |
| **Event kommt beschädigt an** | Daten-Parse-Fehler | Validierung im System, fehlerhafte Events ignoriert |

---

## Zusammenfassung Phase 2

**Was passiert hier:**
- Raw Events werden klassifiziert
- Daten werden extrahiert und strukturiert
- Events werden in eine Warteschlange gelegt
- Queue verarbeitet sie der Reihe nach

**Was du wissen solltest:**
- Die Queue sorgt für Ordnung
- Mehrere Events werden nacheinander, nicht parallel verarbeitet

**Was nicht passiert hier:**
- Wir schreiben Events nicht zur Festplatte (optional)
- Wir senden nichts an Minecraft (nächste Phase)
- Wir zeigen nichts in der GUI (wird separat gemacht)

---

**Nächstes Kapitel:** [Daten an Minecraft senden](./ch01-03-Sending-Data-to-Minecraft.md) – Jetzt wird's konkret: Der Befehl geht ans Spiel!