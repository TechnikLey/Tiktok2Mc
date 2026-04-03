# Daten von TikTok empfangen (Phase 1)

In diesem Kapitel verstehst du, wie das System überhaupt **mitbekommt**, dass etwas auf TikTok passiert. Das ist die erste Komponente der Datenkette.

---

## Das Problem: Wie hören wir TikTok ab?

**Die Herausforderung:**

TikTok ist eine geschlossene Plattform. Es gibt keine offizielle, kostenlose API für Streamer, die in Echtzeit Events liefert. Wir müssen kreativ werden.

Wir nutzen also **Reverse Engineering** – wir beobachten, wie die TikTok-App selbst mit den Servern kommuniziert, und bauen darauf auf.

---

## Lösung: Die TikTokLive API

Wir verwenden die **TikTokLive** Bibliothek (Open Source), die genau das macht: Sie imitiert die TikTok-App und empfängt Events direkt.

### Wie funktioniert TikTokLive?

```
TikTok-Server
    ↓
    ├─→ (sendet Events zu Millionen Apps)
    ├─→ Offizielle TikTok App
    ├─→ Andere Live-Tool-Apps
    └─→ TikTokLive Library (unser Tool)
         ↓
    Wir sehen die Events LIVE
```

Die Bibliothek:
1. **Verbindet sich** mit TikTok-Servern (wie die Mobile App)
2. **Hört zu** auf dem WebSocket-Stream
3. **Empfängt Events** (Gifts, Follows, Likes) in Echtzeit
4. **Übergebe sie** an unser Python-Programm

### Was sind Events?

Ein **Event** ist eine strukturierte Nachricht, die TikTok sendet:

```
Event-Typ:    "Gift"
Benutzer:     "streamer_fan_123"
Gift-Anzahl:   5
Gift-Wert:     1000 Coins
```

Jeden dieser Daten kommt an. Das Programm kennt die Struktur und weiß, wie man sie ausliest.

---

## Womit verbinden wir uns? WebSocket vs HTTP

### WebSocket (wir nutzen das)

```
┌─ Verbindung ─┐
│  offen und   │  Beide Seiten können jederzeit
│  persistent  │  Daten senden. Perfekt für Echtzeit.
└──────────────┘
```

**Vorteile:**
- ✓ Echtzeit (sofortige Events)
- ✓ Effizient (ständig offen, nicht ständig neue Verbindungen)
- ✓ Bidirektional (wir können auch Daten zurückschicken)

**Nachteil:**
- ✗ Komplexer als HTTP

### HTTP (alte Alternative)

```
Wir fragen:  "Gibt es neue Events?"
Server:      "Ja hier!"
Wir fragen:  "Gibt es neue Events?"
Server:      "Nein"
Wir fragen:  "Gibt es neue Events?"
...
```

**Problem:** Ständiges Fragen ist ineffizient. Das ist wie ständig zu fragen "Bist du jetzt wach?" statt zu warten, bis dich die Person anruft.

---

## Der interne Ablauf: Wie Events ins Programm kommen

```
1. START: Programm startet
   ↓
2. CONNECT: Programm verbindet sich mit TikTok via WebSocket
   "Hallo TikTok, es ist dein Client"
   ↓
3. LISTEN: WebSocket bleibt offen
   Programm wartet auf Events
   ↓
4. EVENT KOMMT AN: User sendet Gift
   TikTok sendet: { "type": "gift", "user": "xyz", ... }
   ↓
5. EVENT EMPFANGEN: Unser Programm nimmt es entgegen
   ↓
6. EVENT WEITERGELEITET: An Phase 2 (Verarbeitung)
```

---

---

## Zusammenfassung Phase 1

**Was passiert hier:**
- TikTokLive Library verbindet sich mit TikTok
- Sie empfängt Events als strukturierte Daten
- Diese werden sofort an Phase 2 weitergeleitet

**Was du wissen solltest:**
- Events kommen LIVE (WebSocket, nicht HTTP)
- Ein Event hat Struktur: Typ, User, Daten
- Das Konzept von Events wurde bereits in [Grundkonzepte & Begriffe](./ch00-00-Fundamentals-and-Concepts.md) erklärt

**Was nicht passiert hier:**
- Wir analysieren Events nicht (das ist Phase 2)
- Wir senden nichts an Minecraft (das ist Phase 3)
- Wir speichern Events nicht dauerhaft

> [!TIP]
> Die TikTokLive Bibliothek ist nicht unbediengt sehr zuverlässig, aber es ist die beste Kostenlose Option. Gerne kannst du dir selbst mal alternativen anschauen.
> 
> Die Code-Implementierung der TikTokLive Bibliothek lernst du in [Python in diesem Projekt](./ch05-00-Python-in-This-Project.md).

---

**Nächstes Kapitel:** [Events verarbeiten](./ch01-02-Processing-Events.md) – Jetzt schauen wir, was das Programm MIT den Events macht.