## Plugin in Streaming-Software integrieren

### Concept: Zwei Wege der Integration

Die Streaming-Tools (OBS, Streamlabs, etc.) brauchen Zugriff auf deine Plugins:

1. **ICS (GUI-Plugins)**: Fensteraufnahme → Das GUI-Fenster wird als Video-Layer gezeigt
2. **DCS (HTTP-Plugins)**: Browser-Quelle → Browser rendert HTML vom HTTP-Server

### Vergleich: ICS vs DCS

| Aspekt | ICS | DCS |
|--------|-----|-----|
| **Integration** | Window Capture | Browser Source |
| **Technologie** | Fensteraufnahme | HTTP + HTML/CSS |
| **Skalierung** | Native Fenstergröße | Flexibel konfigurierbar |
| **Latenz** | Höher (Screenshot-zu-Screenshot) | Niedriger (direkte Renderung) |
| **Fehlerbehandlung** | Fenster muss sichtbar sein | Port muss online sein |
| **Best for** | Desktop GUI Tools | Live-Daten (Like-Counter, Timer) |

### ICS-Integration: Fensteraufnahme

**In OBS:**

1. `Quelle` → `+` → `Fensteraufnahme` hinzufügen
2. Dropdown: Wähle GUI-Anwendung (z.B. "GUI Plugin [timer.exe]")
3. Größe/Position anpassen
4. Fertig – GUI wird live ins Stream übernommen

**Voraussetzung:** Plugin muss mit `ics=True` in Registry registriert sein. Das Plugin selbst öffnet das pywebview-Fenster — `start.py` startet nur den Prozess.

### DCS-Integration: Browser-Quelle

**In OBS:**

1. `Quelle` → `+` → `Browserquelle` hinzufügen
2. URL eingeben: `http://localhost:PORT` (z.B. `http://localhost:9797`)
3. Breite/Höhe einstellen (z.B. 1280×720)
4. Aktualisierungsrate: 60 FPS
5. Fertig – Browser rendert deine HTML-UI live

**Praktisches Beispiel:**

Der Like-Counter läuft auf Port 9797:

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

# Flask im Thread starten
Thread(target=lambda: app.run(port=9797, debug=False, use_reloader=False), daemon=True).start()
```

**In OBS:** Browser-Quelle mit URL `http://localhost:9797` → Live Like-Counter overlay!

### Häufige Probleme & Lösungen

| Problem | Ursache | Lösung |
|---------|--------|--------|
| **URL not reachable** | Port blockiert/falsch | `netstat -ano` check, Firewall öffnen |
| **Browser-Quelle zeigt blank** | CORS-Fehler / HTML lädt nicht | Browser-Konsole inspizieren (F12) |
| **Fenster-Capture funktioniert nicht** | Modul nicht mit `ics=True` | Registry überprüfen, `level` checken |
| **Latenz, Verzögerung** | Server zu langsam | Server-Rendering optimieren, Bilder komprimieren |
| **Es gibt nur Browser-Quelle, aber mein Modul hat ics=True** | Das ist OK | ics=True bedeutet "unterstützt auch ICS", nicht "muss ICS nutzen" |

### Integration-Checkliste

**Für DCS (HTTP):**
- ☑ Flask/Server läuft im Hintergrund
- ☑ Port in Registry korrekt
- ☑ HTML mit `transparent` background (falls Overlay)
- ☑ Browser-Quelle in OBS mit korrekter URL
- ☑ Aktualisierungsrate 30-60 FPS

**Für ICS (Window Capture):**
- ☑ pywebview öffnet Fenster
- ☑ Registry: `ics=True`
- ☑ `log_level` >= Modul-`level`
- ☑ Fenster-Titel eindeutig
- ☑ OBS wählt über Dropdown

**Nächster Schritt:**  [Eigenes Plugin erstellen](./ch02-00-Create-your-own-plugin.md)