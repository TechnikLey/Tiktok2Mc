# Projektstruktur: Entwicklung vs Release

> [!WARNING]
> Dieser Teil der Dokumentation wird nur wenig gepflegt.
> Es kann daher vorkommen, dass Inhalte veraltet sind oder teilweise automatisch von KI erstellt wurden und deswegen Fehlerhaft sind.

### Zwei unterschiedliche Strukturen

Das Projekt hat zwei völlig verschiedene Ordnerstrukturen:

1. **Entwicklungsstruktur** (zum Arbeiten) → Quellcode, Tests, Docs
2. **Release-Struktur** (für Benutzer) → Compilierte EXEs, fertige Config

> [!WARNING] 
> Du MUSST immer die richtige Struktur für die Situation nutzen. Falsche Pfade = Fehler!

### Entwicklungs-Struktur (zum Entwickeln)

```
Streaming_Tool/                 ← Root (hier arbeitest du)
├── src/                        ← QUELLCODE
│   ├── python/                 ← Python-Dateien
│   ├── plugins/                ← Plugin-Quellcode
│   └── core/                   ← Core-Module
├── defaults/                   ← Template-Dateien
│   ├── config.default.yaml     ← Config-Vorlage
│   ├── actions.mca             ← Befehls-Template
│   └── ...
├── docs/                       ← Dokumentation (hier!)
├── build.ps1                   ← Build-Skript
├── build/                      ← Build-Zwischenprodukte
│   └── cache/                  ← Cached EXEs
└── tests/                      ← Unit Tests
```

### Release-Struktur (Was Benutzer bekommen)

```
build/release/                  ← FERTIG ZUM AUSFÜHREN
├── core/                       ← Compilierte EXEs
│   ├── app.exe                 ← Hauptprogramm
│   ├── update.exe              ← Updater
│   └── runtime/                ← .NET Runtime
├── config/                     ← User-Einstellungen
│   ├── config.default.yaml     ← Vorlage (nicht editieren!)
│   └── config.yaml             ← User kopiert diese!
├── data/                       ← Persistente Daten
│   ├── plugin_state.json       ← Status speichern
│   └── logs/                   ← Fehlerprotokoll
├── plugins/                    ← Fertige Plugin-EXEs
│   ├── deathcounter.exe
│   ├── timer.exe
│   └── ...
├── version.txt                 ← Version & Updater-Version
├── README.md                   ← Info für Benutzer
└── LICENSE                     ← Lizenz
```

### Wichtige Unterschiede

| Aspekt | Entwicklung | Release |
|--------|-------------|---------|
| **Pfad bei Code** | `src/python/` | `./` (EXE läuft von Release-Root) |
| **Config laden** | `defaults/config.yaml` | `config/config.yaml` |
| **Daten speichern** | PROJECT_ROOT/data | `./data/` (relativ zur EXE) |
| **Logs** | `.../logs/` | `./data/logs/` |
| **Erzeugt durch** | (du schreibst) | `build.ps1` generiert |

### Critical Rules

- ☑ **Immer Release-Pfade im Code** (sobald es deployed wird)
- ☑ **Config NIEMALS im Quellcode** (immer relativ `./config/`)
- ☑ **Data bleibt über Updates** (`./data/` wird nicht gelöscht)
- ☑ **Docs entwickeln im dev-Ordner** (`docs/dev-book-de/src/`)
- ☑ **Nach Änderungen: build.ps1 testen** (überprüft Pfade)

→ [Zurück zu Anhang](./attachment.md)

