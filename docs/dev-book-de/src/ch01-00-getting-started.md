# Quickstart

In 5 Minuten erstellst du dein erstes Plugin und siehst, wie es im System lebt.

## Voraussetzungen

- Python 3.12+ installiert
- TikTok2Mc geklont: `git clone https://github.com/TechnikLey/Tiktok2Mc.git`
- Abhängigkeiten installiert: `pip install -r requirements.txt`

> [!TIP]
> Alle Abhängigkeiten automatisch prüfen und fehlende installieren:
>
> ```bash
> python check_deps.py              # Python-Pakete prüfen + installieren
> python check_deps.py --install    # ALLES installieren (Python + System-Tools)
> python check_deps.py --check-only # Nur prüfen, nichts installieren
> python check_deps.py --requirements  # Zusätzlich requirements.txt ausführen
> ```
>
> - `--install` erkennt den Paketmanager automatisch (apt/dnf/pacman/zypper/brew/winget/choco) und installiert fehlende System-Tools
> - Veraltete Tools (z.B. node < 20) werden automatisch auf die richtige Version aktualisiert (via NodeSource auf Linux)
> - Zeigt installierte Versionen an: `[OK] node (vsix/mca-tests)  (22.17)`

Beim Build können die Abhängigkeiten automatisch geprüft **und installiert** werden:

```bash
python build.py --check app       # Prüft + installiert Dependencies vor dem Build
python build.py --check all       # Funktioniert mit jedem Build-Befehl
python build.py --check ci        #
```

> [!TIP]
> `--check` führt `check_deps.py --install` aus — das installiert fehlende Python-Pakete und System-Tools automatisch.
> Auch `requirements.txt` wird standardmäßig ausgeführt.

### Aus dem Cache bauen

Wenn ein voller Build schonmal gelaufen ist, können Executables aus dem Cache wiederverwendet werden:

```bash
python build.py --use-cache app   # Baut NICHT — kopiert aus build/cache/exes/
python build.py --use-cache all   # Funktioniert mit app, all, ci
```

> [!WARNING]
> `--use-cache` prüft Hashes gegen den aktuellen Source-Code. Fehlende oder veraltete Dateien werden gemeldet:
>
> ```
> MISSING:  plugin.bin — cache entry does not exist
> OUTDATED: plugin.bin — source changed since last build
> ```
>
> Fehlende Dateien: Erst einen vollen Build starten (`python build.py app`). Veraltete Dateien: Hashes stimmen nicht — beim nächsten vollen Build wird automatisch neu gebaut.

### Python-Pakete (requirements.txt)

| Paket | Benötigt für |
|-------|-------------|
| PyYAML, Flask, fastapi, uvicorn, pydantic | Core |
| requests, python-multipart, psutil | Core |
| TikTokLive, mcrcon | Streaming |
| pyinstaller, packaging, ruamel.yaml | Build |
| cryptography | Sicherheit |
| PyQt6, PyQt6-WebEngine, qtpy | GUI (pywebview Backend) |
| pytest, pytest-timeout | Tests |

### System-Tools

| Tool | Benötigt für | Installation |
|------|-------------|--------------|
| **git** | Clone, Updates | Bereits installiert (meistens) |
| **java** | Minecraft-Server | `sudo apt install openjdk-21-jre-headless` |
| **Node.js + npm** | `build.py vsix`, `build.py ci` | https://nodejs.org/ (>= 20) |
| **@vscode/vsce** | `build.py vsix` | `npm install -g @vscode/vsce` |
| **binutils** | PyInstaller auf Linux | Siehe unten |
| **NSIS** (optional) | Windows-Installer | https://nsis.sourceforge.io/ |

> [!NOTE]
> **Linux**: Für den Build mit PyInstaller muss `binutils` installiert sein:
>
> ```bash
> sudo apt install binutils   # Debian / Ubuntu
> sudo pacman -S binutils     # Arch
> sudo dnf install binutils   # Fedora
> ```
>
> Für MCA-Tests und VSIX-Build muss zusätzlich `nodejs` installiert sein:
>
> ```bash
> sudo apt install nodejs npm   # Debian / Ubuntu
> sudo pacman -S nodejs npm     # Arch
> sudo dnf install nodejs npm   # Fedora
> ```

## 1. Plugin erstellen

```bash
python create_plugin.py
```

Das Skript fragt nach einem Namen (a-z, 0-9, Bindestriche). Beispiel: `mein-plugin`

Nach der Erstellung liegt das Plugin unter `src/plugins/mein-plugin/`:

```
src/plugins/mein-plugin/
├── plugin.json         # Manifest
├── main.py             # Einstiegspunkt
├── config.yaml         # Konfiguration
├── version.txt         # Version
└── README.md           # Dokumentation
```

## 2. Plugin-Code schreiben

Ersetze den Inhalt von `src/plugins/mein-plugin/main.py`:

```python
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)

class MeinPlugin(BasePlugin):
    PLUGIN_NAME = "mein-plugin"

    def __init__(self):
        super().__init__()
        self.register_handler("tiktok_event", self._on_tiktok_event)

    def _on_tiktok_event(self, args):
        event_type = args.get("event_type", "")
        user = args.get("user", "")
        if event_type == "tiktok.follow":
            log.info(f"{user} folgt jetzt!")

    def get_overlay_html(self) -> str:
        return "<html><body>Mein Plugin läuft!</body></html>"

if __name__ == "__main__":
    MeinPlugin().run()
```

**Wichtig**: Der Subprozess startet `main.py` als Python-Datei. Der `if __name__`-Block sorgt dafür, dass `run()` aufgerufen wird — ohne ihn beendet sich der Prozess sofort.

## 3. Event-Abonnement eintragen

Füge in `src/plugins/mein-plugin/plugin.json` das Feld `event_subscriptions` hinzu:

```json
{
  "name": "mein-plugin",
  "event_subscriptions": ["tiktok.follow", "tiktok.gift"]
}
```

Ohne diese Deklaration erhält dein Plugin keine TikTok-Events.

## 4. System starten

```bash
python run.py
```

Startet den API-Server unter `http://127.0.0.1:29185`. Der Plugin-Watcher registriert automatisch alle Plugins aus `src/plugins/`.

## 5. Plugin aktivieren

```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/mein-plugin/enable
```

Der Supervisor startet daraufhin den Subprozess: `python src/plugins/mein-plugin/main.py`

Bestätigung in der Konsole: Das Plugin loggt, dass es gestartet ist.

## 6. Test-Event senden

```bash
python tests/send_trigger.py --event tiktok.follow --user TestUser
```

In der Konsole sollte erscheinen: `TestUser folgt jetzt!`

## 7. Plugin deaktivieren

```bash
curl -X PUT http://127.0.0.1:29185/api/v1/plugins/mein-plugin/disable
```

Das System beendet den Subprozess.

## Fehler beheben

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Plugin nicht erkannt | `plugin.json` fehlt oder ungültig | JSON-Syntax prüfen |
| Plugin startet nicht | `entry_point` falsch | Pfad in `plugin.json` prüfen |
| Events kommen nicht an | `event_subscriptions` fehlt | Feld in `plugin.json` ergänzen |
| `PLUGIN_NAME` falsch | Stimmt nicht mit `name` überein | Beide auf gleichen Wert setzen |

## Nächste Schritte

Du hast dein erstes Plugin in Betrieb. Lies [Grundkonzepte](./ch02-00-core-concepts.md) für die Architektur oder steige direkt in die [Plugin-Entwicklung](./ch03-00-plugins.md) ein.
