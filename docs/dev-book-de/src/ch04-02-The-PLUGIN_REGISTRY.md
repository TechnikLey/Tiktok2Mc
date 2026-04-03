## Die PLUGIN_REGISTRY: Zentrale Plugin-Registrierung

### Concept: Was ist die Registry?

Die App kann mehrere Prozesse steuern (Kern-App, GUI, Server, Plugins). Sie müssen **zentral registriert** und **konfigurierbar** sein. Dafür gibt es zwei Registries:

1. **BUILDIN_REGISTRY** — fest in `start.py` definierte Core-Module
2. **PLUGIN_REGISTRY** — dynamisch aus `PLUGIN_REGISTRY.json` geladene Plugins

### Die AppConfig-Klasse

Jeder Registry-Eintrag ist eine `AppConfig`-Instanz (definiert in `core/models.py`):

```python
@dataclass(slots=True)
class AppConfig:
    name: str      # Eindeutiger Name (z.B. "Timer")
    path: Path     # Absoluter Pfad zur EXE
    enable: bool   # Soll das Plugin starten?
    level: int     # Log-Level für Sichtbarkeit
    ics: bool      # Hat GUI? (Interface Control System)
```

### Die fünf Parameter

| Parameter | Typ | Beispiel | Funktion |
|-----------|-----|---------|----------|
| `name` | str | `"Timer"` | Eindeutige Identität (Logs, Status) |
| `path` | Path | `Path("plugins/timer/main.exe")` | Absoluter Pfad zur EXE |
| `enable` | bool | `True` | Startet Plugin beim Boot? |
| `level` | int | `4` | Log-Level für Terminal-Sichtbarkeit |
| `ics` | bool | `True` | Unterstützt GUI-Fenster (pywebview)? |

> [!IMPORTANT]
> Alle fünf Parameter sind **Pflicht**. Fehlt einer oder ist ein unbekannter Key vorhanden, wird ein `ValueError` geworfen.

### Log-Level Bedeutung

Der `level`-Parameter steuert die **Terminal-Sichtbarkeit** abhängig vom `log_level` in der `config.yaml`:

| Level | Name | Beschreibung |
|-------|------|-------------|
| **0** | Off | Versteckt alles, inklusive GUI-Fenster |
| **1** | Silent | Versteckt Konsolen-Fenster, GUI bleibt aktiv |
| **2** | Standard | Zeigt nur Hauptprogramme |
| **3** | Advanced | Zeigt auch Hintergrund-Dienste |
| **4** | Debug | Zeigt alle aktivierten Prozesse |
| **5** | Override | Zeigt **jeden** Prozess, auch wenn `enable=False` |

**Logik:** Ein Plugin ist sichtbar, wenn `log_level >= plugin.level`.

**Level 0** und **Level 5** sind Sonderfälle:
- Level 0 versteckt alles und setzt `gui_hidden=True`
- Level 5 überschreibt alle `enable`-Werte und zeigt alles

---

### BUILDIN_REGISTRY (Core-Module)

Die Core-Module sind direkt in `start.py` definiert:

```python
BUILDIN_REGISTRY: list[AppConfig] = [
    AppConfig(name="App",              path=APP_EXE_PATH,    enable=True,        level=2, ics=False),
    AppConfig(name="Minecraft Server", path=SERVER_EXE_PATH, enable=True,        level=2, ics=False),
    AppConfig(name="GUI",              path=GUI_EXE_PATH,    enable=GUI_ENABLED, level=2, ics=False),
]
```

Diese können nicht von außen verändert werden — sie sind fester Bestandteil des Systems.

---

### PLUGIN_REGISTRY (Dynamische Plugins)

Plugins werden in `PLUGIN_REGISTRY.json` gespeichert. Diese Datei wird automatisch beim Start geladen:

```json
[
  {
    "name": "Timer",
    "path": "C:\\...\\plugins\\timer\\main.exe",
    "enable": true,
    "level": 4,
    "ics": true
  },
  {
    "name": "Death Counter",
    "path": "C:\\...\\plugins\\deathcounter\\main.exe",
    "enable": true,
    "level": 4,
    "ics": true
  }
]
```

---

### Wie Plugins sich registrieren

Plugins registrieren sich über das `--register-only` Flag. Der Ablauf:

```
1. registry.exe findet alle main.exe in plugins/
   ↓
2. Für jede main.exe: Startet mit --register-only
   ↓
3. Plugin gibt AppConfig als JSON aus (REGISTER_PLUGIN: {...})
   ↓
4. registry.exe schreibt in PLUGIN_REGISTRY.json
   ↓
5. start.py liest PLUGIN_REGISTRY.json und startet Plugins
```

**Im Plugin (main.py):**
```python
from core import parse_args, register_plugin, AppConfig, get_base_file
from core.utils import load_config

args = parse_args()

if args.register_only:
    register_plugin(AppConfig(
        name="Timer",
        path=get_base_file(),
        enable=cfg.get("Timer", {}).get("Enable", True),
        level=4,
        ics=True
    ))
    sys.exit(0)

# ... Rest des Plugin-Codes
```

> [!IMPORTANT]
> **Zeitlimit:** Der Registrierungsprozess hat ein hartes Limit von **5 Sekunden**.
> Vor `register_plugin()` darf kein langsamer Code stehen (keine Netzwerkzugriffe, keine I/O-Operationen).
> Nach `register_plugin()` muss sofort `sys.exit(0)` folgen.

---

### Wie start.py die Registry verarbeitet

`start.py` durchläuft **beide** Registries und startet die Plugins:

```python
for registry in (BUILDIN_REGISTRY, PLUGIN_REGISTRY):
    for app in registry:
        if LOG_LEVEL == 0:
            # Level 0: Alles verstecken
            start_exe(path=app.path, name=app.name, hidden=True, gui_hidden=True)
        elif LOG_LEVEL == 5:
            # Level 5: Alles zeigen
            start_exe(path=app.path, name=app.name, hidden=False)
        else:
            if app.ics and CONTROL_METHOD == "DCS" and app.enable:
                # GUI-Plugin im DCS-Modus: GUI verstecken, nur Server
                start_exe(path=app.path, name=app.name,
                          hidden=get_visibility(app.level), gui_hidden=True)
            elif app.enable:
                # Normal starten
                start_exe(path=app.path, name=app.name,
                          hidden=get_visibility(app.level))
```

---

### Scan-Cache (Performance)

Um den Registrierungsprozess zu beschleunigen, nutzt `registry.py` einen **Scan-Cache** (`plugin_registry_scan_cache.json`). Wenn sich eine Plugin-EXE nicht verändert hat (gleiche Dateigröße und Änderungszeit), wird das Ergebnis aus dem Cache verwendet statt das Plugin erneut zu starten.

---

### Zusammenfassung

| Komponente | Datei | Inhalt |
|-----------|-------|--------|
| **AppConfig** | `core/models.py` | Dataclass mit 5 Pflichtfeldern |
| **BUILDIN_REGISTRY** | `start.py` | Fest definierte Core-Module |
| **PLUGIN_REGISTRY** | `PLUGIN_REGISTRY.json` | Dynamisch registrierte Plugins |
| **Registrierung** | `registry.py` | Scannt Plugins mit `--register-only` |
| **Scan-Cache** | `plugin_registry_scan_cache.json` | Beschleunigt wiederholte Scans |

### → Weiter zu [GUI-Architektur](./ch04-03-GUI-Architecture.md)