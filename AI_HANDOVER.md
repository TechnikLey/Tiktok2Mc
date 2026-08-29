# AI Handover — TikTok2Mc: "Bridge stoppt nach Initial-Burst" (Live-Event-Problem)

> Erstellt: 2026-08-28 — Zweck: Eine andere KI soll die Arbeit nahtlos fortsetzen können.
> Aktualisiert: 2026-08-29 (**ROOT CAUSE GEFUNDEN + FIXED, §6e**): Deterministic nested non-reentrant `ctx.like_lock` deadlock in `_enqueue_like_triggers`; Fix = Option 2 (Einzel-Lock), live verifiziert (andykister: 36 Like- statt 2 Like-Events, 18 Trigger-Fires, kein Stopp).
> Alle Aussagen sind strikt nach dem Prinzip **"Nicht raten"** klassifiziert: `[BEWIESEN]` = per Code + Test belegt, `[HYPOTHESE]` = plausibel, aber nicht hart reproduziert, `[OFFEN]` = noch zu klären.

---

## 1. Problemstellung (Kurz)

Der **aktuelle** Bridge (`D:\Tiktok2Mc\src\python\main.py`, TikTokLive 6.6.5) liefert nach dem Initial-Burst (nach ~6–8s und ~5–10 Events) **keine weiteren Live-Events** — die Tier-Websocket ist offen, der Stream läuft, aber es kommen keine Events mehr. Die **alte** main.py (`D:\Streaming_Tool_pub\src\python\main.py`) lief kontinuierlich durch.

---

## 2. Repository-/Kontext-Lage

