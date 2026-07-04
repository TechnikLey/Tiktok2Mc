# Dein erster Hook

In diesem Tutorial erstellst du deinen ersten Hook. Der Hook wird auf den `$superjump`-Befehl reagieren und allen Spielern einen Sprung-Boost geben.

## Hook erstellen

Das Projekt enthält ein Skript, das die Grundstruktur für einen Hook erzeugt:

```bash
python create_hook.py
```

Das Skript fragt nach:

- **Hook-Name**: Nur Kleinbuchstaben und Ziffern, z. B. `sprung`
- **Ort**: Haupt-Hooks-Verzeichnis oder Plugin-gebündelt
- **Action-Name**: Der Name für den `$`-Befehl in der `actions.mca`
- **Update-URL**: Optional

Nach der Erstellung findest du den Hook unter `src/hooks/sprung/`:

```
src/hooks/sprung/
├── hook.json
├── main.py
└── config.yaml
```

## Hook-Code schreiben

Öffne `src/hooks/sprung/main.py`:

```python
from core.hook_api import HookAPI

def register(api: HookAPI):
    def superjump(user, trigger, context):
        api.rcon_enqueue([
            f"effect give @a minecraft:jump_boost 10 5 true",
            f"say {user} hat einen Supersprung ausgelöst!",
        ])

    api.register_action("superjump", superjump)
```

## In actions.mca eintragen

Trage den Hook in der `actions.mca` ein, damit er auf ein TikTok-Event reagiert:

```
follow: $superjump
```

Jedes Mal, wenn jemand auf TikTok folgt, wird der `$superjump`-Hook ausgelöst.

## Hook testen

1. Starte TikTok2Mc: `python run.py`
2. Der Hook wird automatisch geladen.
3. Sende einen Test-Follow-Trigger (siehe [Fehlerbehebung](./troubleshooting.md) im Anhang).

## Nächste Schritte

Im nächsten Kapitel lernst du die [Hook-Struktur](./ch04-02-hook-structure.md) im Detail kennen.
