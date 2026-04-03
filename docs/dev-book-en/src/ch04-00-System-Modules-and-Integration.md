# System Modules and Integration

### Modularity: The Secret to Scalability

The streaming tool is not a **huge monolithic block**, but consists of **independent components**:

```
Streaming Tool
  │
  ├─ Core (Modules - Infrastructure)
  │   ├─ validator.py (validation)
  │   ├─ models.py (data types)
  │   ├─ utils.py (helper functions)
  │   ├─ paths.py (path management)
  │   └─ cli.py (Command-Line Interface)
  │
  ├─ Built-in Plugins (standard functions)
  │   ├─ Timer (countdown tracker)
  │   ├─ DeathCounter (death counter)
  │   ├─ WinCounter (win counter)
  │   ├─ LikeGoal (like milestone tracker)
  │   └─ OverlayTxt (text overlay for OBS)
  │
  └─ Custom Plugins (user-defined)
      └─ Your own plugins
```

**The secret:** Every plugin is **independent of the others**, but can connect with others via **HTTP (DCS)**!

---

### Modules vs. Plugins

| Category | Location | Purpose | Examples |
|----------|----------|---------|----------|
| **Modules (core)** | `src/core/` | Infrastructure & core logic | validator, models, utils, paths, cli |
| **Built-in plugins** | `src/plugins/` | Standard functions | Timer, DeathCounter, WinCounter, LikeGoal, OverlayTxt |
| **Custom plugins** | `plugins/` (user) | User-defined extensions | Your own plugins |

---

### The Three Core Concepts

**1. Registry (central administration)**

All plugins register at startup via `--register-only`:
```python
register_plugin(AppConfig(
    name="Timer",
    path=MAIN_FILE,
    enable=True,
    level=4,
    ics=True
))
```

→ `start.py` knows which plugins are available and starts them

---

**2. Control Methods**

Modules can offer their functions to the **outside world**:

- **DCS** (Direct Control System) = HTTP-based (browser source in OBS)
- **ICS** (Interface Control System) = GUI window (pywebview, window capture in OBS)

→ Users can control modules from outside

---

**3. Data Sharing**

Plugins share data via:
- **HTTP requests** (DCS communication between plugins)
- **Files** (data/ directory, e.g. JSON files)
- **Webhooks** (events from Minecraft via HTTP POST)

→ No direct dependencies, just standardized protocols!

---

### Architecture Principles

```
Autonomy:       Each plugin works alone
  ↓
Registration:   Register at startup (--register-only)
  ↓
Communication:  Via HTTP (DCS) and webhooks
  ↓
Isolation:      Crash of one plugin does not affect others
  ↓
Scalability:    New plugins can be easily added
```

---

### Why Modular?

**Before (monolithic):**
- One error → entire program broken
- New features → complete rewrite
- Scaling impossible

**After (modular):**
- Errors isolated ✓
- Plugin-based ✓
- Infinitely expandable ✓

→ [Next chapter: Control Methods](./ch04-01-Control-Method.md)