- **Aktueller Bridge (A):** `D:\Tiktok2Mc\src\python\main.py` — ~3080 Zeilen. Modell: `ctx = BotContext()` (Modul-global), `create_client(user)` Zeile ~2304 (→ heute `@client.on(ConnectEvent)`-Hook bindet Chatbot + erfasst `ctx.tiktok_client_loop`), `run_bot` Zeile ~2985. **`_run_client_blocking`/`_ws_stall_watchdog` wurden ENTFERNT** (§6e): Connect = pur `await asyncio.to_thread(client.run)` wie in der Referenz.
- **Alter Bridge (B/Referenz):** `D:\Streaming_Tool_pub\src\python\main.py` — ganz andere Architektur: Flask-Webhook (Port aus Config), `MAIN_LOOP`-Global, `print`-Logging (keine `[RAW]`-Marker), `await asyncio.to_thread(client.run)` (Zeile 886). Flask-Server startet **nur unter `__main__`** → beim Modul-Import für Tests läuft er nicht.
- **TikTokLive installiert:** **6.6.5** unter `D:\Programieren\Python\Python3.12\Lib\site-packages\TikTokLive\`
- Alle temporären Test-Skripte: `C:\Users\Finni\AppData\Local\Temp\opencode\` (ausführbare Harness-Dateien, siehe §7).

---

## 3. BEWIESEN — Was hart belegt ist

### 3.1 Symptom ist real [BEWIESEN]
- `bridge_debug --user andykister` reproduzierte den Stopp mehrfach (Logs `test_A_full.log`, `test_A_full2.log`): nach Initial-Burst keine Events mehr.
- `andykister` ist ein sehr aktiver Live-Account (real hoher Flow), aber sein Flow **schwankt stundenweise stark** — mal hoch, mal niedrig.

### 3.2 DAS LOOP-MODELL IST NICHT DIE URSACHE [BEWIESEN]
- Code-Beweis `client.py:510-522`: `client.run()` ≡ `loop.run_until_complete(client.connect())` — funktional äquivalent.
- Empirisch (`test_loop_ab.py`, Logs `test_loop_ab.log`/`test_loop_ab2.log`): Beide Modelle liefen mit den echten `create_client`-Handlern durch: **CURRENT = 82 Events / 40s kein Stopp; OLD = 77 Events / 40s kein Stopp.**
- → Der frühere Ansatz "Fix loop = böser Fehler" (Loop in falschem Thread erstellt) ist **widerlegt**. Der aktuelle `_run_client_blocking` baut die Loop korrekt (Set-Event-loop im selben Worker-Thread).

### 3.3 Der Stopp ist NICHT deterministisch durch einen einzelnen Handler-Befehls [BEWIESEN]
- Meine frühe "Reproduktion" (`test_stagesA.log` — LOG/BOTH-Stufen stoppte nach ~9–12 Events) hielt **nicht** stand:
  - `test_stagesB.log`, `test_stagesC.log` (2×2-Matrix: print/dict × TikTokLive-debug on/off): **kein Stopp in 4/4 Phasen** (30–41 Events, gap 0.47–4.95s).
- → Der Stopp ist **intermittierend und live-flow-/Scheduling-abhängig** — ein **Race**, kein fester Handler-Fehler.
> **2026-08-29 (§6e):** Diese Schlußfolgerung ist ÜBERHOLT. Der Stopp ist deterministisch (2. Like-Event) und trat in den frühen Tests nur deshalb nicht auf, weil dort `like_triggers` nicht geladen/kein 2. Like kam. Der damalige „Race"-Eindruck entstand aus Config/Flow-Stichproben ohne vollständige Config.

### 3.4 Fix 1+2 und 1690 pytest-Tests [BEWIESEN]
- Fix 1 (On-Loop-Arbeit minimieren) + Fix 2 (Watchdog-Auto-Heal) sind implementiert und statisch verifiziert (siehe §5).
- `ruff format` + `ruff check`: sauber (0 Findings).
- `pytest tests/test_core/`: **1690 passed, 1 skipped** (inkl. `test_main_bridge.py` = 102 passed).
- `bridge_debug --user andykister --duration 120`: verbunden, Events, keine fatal flags, kein Watchdog-Feuer, kein Crash — **aber** `andykister` hatte in diesem Fenster nur ~6 Events (niedriger Flow → kein Stress auf die Race).

---

## 4. HYPOTHESE — Die plausibelste (und einzige) Erklärung, die zum Code passt

> **2026-08-29: ÜBERHOLT durch §6e.** Die „On-Loop-Handler-Last / leise Drossel"-Hypothese war naheliegend, aber falsch: Die Ursache ist ein deterministischer **nested-Lock-Deadlock** (`_enqueue_like_triggers` re-acq `ctx.like_lock` unter `on_like`-Lock). Die Latenz (Reader > Ack > Drossel) stimmt nur zufällig mit dem Beobachtungsbild überein. Historisch dokumentiert:

**Timing-Race auf der Event-Loop der TikTokLive-Library (NICHT Loop-Isolation):**
- Reader, per-Frame-**Ack** (`ws_client.py:263-264`) und **`hb`-Heartbeat** (`_ping_loop_fn`, gleicher Loop) teilen **eine** asyncio-Loop.
- **Wichtig (Architektur-Klärung):** Diese Loop-Architektur ist bei **alt (B) und neu (A) identisch** — `TikTokLiveClient.run()` ≡ `_asyncio_loop.run_until_complete(connect())` (`client.py:226`; `_asyncio_loop` = `get_running_loop()`/sonst `new_event_loop()` `client.py:519-522`). B (`to_thread(client.run)`) und A (`to_thread(_run_client_blocking)` mit eigenem `new_event_loop`) lassen den TikTok-Client jeweils in **genau einer** Loop laufen. Es gibt also **keinen** alten Modus, der Reader/Ack/hb auf getrennte Loops verteilt hätte. Der Unterschied ist nicht "Loop-Isolation", sondern die **Menge synchroner Arbeit, die die Event-Handler im Aufruf-Kontext dieser einen Loop verrichten** (der neue, reichere Bridge hat mehr Checks/Queues/HTTP-Sinks pro Event als der spartanische alte).
- Bei hohem Event-Flow hält die **synchrone On-Loop-Handler-Arbeit** die Loop so lange besetzt (`hb` wird zu spät bedient), dass TikTok den Client **leise drosselt** — ohne Close-Frame; der Reader steht still. Genau das adressiert Fix 1 (On-Loop-Arbeit minimieren).
- Untermauert durch: TikTok sendet **keine Pongs** (Kommentar `ws_client.py:191`); isolierte Durchläufe (wenig Arbeit) laufen durch, reale Lows-Flow-Läufe mit wenig Arbeit ebenfalls, aber unter Stress stoppt es. [Konsistent mit §6b: moderater Flow → kein Stopp bei A noch B.]

**Einschränkung [OFFEN]:** Der **endgültige Beweis** (hochflow-Live-Lauf der behobenen Version: läuft durch bzw. Watchdog heilt statt zu stehen) steht noch aus.

---

## 5. UMSETZUNG — Fix 1 + Loop-Port + Deadlock-Fix (§6e) in `src/python/main.py`

> **Stand 2026-08-29:** Fix 2 (`_ws_stall_watchdog`) wurde ENTFERNT — er heilte den eigentlich blockierten Loop nicht (§6d) und ist durch den Deterministic-Fix (§6e) gegenstandslos. Der Loop-Port (Option 3, `await asyncio.to_thread(client.run)`) und der Deadlock-Fix sind UMgesetzt. Fix 1 bleibt.

### Fix 1 — On-Loop-Handler-Arbeit minimieren (GILT WEITERHIN)
- Per-Like-`[LIKE DEBUG]`-Diagnostik von `log.info` auf `log.debug` demoted:
  - `_enqueue_like_triggers` (Zeilen ~1653–1704): alle `[LIKE DEBUG]`-Zeilen (4×).
  - `on_like` (Zeilen ~2404–2452): `[LIKE DEBUG]`-Zeilen (4×) auf `log.debug`.
- `on_comment`: `event.user` wird **einmal pro Event** gelöst (`user = event.user` in try/except → `None` bei Fehler) und für die Fan-/Moderator-Checks wiederverwendet (`_ua(name, default)`-Helper) statt 4–5× `user_attr_safe(event, ...)` — jeder `event.user`-Zugriff ist eine Property, die `ExtendedUser.from_user` re-runt und bei unbekannten Proto-Feldern (z.B. `nickName`) werfen kann.

### Loop-Port (Option 3, §8A-alt) — Connect wie die Referenz
`_run_client_blocking` + eigener Loop + `set_event_loop` + Watchdog ENTFERNT; `run_bot` verbindet jetzt pur mit `await asyncio.to_thread(client.run)` (Referenz-Verhalten). `on_connect` erfasst `ctx.tiktok_client_loop` (der laufenden Loop) und bindet den Chatbot dort; `run_bot`-`finally` entbindet Chatbot + cleared `ctx.tiktok_client_loop`.

### Deadlock-Fix (§6e) — `_enqueue_like_triggers`: inneren Lock entfernt
Einziger Kritischer Abschnitt ist `on_like`'s `with ctx.like_lock:`; der Helfer acq nicht mehr erneut. Docstring dokumentiert den Lock-Vertrag. Regressionstest deckt den Nested-Lock ab.

### Verifiziert (2026-08-29)
- `pytest tests/test_core/test_main_bridge.py`: **103 passed**. Volle Suite: **2070 passed, 3 skipped** (151 s).
- `ruff format --check .` sauber; `ruff check` 0 Findings.
- Live 70 s (andykister): 36 Like- / 12 Comment- / 14 Join-Events, 18 Trigger-Fires, kein Stopp (§6e).

---

## 6. LIVE-TEST-VERLAUF (wichtigste Erkenntnisse zuletzt)

1. **Antwort `/webcast/fetch/` = `429 Too Many Requests`** → TikTok hat uns **temporär ratelimited/gedrosselt** — Folge unserer zahlreichen intensiven Testläufe (viele wiederholte Live-Verbindungen, vermutlich device_id-gebunden). Risiko eines Geräte-Blocks steigt mit jedem weiteren blinden Test. Nach ~45s Wartezeit war es wieder frei.
2. `bridge_debug` (90s): 9 Events, fast alle im Initial-Snapshot direkt nach Connect, dann `quiet` bis 27s → **`andykister` hatte in diesem Fenster kaum Flow**.
3. **Geplanter paralleler A/B** (A=current+fix, B=old, 150s) **schlug fehl / lieferte nichts:** der Orchestrator (`ab_orch.py`) hing über das 200s-Timeout — die beiden Subprozesse beendeten sich nicht sauber (`os._exit` im Skript feuerte nicht rechtzeitig, oder ein Thread hing). Kein brauchbares Teillog, da der Orchestrator alles bis Prozessende puffert und beim Kill nichts ausgegeben hat.

---

## 6b. NEU: Live-A/B (2026-08-28, `live_ab_run2.log`, andykister, 150s) [BEWIESEN]

Der parallele A/B **lief jetzt durch** (fixierter `ab_orch.py`). Zwei Harness-Fixes waren nötig:
1. **`ab_orch.py`** — cp1252-Encoding der Windows-Konsole crashte den Output-Thread (`\ufffd` → `UnicodeEncodeError`) und verschluckte alle Child-Zeilen. Fix: `sys.stdout.reconfigure(utf-8, errors="replace")` + Streaming Zeile-für-Zeile via Threads (echt parallel), `Popen.communicate(timeout=duration+10)` + `kill()` als harte Exit-Garantie; wertet `FINAL_EVENTS=`/`events= gap=` aus.
2. **`_abcount.py`** — Zähler war defekt (lieferte konstant `events=0`): die Bedingung `"[TikTokLive]" in msg` griff nie, weil `[TikTokLive]` ein **Formatter-Prefix** ist (`logger.py:51 FORM = "[%(name)s] ..."`), NICHT Teil von `record.getMessage()`. Fix: `record.name == "TikTokLive"` + `str(record.pathname).endswith("client.py")`. Offline verifiziert (1 nach echtem Record). **`__pycache__/_abcount` muss vor jedem Lauf gelöscht werden.**

### Befund [BEWIESEN] — kein A-Stopp in diesem Fenster
- **A (aktuell+Fix) 617** Received-Events vs **B (alt) 641** in 0–151s — praktisch identisch (Differenz ≈ B's Puffer-Artfakte nach Testende). Per-15s-Window-Verlauf nahezu deckungsgleich; A floss **durchgehend bis 150s**, kein Initial-Burst-Stopp.
- **Kein `[TIKTOK][WATCHDOG]`-Feuer** bei A (kein Stau → kein Auto-Heal nötig). Das einzige Fehlersignal waren `urllib.error code 10061 (Verbindung verweigert)`-Webhook-Proben gegen den nicht laufenden API-Server — **unkritisch**, ist das im §9 erwähnte, bekannte `bridge_debug`-Verhalten, NICHT die Stopp-Ursache.
- **Interpretation:** andykister hatte moderaten, aber kontinuierlichen Flow; der Stopp (intermittierend/flow-abhängig laut §3.3/§4) trat in diesem Fenster bei **keinem** der beiden auf. Negativer Beleg: Die Fixes **verschlechtern nicht** bzw. A ist nicht schlechter als die Referenz — aber der definitive Beweis (Stopp beobachtet und durch Fix behoben/heilt) steht weiterhin aus.

### Hinweis für künftige Läufe
- `live_ab_run2.log` (1.37 MB, TikTokLive-DEBUG roh) ist im Temp-Ordner; per 15s-Window-Analyse auswertbar, da der Orchestrator die Zeilen in Echtzeit-Reihenfolge schreibt.
- Zähler-Fix bedeutet: künftige Läufe geben brauchbare `events=`/`gap=`-Zeilen alle 10s.

---

## 6c. NU: Externes `SIGN_NOT_200` (HTTP 500) beim Start — NICHT unsere App [BEWIESEN]

2026-08-28: Das **gebaute Release** (`app.exe`) verbindet nicht mehr, Log zeigt sofort beim Start:
`tiktok.com OK` → `check_alive OK` → `tiktok.eulerstream.com/webcast/fetch/` **HTTP 500** → `SIGN_NOT_200` → Crash → Reconnect 30s → wieder 500.

- **Ursache ist extern:** Der Sign-Server `https://tiktok.eulerstream.com` ist der von `TikTokLive.web_settings.WebDefaults` hartkodierte Community-Sign-Dienst (`web_settings.py:127`); unsere App überschreibt nichts (kein eigenes `sign_url`/`sign_api_key` im Repo). Er soll die **signierte WebSocket-URL** liefern — schlägt er fehl, kommt die Verbindung gar nicht erst zustande.
- **Dokumentiertes, wiederkehrendes Infra-Problem des Anbieters** (GitHub `isaackogan/TikTokLive#311`, `#278` — 500/503 "API is not ready" / "A 500 error occurred whilst fetching the webcast URL"). Tritt auf, wenn der Sign-Host TikTok's Webcast nicht erreicht (WAF/Scraping-Drosselung). Meist temporär.
- **Kein Zusammenhang** mit unseren Fixes (Event-Stall/Loop); tritt vor jedem Websocket-Aufbau auf.
- **Empfehlung:** Pause (5–20 min) + Neustart. Option bei Beständigkeit: eulerstream **API-Key** (`WebDefaults.tiktok_sign_api_key`) oder eigener Sign-Server (`/webcast/fetch` implementieren).
- Zusätzlich im Log aufgefallen: `[LIKE DEBUG]`-Marker `validate_like_triggers` / `prepare_like_triggers` erscheinen weiterhin auf **INFO** — das sind andere Debug-Stellen **außerhalb** der im Fix 1 demoted Zeilen → §8D-Nachprüfung betrifft nur die On-Loop-Handler-Zeilen, nicht diese Config-Load-Debugs.

