# Grundkonzepte & Begriffe

Bevor wir in die Architektur und den Code einsteigen, müssen wir die **Kernideen** verstehen. Dieses Kapitel behandelt nur die essentiellen Konzepte – alles andere wird in den Folgenden Kapiteln detailliert erklärt.

---

## Was ist dieses Streaming Tool?

Das Streaming Tool verbindet **TikTok-Events** mit **Minecraft** – in Echtzeit.

**Der Ablauf:**

```
Zuschauer auf TikTok
    ↓
sendet Gift / folgt / liked
    ↓
TikTok-Server benachrichtigt das Tool
    ↓
Das Tool führt einen Minecraft-Befehl aus
    ↓
Etwas passiert zwischen Minecraft Spiel
```

**Praktisches Beispiel:**
- Streamer ist live auf TikTok
- Zuschauer sendet ein Gift
- Minecraft-Server erhält: `/say "Danke für das Gift!"`
- Alle Spieler sehen die Nachricht

---

## Kernidee: Events → Aktionen

Das ganze System basiert auf einem einfachen Prinzip:

```
EVENT (Etwas ist passiert)
    ↓
VERARBEITUNG (Was bedeutet das?)
    ↓
AKTION (Was soll passieren?)
```

**Drei zentrale Konzepte:**

### 1. **Events** – Das Eingangssignal

Ein **Event** bedeutet: Etwas ist passiert.

Beispiele:
- User sendet ein Gift
- User folgt dem Kanal
- User liked den Stream

> [!NOTE]
> Events sind strukturierte Daten – sie haben Eigenschaften wie "Wer?", "Wann?", "Was?", "Wie viel?". Mehr in [Wie das System Arbeitet](./ch01-00-How-the-System-Works-Together.md).

### 2. **Verarbeitung** – Das "verstehen"

Das Programm nimmt das Event und fragt:
- "Was ist das für ein Event?" (Gift / Follow / Like?)
- "Von wem kommt es?"
- "Ist das wichtig?"

### 3. **Warteschlange (Queue)** – Die Ordnung

Wenn 100 Events gleichzeitig eintreffen, können sie nicht alle sofort an Minecraft gehen. Stattdessen:

```
Events kommen an → werden in Queue gelegt → nacheinander verarbeitet
```

Die Queue verhindert Chaos und Überlastung.

> [!NOTE]
> Stell dir den Supermarkt vor: Alle Kunden stellen sich an der Kasse an. Einer nach dem anderen wird bedient – faire, geordnete Verarbeitung.

---

## Die 3 Phasen (Überblick)

Das System arbeitet in 3 Phasen (Details in [Wie das System Arbeitet](./ch01-00-How-the-System-Works-Together.md)):

| Phase | Was passiert | Ergebnis |
|-------|--------------|----------|
| **1. Empfangen** | TikTok-Events werden empfangen | Strukturierte Event-Daten |
| **2. Verarbeiten** | Events werden klassifiziert | Klare Kategorien (Gift/Follow/Like/...) |
| **3. Ausführen** | Befehl wird an Minecraft gesendet | Minecraft-Aktion wird ausgelöst |

---

## Konfiguration vs Code

Eine wichtige Idee: **Konfiguration ist getrennt vom Code.**

Das bedeutet:
- **Code**: Die Logik "wie funktioniert das Tool?"
- **Konfiguration**: Die Regeln "was soll passieren, wenn geschieht?"

Du kannst neue Aktionen hinzufügen **ohne eine einzige Codezeile zu ändern** – nur durch Bearbeitung der Konfiguration.

> [!NOTE]
> Details dazu in späteren Kapiteln

---

## Zusammenfassung: Die Grundidee

Das System funktioniert nach diesem Muster:

```
EVENT eintreffen
    ↓
In Warteschlange legen
    ↓
Eine nach dem anderen verarbeiten
    ↓
Entsprechende Aktion ausführen
    ↓
Minecraft reagiert
```

Das ist das ganze Konzept. Alles andere sind **Details und Implementierungen**.

---

## Wo geht es weiter?

Jetzt, da du die Grundidee kennst:

- **[Nächstes Kapitel: Lokale Entwicklung einrichten](./ch00-01-Setting-Up-Local-Development.md)** → Setup auf deinem Rechner
- **[Dann: Wie das System zusammenarbeitet](./ch01-00-How-the-System-Works-Together.md)** → Architekturfür mittel Detail

Danach werden wir tiefer in Code, Konfiguration und spezifische Features gehen.

> [!NOTE]
> Keine Sorge, wenn nicht alles sofort klar ist. Jede Idee wird später mit Beispielen und Details erklärt!