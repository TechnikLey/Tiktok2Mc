# TikTok-Chatbot — Design & Umsetzungsplan

> Status: **Phase 1–4 umgesetzt** (Kernmodul, Bridge-Wiring, API-Routen,
> GUI-Tab inkl. Session-Login Variante A + B). Offen: nur noch Teile von
> Phase 5 (Doku in dev-book EN+DE).
> Dieses Dokument bündelt alle Erkenntnisse und Entscheidungen zum geplanten
> TikTok-Chatbot für TikTok2Mc. Es dient als Referenz für die Umsetzung.

---

## 1. Überblick

Der Chatbot ermöglicht es, **automatisch Nachrichten im TikTok-Live-Chat zu
verschicken** — z. B.:

- Dank an Viewer für Gifts/Follows („Danke @user für das Gift!“)
- Antworten auf Keyword-Befehle („!discord“ → Bot postet den Discord-Link)
- Hinweise/Aktionen, die über `actions.mca` getriggert werden

**Wichtig:** Lesen von Events (Comments, Gifts, Likes …) funktioniert ohne
Login — das macht TikTok2Mc bereits heute. Der Chatbot betrifft nur das
**Schreiben** von Nachrichten.

---

## 2. Technische Grundlagen

| Aspekt | Detail |
|---|---|
| Library | `TikTokLive` (aktuell 6.6.6 gepinnt) |
| Senden | `await client.send_room_chat(content)` — vorhanden seit 6.x (`client.py`) |
| Login | `client.web.set_session(session_id, tt_target_idc)` setzt die Cookies `sessionid` + `sessionid_ss` auf `.tiktok.com` |
| Room-ID | Wird beim Verbinden automatisch geholt — **nicht manuell nötig** |
| Signierung | Läuft über Euler Stream (kostenlose Community-Stufe) — davon unabhängig |
| Umsetzungsort | Eigenes Kernmodul `src/core/tiktok_chatbot.py` (siehe §6) — läuft im Bridge-Prozess mit direktem Client-Zugriff, Event-Anbindung über `event_bus` |

### 7.0.0-Hinweis

TikTokLive 7.0.0 enthält einen Cookie-Domain-Fix (`web_base.py`), der genau
eingeloggte Sessions betrifft (verhindert doppelte Cookies). Sobald der
Chatbot umgesetzt wird, sollte geprüft werden, ob auf 7.x gewechselt wird.
Für den reinen Lesepfad bleibt 6.6.6 korrekt gepinnt.

---

## 3. Was der Bot zum Verbinden braucht

| Was | Wofür | Woher |
|---|---|---|
| `@username` des Streamers | Verbindung zum Live (Lesen) | TikTok-URL — **haben wir schon** |
| `sessionid` (Cookie) | Identität des Accounts, als der gepostet wird | Browser-Cookie oder Webview-Login (siehe §4/§5) |
| `tt-target-idc` *(optional)* | TikTok-Rechenzentrum (z. B. `va`, `maliva`, `useast2a`) | Steht in denselben Cookies; falscher Wert = Auth-Fehler |
| Room-ID | ❌ nicht nötig | Holt die Library selbst |
| Euler-API-Key | ❌ nicht nötig | Nur für höhere Rate-Limits beim Lesen relevant |

---

## 4. Variante A — Manuelle Session-Eingabe

Der User holt die `sessionid` selbst aus dem Browser:

1. Browser öffnen → **tiktok.com** → mit dem Account einloggen, der im Chat
   schreiben soll
2. **F12** → Tab **„Application"** (Chrome/Edge) bzw. **„Speicher"** (Firefox)
3. Links: **Cookies → https://www.tiktok.com**
4. Zeile **`sessionid`** suchen → Wert kopieren
5. Optional: Wert von **`tt-target-idc`** notieren
6. Beides ins GUI-Feld von TikTok2Mc eintragen

**Vorteile:** Einfach zu implementieren, keine Extra-Abhängigkeiten.
**Nachteile:** Für Nicht-Techniker ungewohnt; Fehleranfällig (falsches Feld,
abgelaufene Session).

---

## 5. Variante B — Eingebetteter Webview-Login (wie TikFinity)

