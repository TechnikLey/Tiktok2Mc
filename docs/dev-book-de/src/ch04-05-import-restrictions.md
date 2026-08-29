# Import-Beschränkungen

Hooks laufen direkt im Bridge-Prozess. Aus Sicherheitsgründen dürfen Hooks nicht beliebige Python-Module importieren. Das System prüft alle Importe beim Laden und blockiert nicht erlaubte Module.

## Erlaubte Imports

Folgende Module dürfen in Hooks verwendet werden (alle Teil der Python-Standardbibliothek, außer `requests`, das mit der App mitgeliefert wird — sie sind also immer verfügbar):

| Modul | Zweck |
|---|---|
| `time` | Zeitverzögerungen und Timestamps |
| `datetime` | Datum, Zeitfenster, tägliche Resets |
| `random` | Zufallswerte |
| `logging` | Logging |
| `json` | JSON-Verarbeitung |
| `re` | Reguläre Ausdrücke (z. B. Textfilter) |
| `math` | Numerische Helfer (Runden, Begrenzen) |
| `collections` | `Counter`, `defaultdict`, `deque` (z. B. Rate-Limit-Fenster) |
| `itertools` | Iterations- und Gruppierungshelfer |
| `functools` | `partial`, Caching-Helfer |
| `urllib` | HTTP-Anfragen (eingeschränkt) |
| `requests` | HTTP-Anfragen (falls installiert) |
| `core.hook_api` | Hook-API-Import für Typannotationen |
| `core.plugin_config` | Plugin-Konfiguration (falls benötigt) |

Submodule erlaubter Top-Level-Module sind ebenfalls zulässig
(z. B. `import urllib.request` oder `from collections import defaultdict`).

## Warum diese Einschränkung?

1. **Sicherheit**: Hooks könnten sonst gefährliche Operationen ausführen.
2. **Stabilität**: Externe Module könnten den Bridge-Prozess destabilisieren.
3. **Portabilität**: In einer gebündelten Anwendung (`.exe`) sind nur bestimmte Module verfügbar.

## Was tun, wenn ein Import fehlt?

Die meisten benötigten Funktionen sind über die Hook-API verfügbar:

| Benötigte Funktion | API-Alternative |
|---|---|
| Minecraft-Befehle senden | `api.rcon_enqueue()` |
| Trigger auslösen | `api.enqueue_trigger()` |
| Overlay-Text anzeigen | `api.send_overlay_text()` |
| Konfiguration lesen | `api.get_hook_config()` |
| Loggen | `api.log()` |

## Beispiel: Korrekter Hook

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def mein_handler(user, trigger, context):
        api.rcon_enqueue([f"say {user} hat {trigger} ausgelöst!"])

    api.register_action("mein-befehl", mein_handler)
```

> [!NOTE]
> Der Import von `HookAPI` ist optional, aber empfohlen für Typannotationen und IDE-Unterstützung. Zur Laufzeit wird er ignoriert.
