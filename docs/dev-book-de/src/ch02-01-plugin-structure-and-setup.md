# Plugin-Struktur & Setup

### Aufbau eines Plugins

Jedes Plugin ist ein **isoliertes Python-Programm** mit Standardstruktur. Benefits:
- **Boilerplate-Code** schon vorbereitet
- **Core-Module** für häufige Tasks (Config, Logging, Pfade)
- **Automatische Registrierung** in PLUGIN_REGISTRY

### Ordnerstruktur

**Automatisch-erstellt per PowerShell-Skript (create_plugin.ps1):**
```
src/plugins/
└── my_plugin/
    ├── main.py           ← Plugin-Kern
    ├── README.md        
    └── version.txt       
```

### Plugin erstellen: 2 Schritte

Wenn du das PowerShell-Skript `create_plugin.ps1` ausführst, fragt es dich nach dem Namen deines Plugins. Danach erstellt es automatisch die komplette Ordnerstruktur für dich. Diese sieht dann so aus:

```text
.
├── dein_plugin_name
│   ├── main.py
│   ├── README.md
│   └── version.txt
```

Der neue Ordner wird unter `src/plugins/` erstellt und mit dem Namen benannt, den du während der Erstellung angegeben hast.

## Die einzelnen Dateien

### `main.py` – Das Herz deines Plugins

Das ist die wichtigste Datei! Hier schreibst du die eigentliche Logik deines Plugins. Wenn du mit `create_plugin.ps1` ein Plugin erstellst, bekommst du automatisch einen Basis-Code eingefügt. Der sieht ungefähr so aus:

```python
from core import load_config, parse_args, get_root_dir, get_base_dir, get_base_file, register_plugin, AppConfig
import sys

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"
DATA_DIR = ROOT_DIR / "data"
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=True,
        level=4,
        ics=False
    ))
    sys.exit(0)
```

> [!TIP]
> Wenn du die `config.yaml` Datei direkt im Plugin Ordner nutzen willst dann ersetze:
> ```Python
> CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"
> ```
>
> Durch diesen Code:
> 
> ```Python
> CONFIG_FILE = BASE_DIR / "config.yaml"
> CONFIG_FILE.touch(exist_ok=True) # Legt die Datei an wenn du es nicht schon selbst gemacht hast.
> ```

#### Was passiert da genau?

**Importe**  
Du importierst Funktionen und Klassen aus dem `core`-Modul. Das erspart dir viel Schreibarbeit:
- `load_config`: Lädt die Konfigurationsdatei
- `parse_args`: Liest Command-Line-Argumente
- `get_root_dir`, `get_base_dir`, `get_base_file`: Ermitteln wichtige Verzeichnisse und Dateipfade
- `register_plugin`: Registriert dein Plugin
- `AppConfig`: Eine Klasse, die die Plugin-Konfiguration speichert

**Wichtige Pfade einrichten**  
```python
BASE_DIR = get_base_dir()           # Der Basis-Ordner der Anwendung
ROOT_DIR = get_root_dir()           # Der Wurzelpfad, zwei Ebenen über BASE_DIR
CONFIG_FILE = ROOT_DIR / "config" / "config.yaml"  # Pfad zur Konfiguration
DATA_DIR = ROOT_DIR / "data"        # Ordner für User-Daten
MAIN_FILE = get_base_file()         # Der Pfad zur main.exe (main.py im dev Ordner)
```

Diese Variablen brauchst du später in deinem Code – zum Beispiel um Dateien zu speichern oder die Config zu laden.

**Startargumente auslesen**  
```python
args = parse_args()
gui_hidden = args.gui_hidden        # War die --gui-hidden Flag gesetzt?
register_only = args.register_only  # War die --register-only Flag gesetzt?
```

Das Programm kann dein Plugin mit bestimmten Flags starten:
- `--gui-hidden`: Die GUI wird versteckt gestartet
- `--register-only`: Das Plugin wird nur registriert, aber nicht ausgeführt

**Plugin registrieren (wenn `--register-only` gesetzt ist)**  
```python
if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=True,
        level=4,
        ics=False
    ))
    sys.exit(0)
```

Wenn das Plugin nur registriert werden soll, passiert folgendes:

- **`name`**: Der Name deines Plugins (z.B. "test")
- **`path`**: Der Pfad zur ausführbaren Datei
- **`enable`**: `True` = Plugin ist aktiv, `False` = Plugin ist deaktiviert  
  *Tipp: Statt `True/False` zu hardcodieren, kannst du auch Config-Werte nutzen:*  
  ```python
  enable=cfg.get("custom_name", {}).get("enable", True)
  ```  
  So können Nutzer dein Plugin in der `config.yaml` ein- und ausschalten!

- **`level`**: Bestimmt ab wann das Terminal sichtbar ist (abhängig vom `log_level` in der `config.yaml`):
  - **Level 0**: Deaktiviert alles (sollte nicht verwendet werden)
  - **Level 1**: Terminal sichtbar ab `log_level: 1`
  - **Level 2**: Hauptprogramme (`log_level: 2`)
  - **Level 3**: Hintergrund-Dienste (z.B. Checks, Listener)
  - **Level 4**: Debug/Entwicklung
  - **Level 5**: Überschreibt andere Einstellungen (sollte nicht verwendet werden)

