## Control Method: DCS vs. ICS

### How Do Plugins Communicate with the Outside World?

Two systems:

**DCS** = **Direct Control System** (HTTP-based, browser source in OBS)
**ICS** = **Interface Control System** (GUI window with pywebview, window capture in OBS)

```yaml
# config.yaml
control_method: DCS    # Or: ICS
```

---

### DCS: Direct Control (Standard)

```
Plugin                    Streaming Software (OBS)
  ↓                           ↓
Flask HTTP Server    →    Browser Source (http://localhost:PORT)
  → HTML/CSS is rendered directly in the browser
  → Live updates via Server-Sent Events (SSE)
```

**How it works:**
- Plugin starts a Flask server on `localhost:PORT`
- OBS loads the URL as a **browser source**
- Data is rendered directly in the browser (live updates via SSE)

**Advantages:**
- ✓ Fast and direct (no screen capture artifacts)
- ✓ Reliable
- ✓ Transparent background possible (for overlays)

**Disadvantages:**
- ✗ Streaming software must support browser source

---

### ICS: Interface Control (Fallback)

```
Plugin                    Streaming Software (OBS)
  ↓ (pywebview window)       ↓
 GUI is displayed
  ↓ (Window Capture in OBS)
Overlay in stream
```

**How it works:**
- Plugin opens a **pywebview window** with the GUI
- User uses **Window Capture** in OBS to capture the window
- Result: Visual integration into the stream

**Advantages:**
- ✓ Works with any streaming software (including TikTok Live Studio)
- ✓ No browser source required

**Disadvantages:**
- ✗ Overhead due to screen capture
- ✗ Higher latency
- ✗ Loss of quality possible

---

### When to Use Which System?

| Situation | Recommendation |
|-----------|----------------|
| OBS Studio with browser source | DCS |
| TikTok Live Studio (no browser source) | ICS |
| Custom streaming software | DCS |
| Local testing | DCS |

---

### DCS vs. ICS in the Registry

When registering, each plugin defines whether it supports ICS:

```python
register_plugin(AppConfig(
    name="Timer",
    path=MAIN_FILE,
    enable=True,
    level=4,
    ics=True     # Supports ICS (has pywebview GUI)
))

register_plugin(AppConfig(
    name="App",
    path=APP_EXE_PATH,
    enable=True,
    level=2,
    ics=False    # DCS only (no GUI window)
))
```

**`ics=True`** = Plugin has a pywebview GUI and supports window capture
**`ics=False`** = Plugin only runs as an HTTP server (DCS)

> [!NOTE]
> All built-in plugins (Timer, DeathCounter, WinCounter, LikeGoal, OverlayTxt) have `ics=True`.

---

### At Runtime (start.py)

`start.py` checks the `control_method` from the config and the `ics` value of each plugin:

```python
if app.ics and CONTROL_METHOD == "DCS" and app.enable:
    # Plugin has GUI, but DCS is desired:
    # → Start with --gui-hidden (Flask server only, no window)
    start_exe(path=app.path, name=app.name,
              hidden=get_visibility(app.level), gui_hidden=True)
elif app.enable:
    # Normal start (with GUI if ics=True, without if ics=False)
    start_exe(path=app.path, name=app.name,
              hidden=get_visibility(app.level))
```

**This means:**
- With `control_method: DCS`, GUI plugins are started with `--gui-hidden` → Flask is running, but no window opens
- With `control_method: ICS`, GUI plugins are started normally → pywebview opens a window

---

### Key Points

- **DCS = HTTP server, browser source in OBS**
- **ICS = pywebview window, window capture in OBS**
- **DCS is the default** (faster, more reliable)
- **ICS is the fallback** (if no browser source available)
- **All built-in plugins support ICS** (`ics=True`)

→ [Next: PLUGIN_REGISTRY](./ch04-02-The-PLUGIN_REGISTRY.md)
