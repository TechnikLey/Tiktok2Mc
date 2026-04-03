# Konfiguration: config.yaml im Detail

> [!WARNING]
> Dieser Teil der Dokumentation wird nur wenig gepflegt.
> Es kann daher vorkommen, dass Inhalte veraltet sind oder teilweise automatisch von KI erstellt wurden und deswegen Fehlerhaft sind.

### Zwei-Datei-System

Das Streaming Tool trennt strikt zwischen Template und Benutzerkonfiguration:

- **config.default.yaml** (Template) → wird bei Updates überschrieben
- **config.yaml** (Benutzer) → persistent, niemals überschrieben

**Warum?** Updates können neue Config-Keys einführen, ohne User-Daten zu löschen.

### Das System

```
Update startet
    ↓
Prüft config_version
    ↓
       default > user?
    ↙              ↘
  Ja              Nein
  ↓                 ↓
Migration       Keine Änderung
(Merge Keys)       (User-Values bleiben)
```

### Migration: Schritt-für-Schritt

**1. Version prüfen**
```yaml
# config.default.yaml
config_version: 2

# config.yaml (Benutzer)
config_version: 1  ← älter!
```

**2. System erkennt: Migration nötig**

**3. Merge durchführen:**
- Neue Keys aus default → in user übernehmen
- User-Werte erhalten (nicht überschreiben!)
- Alte Keys aus user → löschen
- Kommentare erhalten (wenn vor Keys)

**4. config.yaml neu geschrieben mit version: 2**

### Code: Config laden mit Fallbacks

```python
import yaml
import sys

CONFIG_FILE = "config/config.yaml"
CONFIG_DEFAULT = "config/config.default.yaml"

def load_config():
    """Lade Config mit Error-Handling."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if cfg is None:
            cfg = {}
        return cfg
    except FileNotFoundError:
        print("config.yaml nicht gefunden! Nutze Defaults.")
        return load_default_config()
    except Exception as e:
        print(f"Config-Fehler: {e}")
        return {}

def load_default_config():
    """Fallback auf config.default.yaml."""
    try:
        with open(CONFIG_DEFAULT) as f:
            return yaml.safe_load(f) or {}
    except:
        return {}

# Werte mit Defaults auslesen
cfg = load_config()
port = cfg.get("WebServer", {}).get("Port", 5000)
enabled = cfg.get("MyPlugin", {}).get("Enable", True)
```

### Config-Wert-Zugriff (Best Practices)

```python
# RICHTIG: Mit .get() + Defaults
log_level = cfg.get("Log", {}).get("Level", "INFO")

# FALSCH: Direkter Zugriff
log_level = cfg["Log"]["Level"]  # KeyError risk!

# Deep Get
db_host = cfg.get("Database", {}).get("Host", "localhost")
db_port = cfg.get("Database", {}).get("Port", 5432)

# Ganze Section mit Default
timer_cfg = cfg.get("Timer", {})
```

### Checkliste für Config-Änderungen

- ☑ Neue Keys → in `config.default.yaml` hinzufügen
- ☑ `config_version` erhöht?
- ☑ Kommentare VOR erstem Key bleiben erhalten
- ☑ Code nutzt `.get()` mit Defaults
- ☑ Test: Migration funktioniert?

→ [Zurück zu Anhang](./attachment.md)

Ob eine Migration der Konfiguration notwendig ist, wird über die `config_version` gesteuert. Diese befindet sich am Anfang der Dateien:

```yaml
config_version: 1
```

* **Datentyp**: Nur Ganzzahlen (Integers).
* **Logik**: Eine Migration wird nur ausgelöst, wenn die `config_version` in der `config.default.yaml` **größer** ist als die in der aktuellen `config.yaml`.

### Ablauf der Migration
Der Migrationsprozess verläuft rekursiv durch alle Ebenen der Konfigurationsdatei. Dabei gelten folgende Regeln:

* **Erhalt von Nutzerwerten**: Werte, die der Nutzer in seiner `config.yaml` angepasst hat, werden nicht überschrieben.
* **Bereinigung**: Keys, die in der neuen `config.default.yaml` nicht mehr existieren, werden aus der `config.yaml` gelöscht.
* **Vollständigkeit**: Neue Keys aus der Vorlage werden in die Nutzer-Config übernommen.

Alles was vor dem ersten Key in `config.default.yaml` steht wird nicht in die config.yaml Kopiert.
Das heißt in diesem Fall alle Kommentare über `config_version` werden nicht Kopiert.
Beachte dies beim Modifizieren.

```yaml
# -------------------------------------------------------------------------
# STREAMING TOOL CONFIGURATION TEMPLATE
# -------------------------------------------------------------------------
# This file is a template.
# Personal settings should be changed in 'config.yaml' only.
# -------------------------------------------------------------------------
config_version: 1
```

---

## Migration deaktivieren

In der `config.yaml` kann die automatische Aktualisierung der Konfiguration deaktiviert werden:

```yaml
auto_update_config: true
```

Wird dieser Wert auf `false` gesetzt, unterbleibt der Abgleich mit der Default-Datei.

> [!WARNING]
> Das Deaktivieren dieser Option erfordert eine **vollständig manuelle Pflege** der Konfiguration. Es gibt keinen CLI-Befehl, um die Migration nachträglich anzustoßen. Eine veraltete Struktur kann zu Fehlern oder Programmabstürzen führen.

## Werte aus der Config auslesen

Um die Konfigurationswerte im Code zu nutzen, wird die `config.yaml` geladen und in ein Dictionary (hier `cfg`) überführt. Der Zugriff erfolgt anschließend über die entsprechenden Keys.

### Laden der Konfiguration

Der folgende Block zeigt das standardmäßige Einlesen der Datei. Hierbei wird sichergestellt, dass das Programm bei einem Lesefehler kontrolliert abbricht:

```python
import yaml
import sys

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    print(f"Fehler beim Laden der Config: {e}")
    input("Drücke Enter zum Beenden...")
    sys.exit(1)
```

### Verwendung im Code

Sobald die Variable `cfg` befüllt ist, kann auf die Werte zugegriffen werden. Da die Migration auch verschachtelte Strukturen unterstützt, erfolgt der Zugriff bei tieferen Ebenen über mehrere Keys:

```python
# Zugriff auf einen Top-Level-Key
auto_update = cfg.get("auto_update_config", True)

# Zugriff auf verschachtelte Werte (Beispiel)
# Angenommen, die Config hat eine Struktur wie:
# database:
#   host: "localhost"
db_host = cfg.get("database", {}).get("host", "127.0.0.1")

# Verwendung der config_version für Logik-Prüfungen
if cfg.get("config_version", 0) < 2:
    # Spezifische Logik für ältere Config-Stände
    pass
```

> [!TIP]
> **Arbeiten mit Dictionaries**
>
> Da die Konfiguration nach dem Laden als Standard-Python-**Dictionary** vorliegt, solltest du dich mit den fortgeschrittenen Methoden zur Datenmanipulation vertraut machen. Das spart Code-Zeilen und verhindert Laufzeitfehler.
>
> Besonders relevant sind:
> * **Sicherer Zugriff (`.get()`):** Vermeide `KeyError`-Abstürze, indem du Standardwerte (Defaults) direkt beim Auslesen definierst.
> * **Verschachtelte Strukturen:** Lerne, wie man effizient auf tiefer liegende Ebenen zugreift (z. B. über `cfg['database']['host']` oder sicherere Ketten).
> * **Type Hinting:** Schau dir an, wie du Typ-Hinweise nutzt, damit deine IDE dich beim Programmieren unterstützt und du genau weißt, ob ein Wert ein `int`, `bool` oder `str` sein muss.
> * **Exceptions:** Verstehe, wie man spezifische Fehler beim Parsen von YAML-Dateien abfängt, um dem Endnutzer hilfreiche Fehlermeldungen statt kryptischer Tracebacks zu zeigen.