> **Umgesetzt** (GUI-Prozess, `src/python/gui.py`): „Mit TikTok anmelden"-
> Button im Chatbot-Tab → `pywebview.api.open_tiktok_login()` öffnet ein
> pywebview-Fenster auf die TikTok-Login-Seite; ein Worker-Thread pollt
> `Window.get_cookies()` (Timeout 5 min), extrahiert `sessionid` +
> `tt-target-idc` via `core.chatbot_session.extract_session_cookies()`,
> speichert verschlüsselt und setzt das Reload-Signal. Das Dashboard pollt
> `get_tiktok_login_state()` und aktualisiert Badge/Toast. Ohne Desktop-App
> (Browser-Dashboard) bleibt der Button ausgeblendet — manuelle Eingabe als
> Fallback.

Ablauf analog zu TikFinity, aber lokal ohne Fremdserver:

1. User klickt in der GUI auf **„Mit TikTok anmelden"**
2. Ein **pywebview-Fenster** (PyQt6-Backend, bereits im Stack) öffnet die
   TikTok-Login-Seite
3. User loggt sich normal ein (Passwort / QR-Code)
4. Nach erfolgreichem Login liest das Tool die Cookies aus dem
   Webview-Profil aus → `sessionid` (+ `tt-target-idc`) automatisch extrahieren
5. Speicherung verschlüsselt via `SecureStorage` (Fernet) — siehe §7
6. Fenster schließt sich, GUI zeigt „Angemeldet als @name"

**Vorteile:** Komfortabelste UX, keine Cookie-Kopiererei, gleiche Erfahrung
wie kommerzielle Tools.
**Nachteile:** Mehr Aufwand (Webview-Cookie-Zugriff unter PyQt6 prüfen),
TikTok könnte Login-Flow ändern.

**Entscheidung: Beide Varianten anbieten.** Der User wählt in der GUI:
Webview-Login (Standard) *oder* manuelle Eingabe (Fallback, z. B. wenn der
Webview-Flow mal nicht funktioniert).

---

## 6. Architektur-Entscheidung: Nativ vs. Hook vs. Plugin

> **Wichtige Klärung:** „Nativ" heißt **nicht** „Logik in main.py kippen",
> sondern ein **eigenes Kernmodul** (`src/core/tiktok_chatbot.py`) plus dünne
> Verdrahtung in main.py — nach dem bestehenden Muster des Projekts
> (`port_scanner`, `overlay_utils`, `trigger_engine`). Deaktivierung läuft
> in allen Varianten über einen Schalter: Config-Flag (nativ) bzw.
> GUI-Haken (Hook) sind gleichwertige UX.

### Variante 1: Nativ als Kernmodul ⭐ (Empfehlung)

| Vorteile | Nachteile |
|---|---|
| Erstklassige Qualitätssicherung: pyright-geprüft, ruff-formatiert, direkte Unit-Tests ohne Loader-Simulation | Komplett Entfernen nur per Update (bei PyInstaller-Binary ohnehin irrelevant — User nutzen Toggles) |
| **Eigene Konfigurationsdatei** `config/chatbot.yaml` + **eigener GUI-Tab** (Nutzerentscheidung — bewusst NICHT die globale `config.yaml`) | Kern wird um ein Feature erweitert, das nicht jeder Nutzer aktiviert (mild — standardmäßig aus) |
| **event_bus-Subscription**: Bot hört Gift/Follow/Comment nebenläufig zur TriggerEngine — null Queue-Kopplung, keine zweite Trigger-Logik | |
| Voller Event-Zugriff (Gift-Namen, Streaks, Kommentare) ohne Erweiterung der HookAPI | |
| **Out-of-the-box**: Nach Login sofort aktiv — Templates/Keywords als Config-Felder, keine `actions.mca`-Zeilen nötig | |

### Variante 2: Hook

| Vorteile | Nachteile |
|---|---|
| Läuft im Bridge-Prozess → Client-Zugriff möglich | Braucht **dieselbe** ~10-Zeilen-main.py-Änderung wie nativ (`send_chat`-Kanal) — schont main.py also nicht mehr als nativ |
| Komplett entfernbar per Ordner-Löschung | Dynamik-Load via importlib: pyright prüft wenig, Tests müssen Loader simulieren |
| Fehler-Isolation bewährt (Hook-Boundary, `HOOK_0006`) | Eigene Config-Datei hätte der Hook auch — ist kein Unterschied mehr; Typisierung/Validierung aber schwächer (JSON-Schema statt Pydantic-Modellen) |
| Third Parties könnten den Bot anpassen, ohne Kerncode zu berühren | Hook erhält nur `(source_user, action, {})` — für Gift-Namen/Streaks müsste die HookAPI aufgebohrt werden |
| | User muss selbst `gift:$chatbot`-Zeilen pflegen — kein Out-of-the-box |

