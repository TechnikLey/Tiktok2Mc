# Einführung

> [!CAUTION]
> **Hinweis zur Aktualität und Genauigkeit dieser Dokumentation**
>
> Ich bemühe mich, diese Entwicklerdokumentation so aktuell wie möglich zu halten. Da ich gleichzeitig am eigentlichen Projekt weiterarbeite und die Dokumentation allein pflege, ist es nicht immer möglich, jede Änderung sofort nachzutragen.
>
> **Bitte beachte daher Folgendes:**
> 
> - **Kennzeichnung veralteter Kapitel** Kapitel die veraltet sind werden nach Möglichkeit gekennzeichnet. Dennoch kann es vorkommen, dass auch unmarkierte Abschnitte nicht mehr dem aktuellen Stand des Codes entsprechen.
> - **Nutzung von KI:** Einige Textpassagen wurden mit Hilfe von KI erstellt. Ich prüfe diese, kann aber nicht garantieren, dass keine Fehler enthalten sind.
> - **Allgemeine Fehler** wie Tippfehler, ungenaue Beschreibungen oder veraltete Codebeispiele können vorkommen – auch in manuell verfassten und unmarkierten Abschnitten.
> - **Deine Hilfe zählt**, wenn dir falsche oder veraltete Kapitel auffallen, melde es gerne über ein GitHub Issue – das hilft, die Dokumentation für alle zu verbessern.
>
> Sieh diese Dokumentation als hilfreichen Leitfaden, aber wenn Dokumentation und Quellcode widersprechen hat der Quellcode immer recht.

Willkommen zur Entwicklerdokumentation des **Streaming Tools** – ein Projekt, das **TikTok-Events** mit **Minecraft** verbindet.

Diese Dokumentation richtet sich an Entwickler, die verstehen wollen:

- **Wie das System intern funktioniert**
- **Wie die Daten fließen** (TikTok → Verarbeitung → Minecraft)
- **Wie man das Projekt erweitert** (eigene Plugins schreiben, Features anpassen)

---

## Wo Starten?

| Profil | Empfohlener Einstieg |
|--------|----------------------|
| **Python-Grundlagen vorhanden** | Start mit [Grundkonzepte](./ch00-00-Fundamentals-and-Concepts.md), dann [Setup](./ch00-01-Setting-Up-Local-Development.md) |
| **Erweiterte-Python-Kenntnisse vorhanden** | [System-Überblick](./ch01-00-How-the-System-Works-Together.md) → [Python in diesem Projekt](./ch05-00-Python-in-This-Project.md) |
| **System erweitern & anpassen mit Python** | Direkt zu [Plugin-Entwicklung](./ch02-00-Create-your-own-plugin.md) oder [Eigenen $ Befehle](./ch03-06-Creating-Your-Own-$-Command.md) |
| **Debuggen / Troubleshooting** | [Debugging & Troubleshooting](./ch06-00-Debugging-and-Troubleshooting.md) |

> [!NOTE]
> Wenn du Kenntnise in anderen Programmiersprachen als Python hast, dann kannst du gerne direkt zu
> [Plugin ohne Python erstellen](./create-a-plugin-without-Python.md) gehen.
> Trozdem solltest du dir einige Kapitel anschauen um besser zu verstehen wie das System Arbeitet.
> Dies hilft dir weiter auch wenn du kein Python kannst.
> Ich Empfehle dir auch [Eigenes Plugin erstellen](./ch02-00-Create-your-own-plugin.md) anzuschauen auch wenn dies Primär für Python geschrieben ist gibt es dort einige Infos die wichtig sind.

---

## Umfang & Fokus

Das Projekt umfasst etwa **3.000–4.000 Zeilen Python-Code**. Wir analysieren nicht jede einzelne Zeile – das würde sinnlos sein.

Stattdessen konzentrieren wir uns auf:

- **Architektonische Kernkomponenten** – Wie ist das System aufgebaut?
- **Datenflüsse** – Wie bewegen sich Daten durch das System?
- **Muster & Best Practices** – Worauf solltest du achten?
- **Praktische Anwendung** – Wie schreibe ich mein eigenes Plugin?

**Im Code selbst** findest du zusätzliche Kommentare, die als Wegweiser für spezifische Details dienen.

---

## Voraussetzungen

 > [!NOTE]