---

## 6d. NU: Stopp REAL reproduziert (darkygame) + Fix 2 WIRKUNGSLOS [BEWIESEN]

2026-08-28, gleicher Account `@darkygame`, gleicher Moment, gebaute Releases gegen-über:

**Neue App (mit Fix 1+2):** verbindet (Live established), **Initial-Burst** (`comment #1-3`, `like #1-2`, `join #1` um 21:46:50), dann **nichts mehr** — nur noch die 60s-App-Heartbeats (`heartbeat | status=alive`, Memory = Main-Loop), **kein** `[TIKTOK][WATCHDOG]`-Feuer, kein Reconnect.
**Alte App (Referenz):** verbindet (nach einem unkritischen, externen `ReadTimeout` beim ersten Sign-Versuch), liefert dann **kontinuierlich Ereignisse** (viele Likes/Actions/Follows) ohne Stopp.

Das ist **der bislang eindeutigste Beleg**: gleicher Account + Flow → alt läuft durch, neu stoppt nach Initial-Burst. Das Symptom ist real in der neuen Datei, unabhängig vom externen Sign-Server (der hier ja funktionierte).

### Warum Fix 2 wirkungslos ist (kritisch)
`_ws_stall_watchdog` wird von `_run_client_blocking` auf **derselben** TikTok-Loop gestartet (`main.py:3033 loop.create_task(_ws_stall_watchdog())`), die auch `loop.run_until_complete(client.connect())` (Zeile 3035) treibt. **Ist diese Loop blockiert/starved (§4-Hypothese), wird auch der Watchdog nie ausgeführt** — er kann sich nicht selbst heilen, weil er im selben blockierten Loop steckt. Die 60s-App-Heartbeats laufen weiter, weil sie auf dem **Main-Loop** sind (getrennt). → Fix 2 greift konstruktionsbedingt nicht gegen die Loop-Starvation.