### Variante 3: Plugin (Subprozess)

| Vorteile | Nachteile |
|---|---|
| Maximale Isolation — Bot-Absturz berührt die Bridge nicht | Senden nur über neuen Bridge-HTTP-Endpoint (z. B. `POST /send_chat`) — größerer main.py-Eingriff als bei beiden anderen Varianten |
| Gut für schwergewichtige Logik (KI-Antworten, eigene DB) | IPC-Latenz durch Long-Polling (`?wait=1`) — spürbar bei Chat-Reaktionen |
| | Zwei Prozesse koordinieren (Start, Health, Reload); Session-Doppelverwaltung |
| | Für „Danke bei Gift" klar überdimensioniert |

### Begründung der Empfehlung (Nativ)

1. **Das alte Haupt-Hook-Argument war unzulässig:** Beide Varianten brauchen
   denselben minimalen main.py-Eingriff — „schont main.py" entscheidet nicht
   zwischen ihnen. Der echte Unterschied liegt in Qualitätssicherung,
   Event-Zugriff und Out-of-the-box-Betrieb, und da gewinnt das Kernmodul
   klar. (Die Konfiguration bekommt der Bot als **eigenständige Datei mit
   eigenem GUI-Tab** — siehe §7, Phase 2/3; die globale `config.yaml` bleibt
   unberührt.)
2. **First-Party gehört nicht in den Erweiterungs-Mechanismus:** Hooks gibt
   es, damit *Nutzer* fremde Integrationen andocken können. Der eigene
   Chatbot ist Produktfunktionalität — wie der Port-Scanner, der ebenfalls in
   `core/` lebt.
3. **event_bus passt perfekt:** Der Bot abonniert Events nebenläufig zur
   TriggerEngine, ohne Queues anzutasten und ohne dass Nutzer mca-Zeilen
   pflegen müssen.
4. **Wann der Hook doch richtig wäre:** Wenn der Bot als vom Nutzer
   austauschbares Vorlagen-/Anpassungssystem gedacht wäre. Das ist nicht das
   Ziel — Templates und Keywords sind konfigurierbar, die Logik nicht.

> **In allen drei Varianten gleich:** Session-Management (Login,
> SecureStorage) ist immer Kernarbeit — der Unterschied liegt nur darin, wo
> die Bot-*Logik* lebt.

---

## 7. Implementierungsplan

> **Status (2026-08-21):** Phase 1–4 umgesetzt (Kernmodul, Bridge-Wiring,
> API-Routen, GUI-Tab, Tests; Session-Login Variante A manuell + Variante B
> Webview). Offen: dev-book EN+DE.

### Phase 1 — Brücke: Chat-Send-Kanal (~100 Zeilen) ✅

1. **Neu** `src/core/tiktok_chatbot.py`: Das Kernmodul (siehe Phase 2) mit
   einer öffentlichen Send-Schnittstelle:

   ```python
   class TikTokChatbot:
       async def send(self, text: str) -> bool: ...
       def bind_client(self, client: TikTokLiveClient) -> None: ...
   ```

2. `src/python/main.py`: Nach Client-Erstellung `bot.bind_client(client)`
   aufrufen und die Bot-Task via `CrashManager.supervised_async_task`
   starten. **Einziger main.py-Eingriff (~10 Zeilen)** — Datei ist laut
   AGENTS.md besonders sensibel.

### Phase 2 — Das Kernmodul mit eigener Config (`src/core/tiktok_chatbot.py`) ✅

3. **Eigene Konfigurationsdatei** `config/chatbot.yaml` (Pfad über
   `core.paths` registrieren) — bewusst **nicht** die globale `config.yaml`:
   - `enabled` (Default: `false`)
   - **Spam-Protection:** `min_interval_s` (Mindestabstand, Default 5),
     `max_per_minute` (Nachrichten-Fenster, z. B. 10),
     `max_queue` (Drop bei Flut), `dedupe_identical` (Default: true),
     `max_len` (150 Zeichen, TikTok-Limit)
   - **Antwort-Regeln** (wann der Bot antwortet):
     `on_gift`, `on_follow`, `on_join` (je an/aus),
     `keyword_replies` (z. B. `!discord` → Link)
   - **Antwort-Inhalte** (was er antwortet): Templates
     `gift_thanks`, `follow_thanks`, `join_welcome` mit Platzhaltern
     `{user}`, `{gift}`; Keyword-Antworten aus `keyword_replies`
