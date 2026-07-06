# Overlay-System

Das Overlay-System erlaubt es, Text und Grafiken im Live-Stream anzuzeigen. Es gibt zwei Wege, Overlays zu nutzen: über die Hook-API und über das Plugin-System.

## Overlay in Hooks

Hooks können mit `api.send_overlay_text()` Text anzeigen:

```python
api.send_overlay_text(
    title="Neuer Follower!",
    subtitle=f"{user} folgt jetzt!",
    duration=5,
    overlay_name="default"
)
```

Parameter:

- `title` (str): Haupttext
- `subtitle` (str, optional): Kleinerer Text darunter
- `duration` (int, optional): Anzeigedauer in Sekunden (Standard: 3)
- `overlay_name` (str, optional): Name des Overlays (Standard: "default")

Die Funktion gibt `True` bei Erfolg zurück, sonst `False`.

## Overlay in Plugins

Plugins können vollständige HTML-Overlays bereitstellen. Eine detaillierte Anleitung findest du in [Overlays & Zustand](./ch03-07-overlays-and-state.md).

```python
def get_overlay_html(self) -> str:
    return "<html><body>...</body></html>"
```

Das HTML-Overlay wird über eine URL als Browser-Quelle in OBS eingebunden:

```
http://127.0.0.1:29185/api/v1/plugins/<plugin-name>/overlay
```

## Echtzeit-Updates per SSE

Plugins können ihren Zustand per `push_state()` aktualisieren. Details zu SSE, EventSource und Zustandsverwaltung findest du in [Overlays & Zustand](./ch03-07-overlays-and-state.md).

## Overlay in der actions.mca

Die `actions.mca` unterstützt Overlay-Text direkt:

```
follow: >>Willkommen!|{user} ist da!|4
```

Das Format ist: `>>Titel|Untertitel|Dauer`

- Teile werden durch `|` getrennt
- `{user}` wird durch den TikTok-Benutzernamen ersetzt
- `{comment}` wird durch den Kommentartext ersetzt (bei Comment-Events)