### Handler-Last-Status (für Folge-Arbeit)
Die Handler sind bereits sauber isoliert: HTTP-Publish (`_publish_tiktok_event` → `_run_in_background`, Executor), Queue-Push (`enqueue_threadsafe` → `call_soon_threadsafe` auf `ctx.main_loop`), `_record_metrics_event` nur In-Memory-List. Fix 1 (Like-Debug demote + `event.user` einmal) hat den Stopp NICHT behoben. Vermuteter Engpass: schiere Menge synchroner Handler-Dispaches pro Sekunde auf der einen TikTok-Loop (Reader+Ack+hb).

### Empfohlene Lösungswege (geordnet nach Eingriffsgröße)
1. **Fix 2 neu auf Main-Loop:** Watchdog-Task von `run_bot`/Main-Loop aus, der per `asyncio.run_coroutine_threadsafe(client.disconnect(...), tiktok_loop)` bei Stille von **außerhalb** reconnectet (umgeht Loop-Blockade). Sicherheitsnetz, Symptom.
2. **Ursache senken:** verbliebene On-Loop-Handler-Last weiter auf Executor verlagern, bis sie bei `darkygame`-Flow durchläuft (jetzt reproduzierbar/verifizierbar).
3. **Alte Verbindungslogik übernehmen:** TikTok-Verbindungsstrategie der alten, funktionierenden Datei in die neue übernehmen (größter Eingriff, orientiert am Nachweis).
- **Benutzerentscheidung 2026-08-28: STOPEN, nur dokumentieren** — keine weiteren main.py-Eingriffe jetzt.

