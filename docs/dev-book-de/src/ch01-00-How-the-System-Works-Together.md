# Wie das System zusammenarbeitet

In diesem Kapitel verstehst du die **Architektur** des Streaming Tools – also wie die einzelnen Komponenten zusammenpassen und Daten von TikTok bis zu Minecraft fließen.

---

## Das große Bild: Der Datenflusss

Das System arbeitet nach einem klaren, dreiphasigen Muster:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DIE 3 PHASEN DES SYSTEMS                     │
└─────────────────────────────────────────────────────────────────┘

Phase 1: EMPFANGEN
    TikTok-Events
        ↓
    TikTokLive API
        ↓
    "User XY hat gefolgt"

           ↓ ↓ ↓

Phase 2: VERARBEITEN
    Event analysieren
        ↓
    Daten filtern & sortieren
        ↓
    "Ist das ein Follow? Von wem? Wann?"

           ↓ ↓ ↓

Phase 3: AUSFÜHREN
    Aktion triggern
        ↓
    RCON-Befehl senden
        ↓
    Minecraft führt aus
```

Jede Phase hat eine klare Aufgabe:

| Phase | Aufgabe | Wer macht es? |
|-------|---------|---------------|
| **1. Empfangen** | Daten von TikTok-Servern abholen | TikTokLive API (in unserem Programm) |
| **2. Verarbeiten** | Events verstehen & dokumentieren | Python-Skripte analyzieren die Rohdaten |
| **3. Ausführen** | Befehl an Minecraft schicken | RCON über Netzwerk-Verbindung |

---

## Phase 1: Daten von TikTok empfangen

**Das Problem:** Wie kriegen wir überhaupt mit, wenn jemand auf TikTok ein Gift sendet?

TikTok hat keine offene **offizielle API** für Entwickler. Deswegen verwendet wir die **TikTokLive-Bibliothek**

Das Programm verbindet sich mit TikToks Servern und **lauscht**.

Sobald eine Aktion passiert (Gift, Follow, Like), bekommen wir eine Nachricht. Diese Nachricht ist wie folgt strukturiert:

```
{
  "Event": "Gift",
  "Von": "BenutzerName",
  "GiftID": "12345",
}
```

**Was passiert danach?** Die Daten gehen direkt zur nächsten Phase → **Verarbeiten**

> [!NOTE]
> **Für Anfänger:** Stell dir vor, du liest eine Nachricht. Der Text ist noch nicht sortiert – du muss zuerst verstehen, wer schreibt, was wird geschrieben, wann wurde es geschrieben.

---

## Phase 2: Events verarbeiten und analysieren

**Das Problem:** Die Rohdaten von TikTok sind unstrukturiert. Wir müssen sie klassifizieren und strukturieren, bevor wir damit etwas anfangen können.

Das Programm nimmt das empfangene Event und fragt:

- **"Was ist passiert?"** (Gift / Follow / Like / Etc.)
- **"Wer war es?"** (Benutzername, User-ID)
- **"Wie viel?"** (Anzahl der Gifts, Größe des Gifts)
- **"Was soll jetzt passieren?"** (Welche Minecraft-Aktion triggert das?)

Das System **kategorisiert** Events intern und **speichert wichtige Metadaten**. Diese werden dann in eine Warteschlange (Queue) gelegt, damit sie nacheinander verarbeitet werden können.

**Warum eine Warteschlange?** 

Wenn 100 Zuschauer gleichzeitig Gifts senden, können nicht alle Events gleichzeitig an Minecraft gehen. Das würde den Server überlasten. Stattdessen werden sie aufgereiht und der Reihe nach abgearbeitet.

> [!NOTE]
> **Für Anfänger:** Denk an den Supermarkt-Kassierer. Wenn 10 Leute gleichzeitig kommen, stellt man sich an. Einer nach dem anderen zahlt. Die Warteschlange sorgt für Ordnung.

---

## Phase 3: Daten an Minecraft senden

**Das Problem:** Wie sagen wir dem Minecraft-Server, was passieren soll?

Minecraft hat ein Remote Control System namens **RCON** (Remote Console). Das ist wie eine Fernbedienung für den Minecraft-Server.

Über RCON können wir Befehle senden:

- `/say "Danke für das Gift!"`
- `/give @s diamond 5`
- `/function my_namespace:special_event`

Das Programm:
1. Bestimmt, welcher Befehl nötig ist (basierend auf dem Event)
2. Sendet ihn über RCON an Minecraft
3. Der Minecraft-Server führt den Befehl aus

Das alles passiert in **Echtzeit** – normalerweise in Millisekunden.

---

## Zusammenhang: So hängt alles zusammen

Das Wichtigste: **Die 3 Phasen sind voneinander abhängig:**

```
(1) Empfangen  →  (2) Verarbeiten  →  (3) Ausführen
      ↓               ↓                   ↓
  TikTok API     Python-Logik         RCON-Befehl
```

Wenn eine Phase ausfällt, funktioniert die ganze Kette nicht mehr:

| Wenn Phase ausfällt | Folge |
|-------------------|--------|
| **1 bricht** | Keine Events von TikTok → Nichts passiert |
| **2 bricht** | Events werden nicht verstanden → Falsche Aktion oder gar keine |
| **3 bricht** | Befehl erreicht Minecraft nicht → Game hat keine Reaktion |

---

## Nächste Schritte

Jede dieser 3 Phasen wird in diesem Kapitel im Detail erklärt:

- [Daten von TikTok empfangen](./ch01-01-Receiving-Data-from-TikTok.md) – Wie die API funktioniert
- [Events verarbeiten](./ch01-02-Processing-Events.md) – Wie das Programm Daten analysiert
- [Daten an Minecraft senden](./ch01-03-Sending-Data-to-Minecraft.md) – Wie RCON funktioniert

Wenn du die Grundidee verstanden hast, kannst du die Unterkapitel lesen, um tiefer einzusteigen.

> [!NOTE]
> **Konzepte:** Grundideen (Events, Queue, etc.) wurden bereits kurz in [Grundkonzepte & Begriffe](./ch00-00-Fundamentals-and-Concepts.md) erklärt. Dieses Kapitel zeigt die **Architektur**.
> 
> **Code & Details:** Wie Handler funktionieren (`@client.on`), wie `actions.mca` geschrieben wird, Control Methods (DCS/ICS), etc. – das kommt in späteren Kapiteln.

> [!TIP]
> Falls dir die Architektur noch nicht 100% klar ist: Das ist völlig normal. Viele Konzepte werden in den kommenden Kapiteln noch konkreter.