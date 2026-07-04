# Overlays & Zustand

Plugins können Overlay-Inhalte für OBS oder das pywebview-Fenster bereitstellen. Es gibt zwei Ebenen: statisches HTML und dynamische Zustands-Updates per SSE.

## Wie Overlays funktionieren

```
Plugin-Prozess           API-Server                    Browser / OBS
     │                       │                              │
     │── POST /overlay-html ─→│                              │
     │                       │── GET /plugins/{name}/overlay →│
     │                       │    (statisches HTML)          │
     │                       │                              │
     │── POST /state ───────→│                              │
     │                       │── SSE: data: {...} ──────────→│
     │                       │    (EventSource-Stream)       │
```

## Statisches Overlay-HTML

Jedes Plugin **muss** `get_overlay_html()` überschreiben. Das HTML wird einmal beim Start geladen und über den API-Server bereitgestellt.

```python
def get_overlay_html(self) -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; background: transparent; }
        .count { font-size: 48px; color: #ff4444; }
    </style>
</head>
<body>
    <div class="count" id="counter">0</div>
    <script>
        const es = new EventSource("/api/v1/plugins/mein-plugin/stream");
        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            document.getElementById("counter").innerText = data.count;
        };
        es.onerror = () => {
            es.close();
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        };
    </script>
</body>
</html>"""
```

**Overlay-URL**: `http://127.0.0.1:29185/api/v1/plugins/<name>/overlay`

Diese URL verwendest du als **Browser-Quelle** in OBS.

## Dynamischer Zustand per SSE

### Zustand setzen und übertragen

```python
self._state["count"] = self._zaehler
self.push_state()
```

`push_state()` sendet `POST /api/v1/plugins/{name}/state` an den API-Server. Der Server speichert den Zustand im `PluginStateStore` und leitet ihn per SSE an alle verbundenen Clients weiter.

### SSE-Code im HTML

```javascript
const es = new EventSource("/api/v1/plugins/mein-plugin/stream");
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById("counter").innerText = data.count;
};
es.onerror = () => {
    es.close();
    setTimeout(() => {
        new EventSource("/api/v1/plugins/mein-plugin/stream");
    }, 2000);
};
```

### Wann push_state() aufrufen?

- Nach jeder Zustandsänderung, die im Overlay sichtbar sein soll
- In `on_tick()` bei periodischen Änderungen (Timer-Countdown)
- Nicht bei jeder Einzeländerung — sammle und rufe einmal auf

## `get_overlay_html()` zur Laufzeit ersetzen

Wenn sich das HTML selbst ändern soll (z. B. Theme-Wechsel):

```python
self.register_overlay("<html>Neues HTML</html>")
```

Für häufige inhaltliche Änderungen ist `push_state()` der richtige Weg.

## Zustand über Neustarts hinweg speichern

`push_state()` ist flüchtig — der Zustand lebt nur im API-Server. Für persistente Daten:

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        count_file = self._data_dir / f"{self.PLUGIN_NAME}_state.json"
        self._daten = self._laden(count_file)

    def _laden(self, pfad):
        if pfad.exists():
            return json.loads(pfad.read_text(encoding="utf-8"))
        return {}

    def _speichern(self, pfad):
        pfad.write_text(json.dumps(self._daten), encoding="utf-8")
```

> [!WARNING]
> `self._data_dir` ist **für alle Plugins gleich** (`<projekt>/data/`). Verwende immer plugin-spezifische Dateinamen.

## Theme-Unterstützung

```python
def get_overlay_html(self) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <style>
{self.theme_style}
        body {{ background: var(--background); color: var(--text); }}
    </style>
</head>
<body>...</body>
</html>"""
```

Verfügbare CSS-Variablen: `--background`, `--text`, `--accent`, `--muted`, `--danger`, `--separator`

## GUI-Fenster mit pywebview

Die Basisklasse öffnet ein pywebview-Fenster auf die Overlay-URL. Mit `--gui-hidden` unterdrückst du das Fenster:

```bash
python src/plugins/mein-plugin/main.py --gui-hidden
```

Fensterabmessungen speichern:

```python
self.save_window_state(breite, hoehe)
```

## Häufige Fehler

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Overlay bleibt schwarz | `get_overlay_html()` fehlt | Implementieren |
| Keine Echtzeit-Updates | `push_state()` fehlt | Nach jeder Änderung aufrufen |
| SSE bricht ab | Kein `onerror`-Handler | `setTimeout`-Wiederverbindung einbauen |
| Theme wirkt nicht | `{self.theme_style}` nicht eingebunden | In `<style>` einfügen |