---

## 6e. ROOT CAUSE GEFUNDEN + FIXED — nested non-reentrant `ctx.like_lock` Deadlock [BEWIESEN]

2026-08-29, der Beleg in drei Stufen:

### Stufe 1: A/B-Minimal-Harnesses grenzen Ursache auf „geladene Config" ein [BEWIESEN]
Fünf neue Harness-Proben (Temp\opencode): `ab_sideB2.py` (alte Datei, minimal), `ab_sideA2.py` (neue Datei, **ohne** `load_config`), `ab_sideA4.py`/`ab_sideA6.py` (neue Datei, **volle Init ohne die 6 Async-Tasks**), alle mit identischem Connect-Code (`await asyncio.to_thread(client.run)`) und By-Type-Zähler über den TikTokLiveLogHandler:
- B2 (alt): **925** Events kontinuierlich (like=185, join=132, comment=16), never stops.
- A2 (neu, keine Config): **856** Events kontinuierlich — Handler/`create_client`/Connect-Code sind unschuldig.
- A4/A6 (neu, volle Init): **stockt nach ~35–73 Events**, Gaps ~90–126 s — egal ob die 6 Async-Tasks laufen(d) oder nicht.
- A2 ∥ A4 im selben Fenster (120 s): A2=625 flows, A4=65 dann 124 s tot → **deterministisch app-seitig, config-abhängig**.