> Diese Dokumentation erklärt die Funktion des **Streaming-Tool-System** – nicht aber die Python-Grundlagen selbst.
> 
> **Du brauchst folgende Vorkenntnisse:**
> - **Grund-Begriffe der Python-Programmierung** (Funktionen, Klassen, Loops)
> - **Command-Line / Terminal** Navigation
> - **Dateisystem** Grundverständnis
> 
> **Wenn dir diese Konzepte neu sind:** Bearbeite zuerst einen Anfänger-Python-Kurs, z.B. [Python.org Tutorial](https://docs.python.org/3/tutorial/) oder [Codecademy Python Course](https://www.codecademy.com/learn/learn-python-3). Da wir diese Grundlagen hier voraussetzen, sparen wir Platz für Tiefe statt für Wiederholung.

Zusätzlich brauchst du:

- **Python 3.12+**
- **Git** (zum Klonen des Repositories)
- Einen **Editor oder IDE** (VS Code, PyCharm, etc.)

Alles Setup erforderlich wird in [Lokale Entwicklung einrichten](./ch00-01-Setting-Up-Local-Development.md) Schritt-für-Schritt erklärt.

---

## Struktur der Dokumentation

```
00 GRUNDLAGEN
  ├─ Fundamentals & Concepts (Was ist dieses System?)
  └─ Local Development Setup (Wie richte ich das auf?)

01 SYSTEM-ÜBERBLICK
  ├─ Wie das System zusammenarbeitet
  ├─ Daten von TikTok empfangen
  ├─ Daten verarbeiten
  └─ Daten an Minecraft senden

02 PYTHON & EVENTS (Kernlogik)
  ├─ Python in diesem Projekt
  ├─ Die main.py Datei
  ├─ TikTok-Client & Event-Handler
  │  └─ Gift-Events, Follow-Events, Like-Events
  └─ Threading & Warteschlangen

03 MINECRAFT-INTEGRATION
  ├─ Von Event zum Command
  ├─ Die actions.mca Datei
  ├─ Mapping-Logik
  └─ mcfunction Dateien

04 SYSTEM-ARCHITEKTUR
  ├─ Modulare Struktur
  ├─ Control Methods (DCS vs. ICS)
  ├─ PLUGIN_REGISTRY
  └─ Integration mit Streaming-Software

05 PLUGIN-ENTWICKLUNG
  ├─ Plugin-Struktur & Setup
  ├─ Events & Webhooks
  ├─ Config & Datenspeicherung
  ├─ GUI mit pywebview
  ├─ Inter-Plugin-Kommunikation
  └─ Fehlerbehandlung & Best Practices

06 ADVANCED
  └─ Debugging & Troubleshooting (Problem-Lösung)

ANHANG
  ├─ Projektstruktur
  ├─ Config-Details
  ├─ Update-Prozess
  └─ Glossar (Begriffe erklärt)
```

Die Dokumentation ist **progressiv aufgebaut**: Jedes Kapitel baut auf den vorherigen auf. **Du kannst aber jederzeit zu Themen springen, die dich interessieren.**

---

## Empfohlene Lesereihenfolge

**Option 1: Kompletter Durchgang (beste Vorbereitung)**

1. [Grundkonzepte](./ch00-00-Fundamentals-and-Concepts.md)
2. [Setup](./ch00-01-Setting-Up-Local-Development.md)
3. [System-Überblick](./ch01-00-How-the-System-Works-Together.md)
4. [Event-Verarbeitung](./ch05-00-Python-in-This-Project.md)
5. [Minecraft-Integration](./ch03-00-Mapping-Events-to-Minecraft.md)
6. [System-Architektur](./ch04-00-System-Modules-and-Integration.md)
7. [Plugin-Entwicklung](./ch02-00-Create-your-own-plugin.md)

**Option 2: Schnelleinstieg für Erfahrene**

1. [Grundkonzepte](./ch00-00-Fundamentals-and-Concepts.md) (10 Minuten)
2. [Plugin-Entwicklung](./ch02-00-Create-your-own-plugin.md)
3. Dann: Spezifische Kapitel je nach Interesse

---

## Der Anhang

Zusätzlich zu den Hauptkapiteln gibt es einen [Anhang](./attachment.md). Der Anhang enthält:

- **Projektstruktur**: Dateien & Ordner im Detail
- **Config-Details**: Konfigurationsdatei verstehen & erweitern
- **Update-Prozess**: Wie Updates funktionieren (für Maintainer)
- **Glossar**: Alle Fachbegriffe erklärt

Der Anhang ist ein **Nachschlagewerk** – du musst ihn nicht linear lesen.

---

## Wie du diese Dokumentation am besten nutzt

1. **Finde dein Level**: Anfänger? Dann start mit [Grundkonzepte & Begriffe](./ch00-00-Fundamentals-and-Concepts.md).
2. **Lies progressiv**: Kapitel bauen aufeinander auf.
3. **Überspringe nichts leicht**: Wenn etwas unklar ist, geh zurück zu vorherigen Kapiteln.
4. **Nutze das Glossar**: Unbekannte Begriffe? [Glossar](./glossary.md).
5. **Experimentiere**: Lesen ist wichtig, aber **selbst programmieren ist entscheidend**.

---

## Code-Beispiele in dieser Dokumentation

Wo wir Code-Beispiele zeigen, nutzen wir diese Formatierung:

```python
# Beispiel-Python-Code
from TikTokLive import TikTokLiveClient

client = TikTokLiveClient(unique_id="my_account")
```

## Info-Blöcke

> [!TIP]
> Praktische Empfehlung, Trick oder Best Practice, um die Arbeit zu erleichtern oder zu verbessern.

> [!NOTE]
> Ergänzende Information oder Hintergrundwissen. Nicht kritisch, aber oft hilfreich zum besseren Verständnis.

> [!IMPORTANT]
> Pflicht-Information oder harte Voraussetzung. Muss zwingend beachtet werden, damit etwas funktioniert. Nicht optional.

> [!WARNING]
> Hier besonders aufmerksam sein! Kann zu Fehlern, Problemen oder unerwartetem Verhalten führen, aber nichts wird dauerhaft beschädigt.

> [!CAUTION]
> Kritischer Hinweis! Falsche Anwendung kann zu Datenverlust, Systemfehlern oder nicht rückgängig machbaren Schäden führen.

---

## Fehler gefunden? Fragen?

Diese Dokumentation wird ständig verbessert. Falls du:

- **Fehler findest** → GitHub Issue öffnen
- **Etwas unklar ist** → Frag eine KI oder andere Entwickler
- **Ideen hast** → Feedback geben im Repository

---

## Viel Erfolg!

Du bist bereit. Starten wir:

**→ [Grundkonzepte & Begriffe](./ch00-00-Fundamentals-and-Concepts.md)**

oder

**→ [Lokale Entwicklung einrichten](./ch00-01-Setting-Up-Local-Development.md)**