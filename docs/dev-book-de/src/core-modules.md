# Core-Module und Infrastruktur

> [!NOTE]
> Diese Übersicht richtet sich an **Fortgeschrittene Entwickler**, die verstehen wollen, wie die Infrastruktur des Systems aufgebaut ist. Erweiterte Grundkenntnisse in Python werden vorausgesetzt.

---

## Überblick

Die **Core-Module** liegen in `src/core/` und bilden die **Infrastruktur** des Systems. Sie sind nicht direkt sichtbar im Stream – aber jedes Plugin nutzt sie im Hintergrund.

| Modul | Aufgabe |
|-------|---------|
| **paths.py** | Verzeichnis-Verwaltung & Pfade |
| **utils.py** | Konfiguration laden, Hilfsfunktionen |
| **models.py** | Datenstrukturen (AppConfig) |
| **validator.py** | Syntax-Validierung (actions.mca) |
| **cli.py** | Command-Line Arguments |

---

## paths.py – Pfad-Management

### Was ist es?

`paths.py` kümmert sich um **wo alles ist** im Dateisystem.

### Kurze Beispiele

```python
from core.paths import get_root_dir, get_config_file

# Wo ist das Projekt?
root = get_root_dir()  
# → "C:\Users\User\Streaming_Tool" oder ".\build\release"

# Wo ist die config.yaml?
config = get_config_file()  
# → "C:\Users\User\Streaming_Tool\config\config.yaml"
```

### Wichtige Funktionen

- `get_root_dir()` – Projekt-Wurzel
- `get_config_file()` – Pfad zu config.yaml
- `get_base_dir()` – Basis-Verzeichnis (unterscheidet frozen vs. development)

**Wofür braucht man das?**
Damit Plugins nicht hart-codieren müssen `C:\...\config.yaml`, sondern einfach `get_config_file()` aufrufen.

---

## utils.py – Konfiguration & Hilfsfunktionen

### Was ist es?

`utils.py` lädt und parst die **config.yaml** Datei. Das ist die zentrale Konfigurationsdatei des Systems.

### Kurze Beispiele

```python
from core.utils import load_config
from core.paths import get_config_file

# Config laden
config = load_config(get_config_file())

# Zugriff auf Werte
plugins = config["plugins"]
log_level = config["settings"]["log_level"]
```

### Was macht load_config()?

1. Prüft, ob die Datei existiert
2. Parst YAML
3. Gibt Dictionary zurück
4. **Bei Fehler**: Beendet das Programm mit aussagekräftiger Fehlermeldung

**Wofür braucht man das?**
Jedes Plugin muss die config.yaml lesen. `load_config()` macht das zuverlässig – mit Error-Handling.

---

## models.py – Datenstrukturen

### Was ist es?

`models.py` definiert die **AppConfig** – die Datenstruktur, die ein Plugin beschreibt (wie es in der Registry registriert wird).

### Die AppConfig Struktur

```python
@dataclass
class AppConfig:
    name: str          # Name des Plugins
    path: Path         # Wo liegt das Plugin?
    enable: bool       # Ist es aktiviert?
    level: int         # Priorität/Log-Level
    ics: bool          # Hat es ein GUI-Fenster?
```

### Kurze Beispiele

```python
from core.models import AppConfig
from pathlib import Path

# Ein Plugin definieren
timer = AppConfig(
    name="Timer",
    path=Path("src/plugins/timer"),
    enable=True,
    level=1,
    ics=True  # Hat GUI
)

# Als Dictionary für config.yaml
plugin_dict = timer.to_dict()
# → {"name": "Timer", "path": "src/plugins/timer", ...}

# Aus Dictionary zurück
timer2 = AppConfig.from_dict(plugin_dict)
```

**Wofür braucht man das?**
Die PLUGIN_REGISTRY verwaltet alle Plugins als AppConfig-Objekte. Das macht die Verwaltung strukturiert und validiert.

---

## validator.py – Syntax-Validierung

### Was ist es?

`validator.py` prüft die **actions.mca** Datei auf Fehler. Es findet:
- Fehlende Doppelpunkte
- Ungültige Syntax
- Doppelte Trigger
- Formatierungsfehler

### Kurze Beispiele

```python
from core.validator import validate_text

text = """
5655:!tnt 2 0.1 2 Notch
follow:/give @a minecraft:golden_apple 7
invalid_line_without_colon
"""

diags = validate_text(text)  # Liste von Fehlern

for diag in diags:
    print(f"[{diag.severity}] Zeile {diag.line}: {diag.message}")
    # → [ERROR] Zeile 3: Fehlender Doppelpunkt
```

### Was wird validiert?

✓ Jede Zeile muss `TRIGGER:...` Format haben  
✓ Keine Leerzeichen direkt nach `:`  
✓ Keine Doppel-Trigger  
✓ Korrektes Command-Format  

**Wofür braucht man das?**
Damit Nutzer schnell Fehler in ihrer actions.mca sehen – mit exakten Zeilennummern und Fehlercodes.

---

## cli.py – Command-Line Arguments

### Was ist es?

`cli.py` parst Command-line Argumente beim Start:

```
python main.py --gui-hidden --register-only
```

### Verfügbare Argumente

| Argument | Effekt |
|----------|--------|
| `--gui-hidden` | Starte ohne GUI-Fenster (Headless) |
| `--register-only` | Registriere nur Plugins, beende dann |

### Kurze Beispiele

```python
from core.cli import parse_args

args = parse_args()

if args.gui_hidden:
    print("Starte im Headless-Modus")

if args.register_only:
    print("Nur Registry aktualisieren, dann exit")
    # ... plugin registry update ...
    sys.exit(0)
```

**Wofür braucht man das?**
Ermöglicht verschiedene Start-Modi (für Testing, Automation, Wartung).

---

## Zusammenfassung

Die **Core-Module** sind die **Infrastruktur-Schicht**:

| Modul | Nutzen |
|-------|--------|
| **paths.py** | Richtige Pfade finden (dev vs. release) |
| **utils.py** | Config zuverlässig laden |
| **models.py** | Plugin-Metadaten verwalten |
| **validator.py** | Fehler finden & berichten |
| **cli.py** | Verschiedene Start-Modi |

**Praktisch für Entwickler:**
- Plugin-Entwickler: Nutzen hauptsächlich `paths.py` und `utils.py`
- System-Entwickler (Core): Nutzen alle Module
- Das System selbst: Nutzt alle zusammen für Registrierung & Verwaltung