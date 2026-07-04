# Overlays & Zustand

Plugins können Overlay-Inhalte für OBS (Open Broadcaster Software) oder das pywebview-Fenster bereitstellen. Die Kommunikation erfolgt über Server-Sent Events (SSE) für Echtzeit-Updates.

## Overlay-HTML

Jedes Plugin muss die Methode `get_overlay_html()` überschreiben. Sie gibt den HTML-String zurück, der im Overlay angezeigt wird:

```python
def get_overlay_html(self) -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; padding: 0;
               font-family: Arial, sans-serif;
               background: transparent; }
        .count { font-size: 48px; color: #ff4444; }
    </style>
</head>
<body>
    <div class="count" id="counter">0</div>
    <script>
        const es = new EventSource("/api/v1/plugins/mein-plugin/stream");
        es.onmessage = (e) => {
            document.getElementById("counter").innerText = JSON.parse(e.data).zahl;
        };
        es.onerror = () => { es.close(); setTimeout(() => connect(), 2000); };
    </script>
</body>
</html>"""
```

## Zustand mitteilen

Rufe `push_state()` auf, um den aktuellen Zustand an die API zu senden. Der Zustand wird dann per SSE an alle verbundenen Overlay-Clients verteilt:

```python
self._state["count"] += 1
self.push_state()
```

Der Zustand sollte immer ein Dictionary sein:

```python
@property
def state(self):
    return self._state

@state.setter
def state(self, value):
    self._state = value
```

## Overlay als Browser-Quelle

Wenn das Plugin ohne GUI-Fenster läuft (`--gui-hidden` oder wenn pywebview nicht installiert ist), kannst du die Overlay-URL als Browser-Quelle in OBS einrichten:

```
http://127.0.0.1:29185/api/v1/plugins/<plugin-name>/overlay
```

## GUI-Fenster mit pywebview

Die Basisklasse öffnet automatisch ein pywebview-Fenster, das auf das Overlay-HTML zeigt. Das Fenster ist standardmäßig im Vordergrund (`on_top=True`).

Falls pywebview nicht installiert ist, wird eine Fehlermeldung ausgegeben und das Overlay ist nur über die URL erreichbar.

## Theme-Unterstützung

Über `self.theme_style` erhältst du CSS-Variablen aus dem aktuellen Theme:

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
    </style>
</head>
<body>
    <div id="counter">0</div>
</body>
</html>"""
```

## Fensterzustand speichern

Die Fenstergröße kann gespeichert und wiederhergestellt werden:

```python
def _on_save_dims(self, args):
    self.save_window_state(
        args.get("width", 500),
        args.get("height", 400),
    )
```
