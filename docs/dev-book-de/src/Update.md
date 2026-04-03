# Update-Prozess: Wie wird die Software aktualisiert?

> [!WARNING]
> Dieser Teil der Dokumentation wird nur wenig gepflegt.
> Es kann daher vorkommen, dass Inhalte veraltet sind oder teilweise automatisch von KI erstellt wurden und deswegen Fehlerhaft sind.

### Concept: Automatische Updates ohne Datenverlust

Der Updater lädt neue Versionen von GitHub, **ohne** Benutzerdaten zu löschen:

```
Benutzer klickt "Check for Updates"
        ↓
Updater prüft GitHub-Release-API
        ↓
       Neue Version gefunden?
    ↙              ↘
  Ja              Nein
  ↓                ↓
Download       Keine Änderung
+ Extract
  ↓
Migration:
  Neue Keys → config
  User-Werte bleiben
  Alte Keys → löschen
  ↓
Neu starten → Fertig!
```

### Updater-Architektur

```
GitHub Release (Tag = Version)
    │
    ├─ version.txt     (Tool Version + Updater Version)
    ├─ update.exe      (selbst-aktualisierbarer Updater)
    ├─ app.exe         (Hauptprogramm)
    ├─ core/           (Plugins, Laufzeiten)
    ├─ config.default.yaml
    └─ README.md
         │
         ↓ (Download + Extract)
    _update_tmp/ (temporär)
         │
         ↓ (Versionsprüfung)
    Selbst-Update des Updaters?
         │
         ↓ (Nein oder Done)
    Dateien in ./core/ kopieren (mit Whitelist)
         ↓
    config/config.yaml Migration
         ↓
    version.txt aktualisieren
         ↓
    Neustart
```

### Update-Flow: 3 Szenarien

**Szenario 1: Normales Update**
```text
1. Release herunterladen (.zip von GitHub)
2. In _update_tmp/ extrahieren
3. Prüfen: version.txt auslesen
4. Wenn Updater selbst neu: update.exe → update_new.exe kopieren
5. update_new.exe starten mit --resume _update_tmp/
6. (Updater startet sich selbst neu)
7. Dann app.exe aktualisieren
```

**Szenario 2: Updater muss sich selbst aktualisieren**
```text
1. Prüfe: UpdaterVersion in Release > lokale Version?
2. Ja & → update.exe → update_new.exe
3. Starte update_new.exe mit --resume
4. Altes Prozess endet
5. Neuer Prozess läuft weiter
6. (Verhindert: Konflikt beim Update der .exe)
```

**Szenario 3: Config-Migration**
```text
1. Prüfe: config_version in default
2. Ist sie größer als in user?
3. Merge neuer Keys aus default
4. User-Werte bleiben erhalten
5. Alte Keys werden gelöscht
```

### Version-Format

```python
# version.txt
ToolVersion: 1.2.3
UpdaterVersion: 1.0.2

# Regex-Pattern (akzeptiert):
# 1.2.3
# 1.2.3-beta
# 1.2.3-alpha
# 1.2

# Vergleich: "1.2.3" > "1.2.0" = True
# Vergleich: "1.2.3-beta" > "1.2.3" = False (Pre-Release älter)
```

### Was wird überschrieben?

**WIRD überschrieben (Safe):**
- `core/` (EXEs, Runtime)
- `config/config.default.yaml` (ist ja nur Template)
- Plugin-EXEs in `core/`
- Dokumentation (README)

**WIRD NICHT überschrieben (User-Daten!):**
- `config/config.yaml` (deine Einstellungen)
- `data/` (Zähler, Logs, States)
- `plugins/` (User-Plugins)

### Checkliste: Update-Safe

- ☑ Wichtige Benutzerdaten in `./data/`
- ☑ Konfiguration nur in `config/config.yaml`
- ☑ `version.txt` aktualisiert nach Release?
- ☑ GitHub-Release korrekt getaggt?
- ☑ Beta-Releases funktionieren mit Bestätigung?

→ [Zurück zu Anhang](./attachment.md)

Der Updater lädt die aktuelle Version von GitHub, entpackt das Release-Paket und kopiert die freigegebenen Dateien in das Zielverzeichnis.

Dabei gelten diese Grundregeln:

- Benutzerdaten dürfen nicht überschrieben werden.
- Der Updater liest die lokale Version aus `version.txt`.
- Die Konfiguration wird beim Start aus `config/config.yaml` geladen.
- Der Updater arbeitet mit dem Verzeichnis, in dem die EXE liegt.
- Das Release-Paket wird als `.zip` von GitHub geladen.
- Die Update-Logik unterscheidet zwischen **Tool-Version** und **Updater-Version**.

---

## Erwartete Dateien und Pfade

Der Updater verwendet diese lokalen Pfade:

- `version.txt`
- `config/config.default.yaml`
- `config/config.yaml`
- `_update_tmp/` als temporäres Arbeitsverzeichnis

Zusätzlich nutzt er die GitHub-Release-API für dieses Repository:

- `TechnikLey/Streaming_Tool`

Der Zugriff auf GitHub erfolgt über die `latest`-Release-API.  
Für API- und Asset-Requests wird optional ein `GITHUB_TOKEN` aus der Umgebung geladen.

---

## Versionsverwaltung

Die Datei `version.txt` enthält zwei Einträge:

- `ToolVersion`
- `UpdaterVersion`

Der Updater liest beide Werte aus und vergleicht sie mit den Versionen aus dem aktuellen GitHub-Release.

Die Versionsauswertung verwendet ein Regex-Muster, das Versionen in diesem Format erkennt:

- `1.2.3`
- `1.2`
- `1.2.3-beta`
- `1.2.3-alpha`

Wenn die online gefundene Tool-Version nicht neuer ist als die lokale Tool-Version, beendet sich der Updater ohne Änderung.

---

## Ablauf beim Update

### 1. Normaler Start

Wenn kein `--resume` übergeben wurde, passiert Folgendes:

1. Der Updater prüft das aktuelle GitHub-Release.
2. Die Tag-Version wird aus `tag_name` gelesen.
3. Wenn das Release ein `beta`-Tag enthält, erscheint eine Bestätigung.
4. Das `.zip`-Asset aus dem Release wird geladen.
5. Das Archiv wird in `_update_tmp/` entpackt.
6. Falls das Archiv nur einen einzelnen Root-Ordner enthält, wird dieser als Basis verwendet.

### 2. Resume-Modus

Wenn `--resume <pfad>` übergeben wurde, benutzt der Updater direkt die bereits extrahierten Dateien aus diesem Pfad.  
In diesem Fall entfällt der komplette Download-Schritt.

---

## Selbst-Update des Updaters

Der Updater prüft zuerst, ob im Release eine neuere `UpdaterVersion` enthalten ist als lokal installiert.

Wenn das der Fall ist:

1. `update.exe` wird aus dem entpackten Release nach `update_new.exe` im Basisverzeichnis kopiert.
2. Die neue Updater-Version wird in `version.txt` gespeichert.
3. Der aktuelle Prozess wird per `os.execv(...)` durch `update_new.exe` ersetzt.
4. Der neue Prozess läuft mit `--resume <extracted_root>` weiter.

Das bedeutet:

- Der Updater aktualisiert sich **vor** dem eigentlichen Tool-Update.
- Das Tool-Update läuft erst im neuen Prozess weiter.
- Die alte `update.exe` wird nicht im laufenden Prozess überschrieben.

---

## Tool-Update

Nach dem Selbst-Update oder wenn kein neues `update.exe` nötig ist, folgt das eigentliche Tool-Update.

Vor dem Kopieren wird eine Signaldatei geschrieben:

```text
update_signal.tmp
```

Diese Datei wird im aktuellen Working Directory erstellt.
Danach wartet der Updater kurz, damit der Startprozess Zeit zum Beenden hat.

Anschließend kopiert der Updater die Dateien aus dem Release in das Zielverzeichnis.

---

## Was kopiert wird

Der Updater arbeitet mit einer Whitelist.

### Erlaubte Verzeichnisse

Nur diese Top-Level-Verzeichnisse werden verarbeitet:

* `core`
* `scripts`
* `server`
* `config`

### Erlaubte Root-Dateien

Nur diese Dateien auf der obersten Ebene werden übernommen:

* `version.txt`
* `README.md`
* `LICENSE`
* `update.exe`
* `server.exe`
* `start.exe`

### Zusätzliche Regeln

* `update.exe` wird beim normalen Kopieren übersprungen.
* `config.yaml` wird beim normalen Kopieren übersprungen.
* Alle anderen Dateien außerhalb der Whitelist werden ignoriert.

Das Update betrifft damit nur genau die Bereiche, die explizit freigegeben sind.

```Python
WHITELIST_DIRS = {"core", "scripts", "server", "config"}
WHITELIST_FILES = {"version.txt", "README.md", "LICENSE", "update.exe", "server.exe", "start.exe"}
```

---

## Konfigurations-Migration

Wenn `auto_update_config` in der geladenen Konfiguration aktiviert ist, führt der Updater eine Konfigurationsmigration durch.

### Ablauf der Migration

1. `config/config.default.yaml` wird als Vorlage geladen.
2. `config/config.yaml` wird als Benutzerdaten geladen.
3. Falls `config/config.yaml` fehlt, wird sie aus der Default-Datei neu erstellt.
4. Vor der Migration wird ein Backup erstellt:

```text
config/config.yaml.bak
```

5. Die Struktur der Vorlage wird beibehalten.
6. Nur Werte, die in der Vorlage existieren, werden aus der Benutzerversion übernommen.
7. Keys, die nur in der alten Benutzerversion existieren, werden entfernt.
8. `config_version` wird auf die Version der Vorlage gesetzt.

### Wichtige Eigenschaft

Die Migration ist strikt:

* Die Struktur kommt aus der Default-Datei.
* Benutzerwerte werden nur dort übernommen, wo die Vorlage einen passenden Key hat.
* Zusätzliche alte Keys bleiben nicht erhalten.

---

## Zusammenfassung

Der Updater baut auf einer klaren Trennung auf:

* **Tool-Version** und **Updater-Version** werden getrennt verwaltet
* das Release wird als `.zip` von GitHub geladen
* nur freigegebene Verzeichnisse und Dateien werden kopiert
* `config.yaml` bleibt geschützt und wird separat migriert
* der Updater kann sich vor dem eigentlichen Tool-Update selbst ersetzen

Für die Entwicklung heißt das:
Jede Änderung an Dateien, Pfaden oder Build-Struktur muss mit dieser Update-Logik abgeglichen werden.

# Nachwort zum Updater

Ein kleiner Hinweis für Entwickler: Du **musst den Updater nicht vollständig verstehen**, um mit dem Projekt arbeiten zu können.  
Solange du dich an die **aktuelle Projekt- und Release-Struktur** hältst und keine speziellen Update-Mechanismen implementieren willst, läuft alles problemlos.

Der Updater kümmert sich selbstständig darum, Dateien korrekt zu kopieren, Versionen zu prüfen und Konfigurationen zu migrieren. Für normale Entwicklungsarbeit, Tests oder Anpassungen reicht es vollkommen aus, dass du die **Release-Struktur** einhältst und deine Dateien an den vorgesehenen Stellen ablegst.  

> [!TIP]  
> - **Backup ist immer sinnvoll.** Auch wenn der Updater die Konfiguration schützt, ein manuelles Backup eigener Daten schadet nie.
> - Eigene Config-Änderungen: Wenn du änderung an der config machst mache dies in `config.default.yaml`. Weitere Infos dazu hier: [config](./config.md)
> - Der Updater ist ein Werkzeug, das die Aktualisierung und Integrität des Releases automatisiert. Für deine Entwicklungsarbeit ist es ausreichend, die **Release-Struktur** einzuhalten; er kümmert sich selbstständig um Versionierung, Datei-Kopien und Config-Migration.

> [!NOTE]  
> - Neue Dateien oder Features: Wenn du neue Dateien hinzufügen willst, prüfe, ob sie vom Updater berücksichtigt werden sollen. Andernfalls lege sie außerhalb der Whitelist ab. 
> - Config-Migration verstehen ist optional. Für normale Änderungen an der Logik oder den Assets musst du die Migration nicht ändern.
> - Tool-Update vs. Updater-Update: Das Tool wird unabhängig vom Updater aktualisiert. Für Entwicklungszwecke reicht es, nur das Tool zu testen.