> [!WARNING]
> Beachte unbedingt, dass du bei Dateipfaden und anderen dateibezogenen Vorgängen immer die [Release-Struktur](#release-struktur) verwendest.
> Die [Entwicklungsstruktur](#entwicklungsstruktur) unterscheidet sich deutlich von der [Release-Struktur](#release-struktur).
> Wenn du versehentlich Pfade aus der Entwicklungsstruktur verwendest, kann das zu Fehlern führen, weil Dateien im Release an einem anderen Ort liegen oder dort anders aufgebaut sind.
>
> Achte besonders auf folgende Punkte:
>
> - Verwende in Code, Skripten und Dokumentation immer die Pfade aus der Release-Struktur, wenn es um das fertige Projekt geht.
> - Verlasse dich nicht darauf, dass Entwicklungsdateien im Release ebenfalls vorhanden sind.
> - Prüfe bei neuen Dateien oder Ordnern, ob sie durch `build.ps1` korrekt ins Release übernommen werden.
> - Wenn du Konfigurationen oder Laufzeitdaten änderst, überlege genau, ob sie in `config/`, `data/`, `core/` oder `runtime/` gehören.
> - Teste nach Änderungen immer den Build, damit keine fehlenden Pfade oder kaputten Verweise übersehen werden.
> - Stelle sicher, dass Updates keine wichtigen Daten überschreiben, insbesondere in den Verzeichnissen `data/` und `config/`.

---

## Entwicklungsstruktur

Die Entwicklungsstruktur enthält alles, was für den Aufbau des Projekts gebraucht wird.

```text
.
├── assets
│   └── gifts_picture
├── build
│   ├── exe_cache
│   └── release
├── build.ps1
├── defaults
│   ├── actions.mca
│   ├── config.default.yaml
│   ├── config.yaml
│   ├── configServerAPI.yml
│   ├── DelayedTNTconfig.yml
│   ├── gifts.json
│   ├── http_actions.txt
│   └── pack.mcmeta
├── docs
│   └── dev-book
├── LICENSE
├── README.md
├── src
│   └── python
├── static
│   └── css
├── templates
│   ├── db.html
│   └── index.html
├── tests
├── tools
│   ├── DelayedTNT.jar
│   ├── Java
│   ├── MinecraftServerAPI-1.21.x.jar
│   └── server.jar
└── upload.ps1
```

### `assets/`

Hier liegen die visuellen Ressourcen des Projekts.
Der Unterordner `gifts_picture/` enthält Bildmaterial für die Geschenke.

### `build/`

Dieser Ordner dient dem Build-Prozess.
Er enthält keine eigentliche Entwicklungslogik, sondern nur Zwischenergebnisse und die fertige Ausgabe.

* `exe_cache/` speichert EXE-Daten, um diese nicht jedes Mal neu generieren zu müssen.
* `release/` ist der Zielordner für das fertige Projekt.
* Zudem finden sich dort Hash-Dateien. Diese sind dafür da, damit das Programm weiß, ob es eine EXE neu bauen muss oder diese aus dem `exe_cache`-Ordner kopieren soll.

### `build.ps1`

Das Build-Skript ist der zentrale Motor des Projekts.
Es sammelt die einzelnen Bestandteile ein, verarbeitet sie und erstellt daraus die fertige Version.

Solltest du Änderungen am Projekt vornehmen, ändere auch unbedingt das `build.ps1`-Skript ab, damit alles richtig gebaut wird.
Außer natürlich, du willst manuell bauen – das geht natürlich auch.

### `defaults/`

In diesem Ordner liegen die Standarddateien des Projekts.
Sie bilden die Ausgangsbasis für Konfigurationen, Daten und Projektwerte.

Wichtige Dateien sind unter anderem:

* `config.default.yaml`
* `config.yaml`
* `configServerAPI.yml`
* `DelayedTNTconfig.yml`
* `gifts.json`
* `actions.mca`
* `http_actions.txt`
* `pack.mcmeta`

Dieser Ordner ist besonders wichtig, weil er den definierten Startzustand beschreibt.
Wenn das Projekt neu aufgesetzt wird, dienen diese Dateien als Grundlage.

### `docs/`

Zusätzliche Dokumentation, Notizen und technische Informationen liegen hier.

#### `docs/dev-book/`

Hier liegt die technische Dokumentation in Form eines mdBook-Projekts.

* `book/` enthält die generierte Dokumentation
* `src/` enthält die eigentlichen Kapiteltexte

Dieser Bereich ist die schriftliche Begleitung des Projekts.

### `src/`

Hier liegt der eigentliche Quellcode.

* `python/` enthält den Python-Teil der Anwendung

Das ist der Bereich, in dem die Logik entsteht, verändert und erweitert wird.

### `static/`

Dieser Ordner enthält statische Ressourcen für Darstellung und Benutzeroberfläche.

* `css/` für Stylesheets und Layout

Alles, was direkt ausgeliefert werden kann und nicht dynamisch berechnet werden muss, gehört hier hinein.

### `templates/`

In diesem Ordner befinden sich HTML-Vorlagen.

* `index.html`
* `db.html`

Diese Templates bilden die Struktur für Seiten und Oberflächen, die später mit Daten gefüllt werden.

### `tests/`

Der Testbereich dient dazu, das Verhalten des Projekts zu prüfen.
Hier können Prüfungen, Kontrollläufe und automatisierte Tests abgelegt werden.

### `tools/`

Dieser Ordner enthält zusätzliche Werkzeuge und externe Abhängigkeiten.

* `DelayedTNT.jar`
* `MinecraftServerAPI-1.21.x.jar`
* `server.jar`
* `Java/`

Diese Dateien und Ordner sind wichtig für Funktionen, die auf externe Komponenten angewiesen sind.

### `LICENSE`

Die Lizenzdatei definiert die rechtlichen Rahmenbedingungen der Nutzung.

### `README.md`

Die README ist die erste Anlaufstelle für Menschen, die das Projekt verstehen oder starten wollen.
Sie bietet einen Überblick über Inhalt, Zweck und grundlegende Nutzung.

### `upload.ps1`

Ein weiteres PowerShell-Skript, das automatisch von der `build.ps1`-Datei erstellt wird.
Es dient dazu, das Projekt mit einem Klick direkt auf GitHub hochladen zu können.

---

## Release-Struktur

Nach dem Build-Prozess entsteht im Ordner `build/release/` die fertige Projektversion.

```text
.
├── config
│   ├── config.default.yaml
│   └── config.yaml
├── core
│   ├── app.exe
│   ├── assets
│   ├── gifts.json
│   ├── gui.exe
│   ├── lib
│   ├── LikeGoal.exe
│   ├── mcServerAPI.exe
│   ├── Overlaytxt.exe
│   ├── PortChecker.exe
│   ├── runtime
│   ├── static
│   ├── templates
│   ├── timer.exe
│   ├── validation.exe
│   ├── WinCounter.exe
│   └── window.exe
├── data
│   ├── actions.mca
│   └── http_actions.txt
├── LICENSE
├── logs
├── README.md
├── scripts
├── server
│   ├── java
│   └── mc
├── server.exe
├── start.exe
├── update.exe
└── version.txt
```

### `config/`

Hier liegen die laufzeitrelevanten Konfigurationsdateien.

* `config.default.yaml`
* `config.yaml`

Damit ist sowohl ein Standardwert als auch eine angepasste Konfiguration vorhanden.

### `core/`

Das ist das eigentliche Herz der fertigen Anwendung.
Hier liegt die ausführbare Software zusammen mit den Ressourcen, die zur Laufzeit gebraucht werden.

Enthalten sind unter anderem:

* `app.exe`
* `gui.exe`
* `LikeGoal.exe`
* `mcServerAPI.exe`
* `Overlaytxt.exe`
* `PortChecker.exe`
* `timer.exe`
* `validation.exe`
* `WinCounter.exe`
* `window.exe`

Zusätzlich gehören dazu:

* `assets/`
* `gifts.json`
* `lib/`
* `runtime/`
* `static/`
* `templates/`

Dieser Ordner bündelt die eigentliche Funktionswelt des Releases.
Der Ordner `runtime/` ist besonders hilfreich für Daten, die in der Laufzeit benötigt werden und für den Benutzer unwichtig sind.

> [!CAUTION]
> Bei einem Update des Programms wird der gesammte `core/`-Ordner überschrieben.
> Wenn du Daten hast, die nicht überschrieben werden dürfen, nimm den [`data/`-Ordner](#data).

### `data/`

Hier werden Daten abgelegt, die zur Laufzeit oder für bestimmte Funktionen gebraucht werden.
Anders als der `runtime/`-Ordner wird `data/` niemals überschrieben.

* `actions.mca`
* `http_actions.txt`

### `logs/`

Der Log-Ordner speichert Protokolle und Ablaufspuren.
Das ist wichtig, um Fehler, Ereignisse und das Verhalten der Anwendung nachvollziehen zu können.

### `scripts/`

Dieser Ordner enthält zusätzliche Skripte für die fertige Version.
Dort können Hilfsfunktionen oder Wartungsroutinen liegen.

### `server/`

Hier befinden sich serverbezogene Bestandteile.

* `java/`
* `mc/`

### `server.exe`

Eine ausführbare Datei für den Serverstart.

### `start.exe`

Der wichtigste Einstiegspunkt für Benutzer.
Wer das Release startet, beginnt in der Regel hier.

### `update.exe`

Dieses Programm ist für Aktualisierungen gedacht.
Es kann dazu dienen, neue Versionen einzuspielen oder bestehende Installationen zu aktualisieren.

### `version.txt`

Eine kleine, aber wichtige Datei mit der Versionsinformation des Builds.
Zudem enthält sie auch die Version des Updaters.

### `LICENSE` und `README.md`

Auch im Release sind diese Dateien enthalten.
Das sorgt dafür, dass Nutzungsbedingungen und eine kurze Einführung direkt mitgeliefert werden.

---

## Zusammenfassung

Das Projekt ist so aufgebaut, dass alles sauber sortiert bleibt und die einzelnen Teile gut verwaltet werden können.
Nimm dir am besten die Projektstruktur einmal in Ruhe vor und gehe die Ordner nach und nach durch. So bekommst du schnell ein Gefühl dafür, wo später welche Daten hingehören.

Besonders wichtig ist dabei das `build.ps1`-Skript. Es ist dein bester Freund, weil es alles automatisch baut.
Müsstest du das manuell machen, würde das sehr lange dauern. Deshalb lohnt es sich, die Build-Datei gut zu kennen und bei Änderungen am Projekt mit anzupassen.