4. Event-Anbindung per **event_bus-Subscription** (Gift/Follow/Comment) —
   nebenläufig zur TriggerEngine, keine Queue-Kopplung, keine
   `actions.mca`-Pflicht für den Nutzer.
5. Rate-Limiter im Modul:
   - Mindestabstand zwischen Sends
   - Fenster-Limit (`max_per_minute`) + Drop bei vollem Queue-Limit
   - Dedupe identischer Nachrichten (TikTok blockt Duplikate)
   - Auto-Disable nach wiederholten Auth-Fehlern + `report_error()`
6. Live-Reload: GUI speichert → API schreibt `chatbot.yaml` → Bridge re-read
   via bestehendes Runtime-Signal-Muster (`core/runtime/`), kein Neustart.

### Phase 3 — API & eigener GUI-Tab ✅

7. Backend nach dem Thin-Routes-Muster:
   - Pydantic-Modelle (`ChatbotConfigResponse`, `ChatbotConfigUpdateRequest`,
     `ChatbotStatusResponse`) in `src/core/api/models.py`
   - Status-Cache als Tracker-Singleton in `src/core/api/chatbot_status.py`
     (gleiches Muster wie `tiktok_live.py`, Start/Stop im App-Lifespan)
   - Routes in `src/core/api/routes/chatbot.py`:
     `GET/PUT /api/v1/chatbot/config`, `GET /api/v1/chatbot/status`;
     Registrierung in `routes/__init__.py`; PUT schreibt das
     `reload_chatbot`-Runtime-Signal für die Bridge
8. **GUI-Tab „Chatbot"** (`templates/gui/`: Tab in `index.html`, Logik in
   neuem `chatbot-editor.js`, wiederverwendete DOM-Helper aus `app.js`):
   - **An/Aus**-Schalter (Master-Toggle, schreibt `enabled`)
   - **Spam-Protection**: Mindestabstand, Nachrichten/Minute,
     Warteschlangen-Limit, Dedupe-Haken
   - **Wann antworten**: Haken für Gift/Follow/Join +
     Keyword→Antwort-Liste (Editor wie Plugin-Config-Schema)
   - **Was antworten**: Template-Felder pro Event mit Platzhalter-Hinweis
     (`{user}`, `{gift}`)
   - Statuszeile: verbunden/nicht verbunden, Session-Status, letzte Sends

### Phase 4 — Session-Management (beide Varianten)

> Variante A umgesetzt (2026-08-21). Variante B umgesetzt (2026-08-21).

9. **Variante A:** ✅ GUI-Feld im Chatbot-Tab (`chatbot-editor.js`) →
   `PUT/GET/DELETE /api/v1/chatbot/session` → verschlüsselter Store in
   `data/chatbot_session.json` (`core/chatbot_session.py`, SecureStorage /
   Fernet — **niemals** Klartext in einer YAML; die API liefert nur eine
   maskierte Vorschau `abcd…wxyz`). Validierung: Länge 10–512, Charset,
   `tt-target-idc` optional.
10. **Variante B:** ✅ Webview-Login-Fenster (siehe §5) —
    `open_tiktok_login()` / `get_tiktok_login_state()` in `LauncherAPI`
    (`src/python/gui.py`), Cookie-Extraktion via
    `core.chatbot_session.extract_session_cookies()` (unit-getestet),
    Speicherung + Reload-Signal im GUI-Prozess, Dashboard-Polling in
    `chatbot-editor.js`; Button nur sichtbar, wenn die Desktop-App die
    Bridge-Methode anbietet
11. ✅ Bridge liest beim Connect die Session →
    `TikTokChatbot.apply_session_to_client(client)` ruft
    `client.web.set_session(sid, idc)` vor dem Verbinden auf (Wiring in
    `main.run_bot` direkt nach `bind_client`); `tt_target_idc` bleibt
    optionales Config-Feld
12. ✅ Status-Rückmeldung: `has_session` im `chatbot.status`-Event →
     Warnbanner im Chatbot-Tab, wenn der Bot aktiviert, aber ohne Login ist;
     Auto-Disable nach wiederholten Sendefehlern (CHATBOT_0003) + Fehlerbox;
     „Session abgelaufen" → erneut anmelden (die `sessionid` rotiert
     gelegentlich!)

### Phase 5 — Tests & Doku

> pytest (Kern-, Session- und API-Tests) und vitest (GUI-Tab inkl.
> Session-Flows) sind umgesetzt; ruff/pyright/eslint grün. Offen:
> dev-book EN+DE.