### Stufe 2: faulthandler-Stack-Dump liefert den hängenden Thread [BEWIESEN]
`ab_sideA6.py` = A4 + `faulthandler.dump_traceback_later(4, repeat=True)`. Der Dump direkt nach dem Einfrieren (`ab7_a6_fh.log.err`) zeigt Thread 0x00000b8c:
```
main.py:1668 in _enqueue_like_triggers      ← `with ctx.like_lock:` (acquire blockiert)
main.py:2442 in on_like                     ← INNERHALB `with ctx.like_lock:` (Z. 2409)
pyee … _ws_client_loop → client.run → to_thread worker
```
→ Der TikTok-Reader-Thread hängt **permanent** im zweiten `acquire`. WebSocket bleibt offen, keine weiteren Frames gelesen, keine Acks → TikTok drosselt still → „Burst dann Stille". Kein Close, kein Reconnect — exakt das Symptom.

### Stufe 3: Zeitlinie erklärt ALLE Messungen [BEWIESEN]
- `ctx.like_lock = threading.Lock()` (main.py:207) — **nicht reentrant**.
- `on_like` (Z. 2404) hält den Lock ab Z. 2409 und ruft **innerhalb** `_enqueue_like_triggers` (Z. 2442), das denselben Lock erneut akquiriert (Z. 1668) → **Deadlock beim 2. Like-Event**.
- 1. Like: `start_likes is None` → Initial-Count → `return` VOR dem Trigger-Enqueue → kein Deadlock. → **jede** A-Full/A4/A6-Messung zeigt exakt `like=2`, dann 0 Events.
- Variierende Stalls (5/35/59/73) = Zufall, wie viele Events bis zum 2. Like im Initial-Burst ankommen.
- A2 fließt, weil `like_triggers` leer ist (kein `load_config`) → `if not rules: return` VOR dem Lock. Alte Datei (`Streaming_Tool_pub` Z. 795) hält den Lock genau **einmal** (Inline-Trigger-Loop).

