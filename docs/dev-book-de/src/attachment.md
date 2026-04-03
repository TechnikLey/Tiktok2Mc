# Anhang

Der Anhang ist ein **Nachschlagewerk** für Themen, die in den Hauptkapiteln zu tief gehen würden oder zusätzliche Kontexte bieten.

Hier findest du:

- **Projektstruktur** – Dateien & Ordner verstehen
- **Konfiguration** – Config-Details & Migration
- **Update-Prozess** – Wie Updates funktionieren
- **Glossar** – Alle Fachbegriffe erklärt (sehr wichtig!)

---


## Was ist im Anhang?
### [Plugins ohne Python (main.exe-Pflicht)](./create-a-plugin-without-Python.md)

Wie du Plugins in anderen Sprachen als Python schreibst, was du bei der Registrierung beachten musst und warum **main.exe** Pflicht ist. Auch wie du von main.exe aus andere Dateien/Skripte aufrufen kannst.

[Kapitel öffnen](./create-a-plugin-without-Python.md)

---

### [Glossar](./glossary.md) **START HIER bei Unklarheiten**

Das ist dein **Nachschlagewerk**. Wenn du einen Begriff nicht verstehst:

- **Event** – Was ist das?
- **Queue** – Wie funktioniert eine Warteschlange?
- **DCS/ICS** – Was ist der Unterschied?
- **Threading** – Warum ist das wichtig?
- Und 50+ weitere Begriffe!

[Glossar öffnen](./glossary.md)

---

### [Core-Module der Infrastruktur](./core-modules.md) 

Für **Fortgeschrittene Entwickler**: Verstehe die technische Infrastruktur:

- **paths.py** – Pfad-Management
- **utils.py** – Konfiguration laden
- **models.py** – Datenstrukturen (AppConfig)
- **validator.py** – Syntax-Validierung
- **cli.py** – Command-Line Arguments

Hier erfährst du, wie die Core-Module zusammenarbeiten und wie Plugins sie nutzen.

[Core-Module öffnen](./core-modules.md)

---

### [Projektstruktur](./project-structure.md)

Verstehe, wie das Projekt organisiert ist:

- **src/** – Quellcode
- **defaults/** – Template-Konfigurationen
- **config/** – Nutzer-Einstellungen
- **data/** – Persistent gespeicherte Daten
- **build/release/** – Fertige Distribution

**Wichtig:** Unterschied zwischen **Entwicklungsstruktur** und **Release-Struktur**.

[Projektstruktur öffnen](./project-structure.md)

---

### [Konfiguration](./config.md)

Details zur `config.yaml`:

- Wie lädt man Konfiguration im Code?
- Was ist `config_version`?
- Wie funktioniert Config-Migration?
- Wo kommen die Werte hin?

[Config-Details öffnen](./config.md)

---

### [Update-Prozess](./update.md)

Für Maintainer & Advanced Developers:

- Wie werden Updates heruntergeladen?
- Was wird überschrieben, was nicht?
- Wie aktualisiert sich der Updater selbst?
- Welche Dateien sind sicher?

[Update-Prozess öffnen](./update.md)

---

## Wann nutze ich den Anhang?

| Situation | Anhang-Kapitel |
|-----------|------------------|
| "Ich verstehe diesen Begriff nicht" | → **Glossar** |
| "Wie funktioniert die Infrastruktur?" | → **Core-Module** |
| "Wo ist das config.yaml File?" | → **Projektstruktur** |
| "Welche Config-Keys gibt es?" | → **Konfiguration** |
| "Wie testen wir Updates?" | → **Update-Prozess** |
| "Ich schreibe einen Maintainer-Guide" | → Alle oben |
| "Wie schreibe ich ein Plugin ohne Python?" | → Plugins ohne Python |

---

## Der Anhang wird ständig erweitert

Falls du noch Themen vermisst, die hier sein sollten:

- Datenbank-Schema
- Performance-Optimization-Guide
- API-Dokumentation
- Migration-Guides

...dann gib Feedback oder schreib es selbst! 

---

## Siehe auch

- **[Glossar](./glossary.md)** – Das wichtigste Nachschlagewerk
- **[Debugging & Troubleshooting](./ch06-00-Debugging-and-Troubleshooting.md)** – Wenn etwas nicht funktioniert
- **[Hauptdokumentation](./introduction.md)** – Zurück zum Hauptinhaltsverzeichnis