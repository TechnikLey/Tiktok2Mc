## Control Method: DCS vs. ICS

### Wie kommunizieren Plugins mit der Außenwelt?

Zwei Systeme:

**DCS** = **Direct Control System** (HTTP-basiert, Browser-Source in OBS)
**ICS** = **Interface Control System** (GUI-Fenster mit pywebview, Window Capture in OBS)

```yaml
# config.yaml
control_method: DCS    # Oder: ICS
```

---

### DCS: Direct Control (Standard)

```
Plugin                    Streaming-Software (OBS)
  ↓                           ↓
Flask HTTP-Server    →    Browser-Source (http://localhost:PORT)
  → HTML/CSS wird direkt im Browser gerendert
  → Live-Updates via Server-Sent Events (SSE)
```

**Funktioniert so:**
- Plugin startet einen Flask-Server auf `localhost:PORT`
- OBS lädt die URL als **Browser-Source**
- Daten werden direkt im Browser gerendert (Live-Updates via SSE)

**Vorteile:**
- ✓ Schnell und direkt (keine Screencapture-Artefakte)
- ✓ Zuverlässig
- ✓ Transparenter Hintergrund möglich (für Overlays)

**Nachteile:**
- ✗ Streaming-Software muss Browser-Source unterstützen

---

### ICS: Interface Control (Fallback)

```
Plugin                    Streaming-Software (OBS)
  ↓ (pywebview Fenster)       ↓
 GUI wird angezeigt
  ↓ (Window Capture in OBS)
Overlay im Stream
```

**Funktioniert so:**
- Plugin öffnet ein **pywebview-Fenster** mit der GUI
- User nutzt **Window Capture** in OBS, um das Fenster aufzunehmen
- Ergebnis: Visuelle Integration in den Stream

**Vorteile:**
- ✓ Funktioniert mit jeder Streaming-Software (auch TikTok Live Studio)
- ✓ Keine Browser-Source nötig

**Nachteile:**
- ✗ Overhead durch Screencapture
- ✗ Höhere Latenz
- ✗ Qualitätsverlust möglich

---

### Wann welches System?

| Situation | Empfehlung |
|-----------|------------|
| OBS Studio mit Browser-Source | DCS |
| TikTok Live Studio (keine Browser-Source) | ICS |
| Custom Streaming Software | DCS |
| Lokales Testen | DCS |

---

### DCS vs. ICS in der Registry

Jedes Plugin definiert bei der Registrierung, ob es ICS unterstützt:

```python
register_plugin(AppConfig(
    name="Timer",
    path=MAIN_FILE,
    enable=True,
    level=4,
    ics=True     # Unterstützt ICS (hat pywebview-GUI)
))

register_plugin(AppConfig(
    name="App",
    path=APP_EXE_PATH,
    enable=True,
    level=2,
    ics=False    # Nur DCS (kein GUI-Fenster)
))
```

**`ics=True`** = Plugin hat eine pywebview-GUI und unterstützt Window Capture
**`ics=False`** = Plugin läuft nur als HTTP-Server (DCS)

> [!NOTE]
> Alle Built-in Plugins (Timer, DeathCounter, WinCounter, LikeGoal, OverlayTxt) haben `ics=True`.

---

### Zur Laufzeit (start.py)

`start.py` prüft die `control_method` aus der Config und den `ics`-Wert jedes Plugins:

```python
if app.ics and CONTROL_METHOD == "DCS" and app.enable:
    # Plugin hat GUI, aber DCS ist gewünscht:
    # → Starte mit --gui-hidden (nur Flask-Server, kein Fenster)
    start_exe(path=app.path, name=app.name,
              hidden=get_visibility(app.level), gui_hidden=True)
elif app.enable:
    # Normaler Start (mit GUI wenn ics=True, ohne wenn ics=False)
    start_exe(path=app.path, name=app.name,
              hidden=get_visibility(app.level))
```

**Das bedeutet:**
- Bei `control_method: DCS` werden GUI-Plugins mit `--gui-hidden` gestartet → Flask läuft, aber kein Fenster wird geöffnet
- Bei `control_method: ICS` werden GUI-Plugins normal gestartet → pywebview öffnet ein Fenster

---

### Merksätze

- **DCS = HTTP-Server, Browser-Source in OBS**
- **ICS = pywebview-Fenster, Window Capture in OBS**
- **DCS ist Standard** (schneller, zuverlässiger)
- **ICS ist der Fallback** (wenn keine Browser-Source verfügbar)
- **Alle Built-in Plugins unterstützen ICS** (`ics=True`)

→ [Nächstes: PLUGIN_REGISTRY](./ch04-02-The-PLUGIN_REGISTRY.md)