13. Unit-Tests: Limiter, Template-Formatting, Send-Guard, Config-Roundtrip
    (conftest mockt TikTokLive — das Modul importiert den Client nur als
    Typ-Hint, gesendet wird über die gebundene, gemockte Instanz);
    API-Tests in `tests/test_api/`; GUI-Tests (vitest) für den neuen Tab ✅
14. Dev-Books **EN + DE** synchron aktualisieren (Pflicht) — offen

---

## 8. Sicherheit

- Die `sessionid` ist **so wertvoll wie ein Passwort** — volle Kontoübernahme
  möglich.
- Speicherung ausschließlich verschlüsselt (`core/secure_storage.py`, Fernet
  mit maschinenlokalen Key-File).
- Kein Klartext in irgendeiner YAML (`config.yaml`, `chatbot.yaml`), Logs,
  Error-Reports oder Screenshots.
- Beim manuellen Kopieren gilt: nur eigene Geräte, Wert nie weitergeben.

---

## 9. Risiken & Grenzen

| Risiko | Bewertung / Gegenmaßnahme |
|---|---|
| **Account-Ban** | Automatisierte Posts sind ToS-Grauzone. Mit ≥5 s Abstand und wenigen Nachrichten pro Stream vertretbar, Restrisiko bleibt. Empfehlung: separaten Bot-Account verwenden, nicht den Haupt-Account. |
| **Chat-Rate-Limits** | TikTok limitiert Chat stark (auch TikFinity warnt davor). Limiter + Queue-Drop statt Warteschlange. |
| **Duplikat-Block** | TikTok verwirft identische aufeinanderfolgende Nachrichten → Variationen oder Skip. |
| **Session-Ablauf** | `sessionid` rotiert bei Sicherheitsereignissen/Logout; Login im Browser invalidiert sie. → klare GUI-Diagnose nötig. |
| **Anti-Bot-Detection** | TikTok erkennt Muster; keine Garantie. |

---

## 10. Vergleich mit TikFinity

TikFinity nutzt einen Autorisierungs-Popup-Flow („Connect to TikTok LIVE" →
TikTok-Fenster → „Authorize") und muss **vor jedem Stream neu verbunden**
werden. Der Chatbot dort hat dieselben Einschränkungen (Rate-Limits).
Unser Ansatz (§5) bildet diese UX lokal nach — ohne Fremdserver, dafür mit
beiden Login-Wegen zur Auswahl.

---

## 11. Euler Stream — was es ist, warum wir es nicht brauchen

- Unsere Library nutzt Euler **bereits heute**: Jede Verbindungsanfrage wird
  durch Eulers Signatur-Server signiert (kostenlose Community-Stufe).
- `eulerstream.com/websockets` ist ein zusätzlicher **Managed-Dienst**: Eulers
  Server verbindet sich selbst mit dem Stream und liefert fertige JSON-Events
  über `wss://ws.eulerstream.com?uniqueId=...&apiKey=...`
  (1M+ Events/Tag, <50 ms, 99.9 % Uptime).
- Für unseren Desktop-Anwendungsfall nicht nötig: zusätzliche Kosten +
  Abhängigkeit von einem Fremdanbieter. Relevant höchstens für
  Server-/Multi-Stream-Setups oder falls TikTok Direktverbindungen blockt.

---

## 12. Offene Punkte

- [x] Session-Login Variante A umsetzen (Phase 4): SecureStorage +
      `set_session` vor dem Verbinden, Warnung bei fehlender/abgelaufener
      Session
- [x] Session-Login Variante B (Webview-Login-Fenster, §5)
- [x] Keyword-Befehle: über event_bus abgedeckt (Nativ-Entscheidung,
      `_handle_event` matched Kommentar-Prefix case-insensitive)
- [x] PyQt6/pywebview: Cookie-Extraktion aus dem Webview-Profil verifizieren
      (`Window.get_cookies()` existiert seit pywebview 6.x, gepinnt 6.2.1;
      umgesetzt in `gui.py` + `extract_session_cookies`)
- [ ] Soll TikTokLive auf 7.x wechseln, sobald der Chatbot kommt?
      (Cookie-Fix betrifft eingeloggte Sessions)
- [ ] Dev-Books EN+DE ergänzen (Phase 5-Rest)
- [ ] Ban-Risiko final kommunizieren (Disclaimer im Setup-Dialog?)