- **`ics`**: **I**nterface **C**ontrol **S**ystem – gibt an, ob die GUI unterstützt wird
  - `True` = GUI wird unterstützt
  - `False` = GUI wird NICHT unterstützt (Direct Control System / DCS)

Nach der Registrierung endet das Programm mit `sys.exit(0)`.

---

> [!WARNING]
> **Plugin-Registrierung: Reihenfolge und Laufzeitbeschränkung**
>
> Der Aufruf von `register_plugin(...)` muss so früh wie möglich im Programm erfolgen.
> Vor der Registrierung darf **kein ausführbarer Code** stehen – ausgenommen sind:
>
> * Imports
> * Konfigurations- und Pfaddefinitionen
> * Argument-Parsing (z. B. `parse_args()`)
>
> **Nicht erlaubt vor der Registrierung:**
>
> * Logik mit Seiteneffekten
> * Netzwerkzugriffe oder Dateizugriffe
> * Initialisierungen mit externer Abhängigkeit
> * `print`-Ausgaben oder sonstige I/O-Operationen
>
> Hintergrund: Die Registrierungsroutine läuft in einer strikt begrenzten Umgebung und kann andernfalls fehlschlagen.
>
> ---
>
> **Unmittelbares Beenden erforderlich**
>
> Nach erfolgreichem Aufruf von `register_plugin(...)` muss das Programm sofort mit
> `sys.exit(0)` beendet werden.
>
> ```python
> if register_only:
>     register_plugin(AppConfig(
>         name="test",
>         path=MAIN_FILE,
>         enable=True,
>         level=4,
>         ics=False
>     ))
>     sys.exit(0)
> ```
>
> Ohne dieses sofortige Beenden besteht die Gefahr, dass nachgelagerter Code ausgeführt wird, was die Registrierung beeinträchtigen oder ungültig machen kann.
>
> ---
>
> **Zeitlimit beachten**
>
> Der Registrierungsprozess hat ein hartes Zeitlimit von **5 Sekunden**.
> Wird dieses überschritten, wird das Programm extern beendet.

---

**Konfiguration laden**  
```python
cfg = load_config(CONFIG_FILE)
```

Hier wird die `config.yaml` geladen. Sie enthält alle Einstellungen für dein Plugin. `cfg` ist jetzt ein Dictionary, auf das du zugreifen kannst:
```python
# Beispiel: Config-Wert auslesen mit Standard-Wert
enable=cfg.get("custom_name", {}).get("enable", True)
```

So muss das dann in der config.yaml aussehen:
```yaml
custom_name:
  enable: True
```

---

### `README.md` – Dokumentiere dein Plugin

Diese Datei ist deine Chance, anderen Entwicklern zu zeigen, was dein Plugin macht. Schreib hier auf:

- **Was macht das Plugin?** – Eine kurze Beschreibung
- **Anforderungen** – Welche Voraussetzungen muss der Nutzer erfüllen?
- **Konfiguration** – Welche Optionen gibt es in der `config.yaml`?
- **Verwendung** – Wie wird das Plugin verwendet?

Ein gutes README macht es dir selbst und anderen später leichter!

### `version.txt` – Die Versionsnummer

In dieser Datei speicherst du die aktuelle Version deines Plugins. Wenn du ein neues Plugin erstellst, steht dort standardmäßig:

```
v1.0.0
```

**Wichtig:** Halte dich an dieses Format! Es befolgt das [Semantic Versioning](https://semver.org/)-Standard:
- **v1.0.0** = Major.Minor.Patch
- **Major**: Breaking Changes (große Änderungen)
- **Minor**: Neue Features (rückwärts-kompatibel)
- **Patch**: Bugfixes

Beispiele:
- v1.0.0 → v1.0.1 (kleiner Bugfix)
- v1.0.1 → v1.1.0 (neue Funktion hinzugefügt)
- v1.1.0 → v2.0.0 (großer Umbau, nicht mehr kompatibel)

---

## Plugins in anderen Programmiersprachen

Kann ich mein Plugin auch in Java, C++, JavaScript etc. schreiben? **Ja, aber...** 

Wenn du Python verlässt, musst du viel selbst machen, das Python-Module dir abnehmen. Nur um dir eine Idee zu geben:
- Config laden
- Startargumente auslesen
- Pfade ermitteln
- Plugin registrieren
- Fehlerbehandlung

Der Grundaufbau kann je nach Sprache schnell **mehrere hundert Zeilen Code** brauchen – deutlich mehr als die ~20 Zeilen Python oben.

**Faustregel:** Python ist der beste Startpunkt. Wenn du später mehr Performance brauchst, kannst du Performance-kritische Teile später immer noch optimieren oder in eine andere Sprache erstellen.

---

**Nächstes Kapitel:** [Webhook-Events und Minecraft-Integration](./ch02-02-webhook-events-and-minecraft-integration.md)