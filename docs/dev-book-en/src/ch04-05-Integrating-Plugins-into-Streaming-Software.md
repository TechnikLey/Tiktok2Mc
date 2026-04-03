## Integrating Modules into Streaming Software

### Concept: Two Ways of Integration

Streaming tools (OBS, Streamlabs, etc.) need access to your modules:

1. **ICS (GUI modules)**: Window capture → The GUI window is shown as a video layer
2. **DCS (HTTP modules)**: Browser source → Browser renders HTML from HTTP server

### Comparison: ICS vs DCS

| Aspect | ICS | DCS |
|--------|-----|-----|
| **Integration** | Window Capture | Browser Source |
| **Technology** | Window capture | HTTP + HTML/CSS |
| **Scaling** | Native window size | Flexibly configurable |
| **Latency** | Higher (frame-to-frame) | Lower (direct rendering) |
| **Error handling** | Window must be visible | Port must be online |
| **Best for** | Desktop GUI tools | Live data (like counter, timer) |

### ICS Integration: Window Capture

**In OBS:**

1. `Source` → `+` → `Window Capture` add
2. Dropdown: Select GUI application (e.g. "GUI Module [gui_module.exe]")
3. Adjust size/position
4. Done – GUI will be added live to the stream

**Requirement:** Plugin must be registered with `ics=True` in the registry. The plugin itself opens the pywebview window — `start.py` just starts the process.

### DCS Integration: Browser Source

**In OBS:**

1. `Source` → `+` → `Browser Source` add
2. Enter URL: `http://localhost:PORT` (e.g. `http://localhost:9797`)
3. Set width/height (e.g. 1280×720)
4. Refresh rate: 60 FPS
5. Done – browser renders your HTML UI live

**Practical example:**

The like counter runs on port 9797:

```python
# likegoal.py
@app.route("/")
def index():
    return f"""
    <html>
    <style>
        body {{ background: transparent; color: #fff; font-size: 48px; text-align: center; padding: 20px; }}
    </style>
    <body>
        <h1 id="count">Loading...</h1>
        <script>
            setInterval(() => {{
                fetch('/api/like_count')
                    .then(r => r.json())
                    .then(d => document.getElementById('count').innerText = d.count);
            }}, 500);
        </script>
    </body>
    </html>
"""

@app.route("/api/like_count")
def get_like_count():
    return {"count": current_likes}

# Start Flask in thread
Thread(target=lambda: app.run(port=9797, debug=False, use_reloader=False), daemon=True).start()
```

**In OBS:** Browser source with URL `http://localhost:9797` → Live Like Counter overlay!

### Common Problems & Solutions

| Problem | Cause | Solution |
|---------|-------|----------|
| **URL not reachable** | Port blocked/incorrect | Check with `netstat -ano`, open firewall |
| **Browser source shows blank** | CORS error / HTML not loading | Inspect browser console (F12) |
| **Window capture doesn't work** | Module not registered with `ics=True` | Check registry and `level` |
| **Latency, delay** | Server too slow | Optimize server rendering, compress images |
| **Only browser source but my module has ics=True** | That's OK | ics=True means "also supports ICS", not "must use ICS" |

### Integration Checklist

**For DCS (HTTP):**
- ☑ Flask/Server runs in the background
- ☑ Port in registry correct
- ☑ HTML with `transparent` background (if overlay)
- ☑ Browser source in OBS with correct URL
- ☑ Refresh rate 30-60 FPS

**For ICS (Window Capture):**
- ☑ pywebview opens window
- ☑ Registry: `ics=True`
- ☑ `log_level` >= module `level`
- ☑ Window title clear
- ☑ OBS selects via dropdown
  
**Next step:** [Create your own plugin](./ch02-00-Create-your-own-plugin.md)