### Fix (Option 2, freigegeben)
`_enqueue_like_triggers` einzig aus `on_like` unter Lock gerufen → das innere `with ctx.like_lock:` entfernt, Loop-Body dedented, Docstring dokumentiert den Lock-Vertrag („Callers must hold ctx.like_lock"). → Einzel-Lock wie in der Referenz-Datei.

### Verifikation [BEWIESEN]
- Regressionstest `TestEnqueueLikeTriggers::test_locks_not_nested_when_called_under_like_lock` (Daemon-Thread + `join(5)`; ohne Fix DEADLOCK/FAIL) — `pytest tests/test_core/test_main_bridge.py`: **103 passed**.
- Volle Suite: **2070 passed, 3 skipped** (151 s). `ruff format --check .` sauber, `ruff check` sauber.
- **Live andykister 70 s** (`bridge_debug --user andykister --duration 70 --like-every 3 --no-probe`): **36 LikeEvents** (vorher exakt 2), Comment=12, Join=14, **18 `[LIKE] Trigger`-Fires** (`likes_standard` +63, `likes_100k` +63), Events fließen bis zum Ende — **kein Stopp**.
- **Sauberer paralleler A/B (2026-08-29, andykister, 110 s, gleicher Live-Moment, `ab11_*.log`):** A4 (fix, volle Init) **548** Events (Like=103, Join=84, Comment=12, gap max 0,2 s) ∥ B2 (alt) **554** Events (Like=105, Join=83, Comment=12, gap max 1,4 s) — praktisch identische Verteilung, **kein Stopp auf beiden Seiten**. Solo-A4-Lauf (`ab10_*.log`): 693 Events / 121 s (Gaps ≤0,8 s). Hinweis: Ein erster Parallel-Anlauf (`ab9_A4_err.log`) fiel beim externen Sign-Server ab (`SIGN_NOT_200`, HTTP 500, §6c) — NICHT App-seitig; A4-Minimal-Harness hat keinen Reconnect.

> Hinweis: CSS-TikTokLive-Version lautet tatsächlich 6.6.5 (Kerncode identisch zu 6.6.6-Angaben in §2 der Doku). Die early „Loop-Model/Race"-Hypothesen (§4) sind übertroffen: Ursache war ein deterministischer Lock-Fehler, kein Scheduling-Race.

## 7. WICHTIGSTE DATEIEN / HARNESSES (für die Fortsetzung)

Alle unter `C:\Users\Finni\AppData\Local\Temp\opencode\`:

| Datei | Zweck |
|---|---|
| `ab_orch.py` | **FIXT (nutzbar):** startet A und B **parallel** (Threads), streamt Zeile-für-Zeile live, `Popen.communicate(timeout=duration+10)` + `kill()` als harte Exit-Garantie, UTF-8/`errors="replace"`-reconfigure, wertet `FINAL_EVENTS=`/`events= gap=` aus. Befehl: `python ab_orch.py --user <acct> --duration 150`. |
| `ab_a.py` | Prozess A: aktuelles `main.py` (create_client + new_loop + `_ws_stall_watchdog` + connect), reale Sinks. Nutzt `_abcount`. Beendet sauber via `os._exit(0)` nach Dauer-Kondition. |
| `ab_b.py` | Prozess B: altes `main.py`, `await asyncio.to_thread(client.run)`. Nutzt `_abcount`. **Fix:** daemon `_hard_deadline`-Thread (Dauer+5s) erzwingt `os._exit(0)` + druckt `FINAL_EVENTS` (client.run kehrt bei offener WS nie zurück). |
| `_abcount.py` | Gemeinsamer TikTokLive-`Received Event`-Zähler (zählt `Received Event`-Zeilen aus `client.py`, gibt `events=…` + `gap=…`). **FIXT:** zählt jetzt (vorher griff der `[TikTokLive]`-String-Check nie, da Formatter-Prefix); Filter = `record.name=="TikTokLive"` + `pathname.endswith("client.py")`. **`__pycache__/_abcount` vor jedem Lauf löschen!** |
| `test_loop_ab.py` | **Bewährter** sequentieller Loop-A/B in einem Prozess (82/77 Events). Netz/Queues neutralisiert. Läuft **nur in einem Prozess** — Ausgangslage für jede spätere Aufspaltung. |
| `test_b_full.py` | Treibt die **alte** main.py korrekt (Modul-Import, `MAIN_LOOP` setzen, TikTokLive-DEBUG via `CountHandler`). Wiederverwendbare Vorlage fürs alte main.py. |
| `test_stages*.py` / `test_a_inc.py` | Frühere Stufen-/Inkrement-Tests (nur zur Historie). |
| `fix_verify_andykister.log`, `test_loop_ab.log`, `test_stagesA/B/C.log`, `test_b_full2.log` | Referenz-Logs mit den Messwerten (Einzelheiten: `ANDYKISTER FLOW SCHWANKT`). |

### Logs mit Messwerten (Kurzfassung)
- **§6d (entscheidend):** `darkygame` — alte App läuft durch, neue stoppt nach Initial-Burst (5 Events → nichts). Fix 2 wirkungslos (Watchdog im blockierten Loop).
- `live_ab_run2.log`: paralleler A/B 150s andykister: A 617 / B 641 Received-Events, kein Stopp, kein Watchdog-Feuer (§6b).
- `test_loop_ab2.log`: CURRENT 82 / OLD 77 Events in je 40s, kein Stopp.
- `test_stagesB/C.log`: 2×2-Matrix, kein Stopp in 4/4 Phasen (30–41 Events, gap 0.47–4.95s).
- `test_stagesA.log`: frühere (reproduzierbare? → NICHT reproduzierbar) Stopp-Begehung: LOG/BOTH stoppte nach ~9–12 Events — als flow-abhängig eingeordnet, NICHT als deterministischer Handler-Fehler.

---

## 8. NÄCHSTE SCHRITTE — für die nachfolgende KI

### A. [ERLEDIGT §6e] Stopp-Ursache behoben — nested `ctx.like_lock`-Deadlock
Deterministische Root Cause gefunden und mit Option 2 gefixt (`_enqueue_like_triggers` innerer Lock entfernt). Verifiziert: 103 bridge-Tests, 2070 volle Suite, Live andykister 70 s (36 Like- statt 2; 18 Trigger-Fires; kein Stopp). **Ausstehend:** Long-Run-Verifikation gegen einen Konstant-Flow-Account (`darkygame`) über mehrere Minuten im vollen `run_bot` (inkl. der 6 Async-Tasks + Reconnect), da die Minimal-Harness A4 ohne Tasks lief.

### B. Warum die bisherige Verifikation den Stopp nicht zuverlässig traf
- Der Stopp tritt **immer beim 2. Like-Event** ein (nicht flow-abhängig, sondern strict deterministisch sobald `like_triggers` geladen sind). Frühere Tests ohne geladene Config oder ohne echten 2. Like konnten ihn nie treffen — das erklärt alle „kein Stopp"-Läufe (§6b/§6c/§3.3).
- `andykister`'s Flow schwankt stark; für künftige Live-Tests `darkygame` (bzw. einen Account mit konstant hohem Flow) nutzen.
- **429-Risiko**: TikTok ratelimed uns bei zu vielen blinden Verbindungen. Spärlich und zielgerichtet testen; nach einem 429 eine Pause (>1–2 min) einlegen.

### C. Watchdog-Auto-Heal — **mangels Ursache irrelevant geworden, aber als Sicherheitsnetz wertvoll**
Fix 2 (Watchdog) ist **entfernt** — die Ursache ist behoben. Falls in Zukunft wieder Stille auftritt: Watchdog von außen (Main-Loop) per `asyncio.run_coroutine_threadsafe(client.disconnect(...), ctx.tiktok_client_loop)` reconnecten als Symptom-Netz.

### D. Löschbar/Hinweise
- `ab_sideA2/B2/A4/A5/A6.py`-Harnesses + `ab2_*`–`ab8_*`-Logs in Temp\opencode dokumentieren den Beweisweg (§6e); können nach Long-Run-Verifikation verworfen werden.
- `bridge_debug.py`-Webhook-Proben (`urllib.error`, ECONNREFUSED) sind unkritisch, wenn kein API-Server läuft.

---

## 9. Kontakt-/Kontext-Regeln (AGENTS.md-Kurzabgleich)

- `src/python/main.py` ist die **sensitivste Datei** — Änderungen minimal und getestet.
- **Fix-Umsetzung wurde vom Benutzer ausdrücklich freigegeben** (Fix 1 + Fix 2 + Loop-A/B gewählt). Für weitere Eingriffe in Live-Verhalten wieder fragen.
- `tools/bridge_debug.py` = Debug-Launcher für echte main.py in einer Sandbox (Marker `[TIKTOK][RAW]`, `[TIKTOK][WATCHDOG]`; Webhook-Proben gegen einen nicht laufenden API-Server können `urllib.error`-Meldungen zeigen — unkritisch).
- Versionen nur in `src/core/version.py`; die Fixes berühren `main.py`, den Regressionstest (`tests/test_core/test_main_bridge.py`) und diese Doku — sonst kein Repo-Artefakt.
- **Status:** Fix 1+2 + Loop-Port + **Deadlock-Fix (§6e)** liegen UNCOMMITTED auf `v1.0.0-dev` (Stand: 2070 passed, Live-Verifikation erfolgt). Frühere Commits: `96131fa` (fix-bridge), `a7fe15e` (docs). `src/data/` (Runtime-Backups) bleibt untracked. Commits/Push nur auf ausdrücklichen Wunsch.
