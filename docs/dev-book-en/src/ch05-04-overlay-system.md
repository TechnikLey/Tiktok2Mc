# Overlay System

The overlay system allows displaying text and graphics in the live stream. There are two ways to use overlays: via the Hook API and via the Plugin system.

## Overlay in Hooks

Hooks can display text using `api.send_overlay_text()`:

```python
api.send_overlay_text(
    title="New Follower!",
    subtitle=f"{user} is now following!",
    duration=5,
    overlay_name="default"
)
```

Parameters:

- `title` (str): Main text
- `subtitle` (str, optional): Smaller text below
- `duration` (int, optional): Display duration in seconds (default: 3)
- `overlay_name` (str, optional): Name of the overlay (default: "default")

The function returns `True` on success, otherwise `False`.

## Overlay in Plugins

Plugins can provide complete HTML overlays. A detailed guide can be found in [Overlays & State](./ch03-07-overlays-and-state.md).

```python
def get_overlay_html(self) -> str:
    return "<html><body>...</body></html>"
```

The HTML overlay is integrated in OBS via a URL as browser source:

```
http://127.0.0.1:29185/api/v1/plugins/<plugin-name>/overlay
```

## Real-Time Updates

Plugins can update their state via Server-Sent Events (SSE):

```python
self.push_state()
```

The overlay HTML connects to the SSE endpoint:

```javascript
const es = new EventSource("/api/v1/plugins/my-plugin/stream");
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById("counter").innerText = data.count;
};
```

## Overlay in actions.mca

The `actions.mca` supports overlay text directly:

```
follow: >>Welcome!|{user} is here!|4
```

The format is: `>>Title|Subtitle|Duration`

- Parts are separated by `|`
- `{user}` is replaced by the TikTok username
- `{comment}` is replaced by the comment text (for Comment events)
