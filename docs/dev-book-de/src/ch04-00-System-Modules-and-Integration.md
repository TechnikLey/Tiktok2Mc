# System-Module und Integration

### Modularität: Das Geheimnis der Skalierbarkeit

Das Streaming-Tool ist nicht ein **riesiger monolithischer Block**, sondern besteht aus **unabhängigen Komponenten**:

```
Streaming-Tool
  │
  ├─ Core (Module - Infrastruktur)
  │   ├─ validator.py (Validierung)
  │   ├─ models.py (Datentypen)
  │   ├─ utils.py (Hilfsfunktionen)
  │   ├─ paths.py (Pfad-Management)
  │   └─ cli.py (Command-Line Interface)
  │
  ├─ Built-in Plugins (Standard-Funktionen)
  │   ├─ Timer (Countdown-Tracker)
  │   ├─ DeathCounter (Tod-Zähler)
  │   ├─ WinCounter (Sieg-Zähler)
  │   ├─ LikeGoal (Like-Milestone-Tracker)
  │   └─ OverlayTxt (Text-Overlay für OBS)
  │
  └─ Custom Plugins (Benutzer-definiert)
      └─ Deine eigenen Plugins
```

**Das Geheimnis:** Jedes Plugin ist **von den anderen unabhängig**, kann sich aber über **HTTP (DCS)** mit anderen verbinden!

---

### Module vs. Plugins

| Kategorie | Speicherort | Zweck | Beispiele |
|-----------|-------------|-------|----------|
| **Module (Core)** | `src/core/` | Infrastruktur & Kernlogik | validator, models, utils, paths, cli |
| **Built-in Plugins** | `src/plugins/` | Standard-Funktionen | Timer, DeathCounter, WinCounter, LikeGoal, OverlayTxt |
| **Custom Plugins** | `plugins/` (Benutzer) | Benutzerdefinierte Erweiterungen | Deine eigenen Plugins |

---

### Die drei Kern-Konzepte

**1. Registry (Zentrale Verwaltung)**

Alle Plugins registrieren sich beim Start über `--register-only`:
```python
register_plugin(AppConfig(
    name="Timer",
    path=MAIN_FILE,
    enable=True,
    level=4,
    ics=True
))
```

→ `start.py` weiß, welche Plugins verfügbar sind und startet sie

---

**2. Control Methods (Steuermechanismen)**

Module können ihre Funktionen der **Außenwelt** anbieten:

- **DCS** (Direct Control System) = HTTP-basiert (Browser-Source in OBS)
- **ICS** (Interface Control System) = GUI-Fenster (pywebview, Window Capture in OBS)

→ User können Module von außen kontrollieren

---

**3. Daten-Sharing (Datenaustausch)**

Plugins teilen Daten über:
- **HTTP-Requests** (DCS-Kommunikation zwischen Plugins)
- **Dateien** (data/ Verzeichnis, z.B. JSON-Dateien)
- **Webhooks** (Events von Minecraft via HTTP POST)

→ Keine direkten Abhängigkeiten, nur standardisierte Protokolle!

---

### Architektur-Prinzipien

```
Autonomie:       Jedes Plugin funktioniert allein
  ↓
Registrierung:   Beim Start registrieren (--register-only)
  ↓
Kommunikation:   Via HTTP (DCS) und Webhooks
  ↓
Isolation:       Crash eines Plugins beeinflusst andere nicht
  ↓
Skalierbarkeit:  Neue Plugins einfach hinzufügbar
```

---

### Warum modular?

**Vor (monolithisch):**
- Ein Fehler → gesamtes Programm kaputt
- Neue Features → kompletter Rewrite
- Skalierung unmöglich

**Nach (modular):**
- Fehler isoliert ✓
- Plugin-basiert ✓
- Unbegrenzt erweiterbar ✓

→ [Nächstes Kapitel: Control Methods](./ch04-01-Control-Method.md)