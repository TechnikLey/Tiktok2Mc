# Overlays & Zustand

Plugins können Overlay-Inhalte für OBS (Open Broadcaster Software) oder das pywebview-Fenster bereitstellen. Es gibt zwei Ebenen: das statische HTML, das einmal beim Start geladen wird, und den dynamischen Zustand, der per Server-Sent Events (SSE) in Echtzeit aktualisiert wird.

## Wie Overlays funktionieren

Das Overlay-System besteht aus drei Komponenten:

1. **Plugin** erzeugt HTML und sendet Zustands-Updates
2. **API-Server** liefert das HTML aus und verteilt Updates per SSE
3. **Client** (Browser, OBS, pywebview) zeigt das HTML an und empfängt Updates

```
Plugin-Prozess                         API-Server                         Browser / OBS
      │                                    │                                   │
      │── POST /overlay-html (HTML) ──────→│                                   │
      │                                    │── GET /plugins/{name}/overlay ───→│
      │                                    │    (statisches HTML)              │
      │                                    │                                   │
      │── POST /state {"count": 5} ──────→│                                   │
      │                                    │── SSE: data: {"count": 5} ──────→│
      │                                    │    (EventSource-Stream)           │
```

## Statisches Overlay-HTML

Jedes Plugin **muss** die Methode `get_overlay_html()` überschreiben. Sie wird von `run()` genau einmal beim Start aufgerufen und das Ergebnis per `POST /api/v1/plugins/{name}/overlay-html` beim API-Server registriert.

```python
def get_overlay_html(self) -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; padding: 0; background: transparent; }
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
                new EventSource("/api/v1/plugins/mein-plugin/stream");
            }, 2000);
        };
    </script>
</body>
</html>"""
```

**Wichtig**: Das HTML wird nur **einmal** beim Start geladen. Wenn du das HTML zur Laufzeit ändern musst (z. B. bei Theme-Wechsel), verwende `register_overlay(html)`. Für häufige inhaltliche Änderungen ist `push_state()` der richtige Weg.

### Die Overlay-URL

Nach der Registrierung ist das Overlay unter folgender URL erreichbar:

```
http://127.0.0.1:29185/api/v1/plugins/<plugin-name>/overlay
```

Diese URL kannst du als **Browser-Quelle** in OBS einrichten.

## Dynamischer Zustand per SSE

Server-Sent Events (SSE) ermöglichen Echtzeit-Updates vom Server zum Client. Der Client öffnet eine dauerhafte HTTP-Verbindung, über die der Server Nachrichten senden kann.

### Zustand setzen

```python
self._state["count"] = self._zaehler
self.push_state()
```

**Was passiert intern?**

1. `push_state()` ruft `self.api_post(f"/plugins/{PLUGIN_NAME}/state", {"state": self.state})` auf
2. Der API-Server speichert den Zustand im `PluginStateStore` und aktualisiert den Heartbeat
3. Der API-Server veröffentlicht ein Event `plugin.{name}.state_update` auf dem EventBus
4. Alle SSE-Clients, die `GET /api/v1/plugins/{name}/stream` abonniert haben, empfangen die Nachricht

### Zustand im Client empfangen

```javascript
const es = new EventSource("/api/v1/plugins/mein-plugin/stream");
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById("counter").innerText = data.count;
};
es.onerror = () => {
    es.close();
    setTimeout(() => {
        // Automatische Wiederverbindung nach 2 Sekunden
        window.location.reload();
    }, 2000);
};
```

### Wann push_state() aufrufen?

- **Nach jeder Zustandsänderung**, die im Overlay sichtbar sein soll
- **In `on_tick()`**, wenn sich der Zustand periodisch ändert (z. B. Timer-Countdown)
- **Nicht** bei jeder einzelnen Änderung, wenn mehrere Änderungen in schneller Folge passieren – sammle sie und rufe `push_state()` einmal auf.

## Zustand über Neustarts hinweg

Der `push_state()`-Zustand ist **flüchtig** – er lebt nur im API-Server. Wenn das Plugin neu startet, ist der Zustand weg.

Für persistente Daten, die über Neustarts erhalten bleiben sollen:

```python
class MeinPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._daten_pfad = self._data_dir / "zustaende.json"
        self._daten = self._laden()

    def _laden(self):
        if self._daten_pfad.exists():
            try:
                return json.loads(self._daten_pfad.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _speichern(self):
        try:
            self._daten_pfad.parent.mkdir(parents=True, exist_ok=True)
            self._daten_pfad.write_text(
                json.dumps(self._daten, indent=4), encoding="utf-8"
            )
        except Exception:
            pass
```

Verwende dafür `self._data_dir` – das Datenverzeichnis bleibt über Plugin-Neustarts erhalten.

## Theme-Unterstützung

Die Eigenschaft `self.theme_style` gibt CSS-Variablen aus dem aktuellen Plugin-Theme zurück:

```python
def get_overlay_html(self) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <style>
{self.theme_style}
        body {{
            background: var(--background);
            color: var(--text);
        }}
        .zahl {{
            font-size: 48px;
            color: var(--accent);
        }}
    </style>
</head>
<body>
    <div class="zahl" id="counter">0</div>
</body>
</html>"""
```

Verfügbare CSS-Variablen:

| Variable | Beschreibung |
|---|---|
| `--background` | Hintergrundfarbe |
| `--text` | Textfarbe |
| `--accent` | Akzentfarbe |
| `--muted` | Dezentere Farbe |
| `--danger` | Warn-/Fehlerfarbe |
| `--separator` | Trennerfarbe |

## GUI-Fenster mit pywebview

Die Basisklasse öffnet automatisch ein pywebview-Fenster, das auf die Overlay-URL zeigt. Das Fenster ist standardmäßig im Vordergrund (`on_top=True`).

Falls pywebview nicht installiert ist, erscheint eine Fehlermeldung und das Overlay ist nur über die Browser-URL erreichbar.

Mit dem Flag `--gui-hidden` wird das Fenster unterdrückt – nützlich für Server ohne Desktop oder wenn du nur die OBS-Browser-Quelle nutzt:

```bash
python src/plugins/mein-plugin/main.py --gui-hidden
```

## Fensterzustand speichern

Die Fenstergröße kann gespeichert werden:

```python
def _on_save_dims(self, args):
    self.save_window_state(
        args.get("width", 500),
        args.get("height", 400),
    )
```

Die gespeicherten Werte werden beim nächsten Start automatisch wiederhergestellt.

## Häufige Fehler

| Fehler | Ursache | Lösung |
|---|---|---|
| Overlay bleibt schwarz | `get_overlay_html()` nicht implementiert | Überschreibe die Methode |
| Keine Echtzeit-Updates | `push_state()` wird nicht aufgerufen | Rufe `push_state()` nach jeder Zustandsänderung |
| SSE-Verbindung bricht ab | Keine Wiederverbindung im JS | Implementiere `onerror`-Handler mit `setTimeout` |
| GUI-Fenster öffnet nicht | pywebview nicht installiert | Nutze die Browser-URL in OBS |
| Theme-Variablen wirken nicht | `theme_style` nicht ins CSS eingebunden | Füge `{self.theme_style}` in `get_overlay_html()` ein |
