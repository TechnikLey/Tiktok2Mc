# AI Handover — TikTok2Mc: "Bridge stoppt nach Initial-Burst" (Live-Event-Problem)

> Erstellt: 2026-08-28 — Zweck: Eine andere KI soll die Arbeit nahtlos fortsetzen können.
> Aktualisiert: 2026-08-28 (Live-A/B §6b): Harness gefixt, A lief kontinuierlich durch, Stopp nicht reproduziert.
> Alle Aussagen sind strikt nach dem Prinzip **"Nicht raten"** klassifiziert: `[BEWIESEN]` = per Code + Test belegt, `[HYPOTHESE]` = plausibel, aber nicht hart reproduziert, `[OFFEN]` = noch zu klären.

---

## 1. Problemstellung (Kurz)

Der **aktuelle** Bridge (`D:\Tiktok2Mc\src\python\main.py`, TikTokLive 6.6.5) liefert nach dem Initial-Burst (nach ~6–8s und ~5–10 Events) **keine weiteren Live-Events** — die Tier-Websocket ist offen, der Stream läuft, aber es kommen keine Events mehr. Die **alte** main.py (`D:\Streaming_Tool_pub\src\python\main.py`) lief kontinuierlich durch.

---

## 2. Repository-/Kontext-Lage

- **Aktueller Bridge (A):** `D:\Tiktok2Mc\src\python\main.py` — 81168 Bytes, ~3055 Zeilen. Modell: `ctx = BotContext()` (Modul-global), `create_client(user)` Zeile 2323, `_ws_stall_watchdog` Zeile 2302 (nested), `run_bot` Zeile 2901, **`_run_client_blocking` ist NESTED in `run_bot` (Zeile 3025), NICHT Modul-Ebene** — wichtig für jede weitere Test-Harness.
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

### 3.4 Fix 1+2 und 1690 pytest-Tests [BEWIESEN]
- Fix 1 (On-Loop-Arbeit minimieren) + Fix 2 (Watchdog-Auto-Heal) sind implementiert und statisch verifiziert (siehe §5).
- `ruff format` + `ruff check`: sauber (0 Findings).
- `pytest tests/test_core/`: **1690 passed, 1 skipped** (inkl. `test_main_bridge.py` = 102 passed).
- `bridge_debug --user andykister --duration 120`: verbunden, Events, keine fatal flags, kein Watchdog-Feuer, kein Crash — **aber** `andykister` hatte in diesem Fenster nur ~6 Events (niedriger Flow → kein Stress auf die Race).

---

## 4. HYPOTHESE — Die plausibelste (und einzige) Erklärung, die zum Code passt

**Timing-Race auf der Event-Loop der TikTokLive-Library (NICHT Loop-Isolation):**
- Reader, per-Frame-**Ack** (`ws_client.py:263-264`) und **`hb`-Heartbeat** (`_ping_loop_fn`, gleicher Loop) teilen **eine** asyncio-Loop.
- **Wichtig (Architektur-Klärung):** Diese Loop-Architektur ist bei **alt (B) und neu (A) identisch** — `TikTokLiveClient.run()` ≡ `_asyncio_loop.run_until_complete(connect())` (`client.py:226`; `_asyncio_loop` = `get_running_loop()`/sonst `new_event_loop()` `client.py:519-522`). B (`to_thread(client.run)`) und A (`to_thread(_run_client_blocking)` mit eigenem `new_event_loop`) lassen den TikTok-Client jeweils in **genau einer** Loop laufen. Es gibt also **keinen** alten Modus, der Reader/Ack/hb auf getrennte Loops verteilt hätte. Der Unterschied ist nicht "Loop-Isolation", sondern die **Menge synchroner Arbeit, die die Event-Handler im Aufruf-Kontext dieser einen Loop verrichten** (der neue, reichere Bridge hat mehr Checks/Queues/HTTP-Sinks pro Event als der spartanische alte).
- Bei hohem Event-Flow hält die **synchrone On-Loop-Handler-Arbeit** die Loop so lange besetzt (`hb` wird zu spät bedient), dass TikTok den Client **leise drosselt** — ohne Close-Frame; der Reader steht still. Genau das adressiert Fix 1 (On-Loop-Arbeit minimieren).
- Untermauert durch: TikTok sendet **keine Pongs** (Kommentar `ws_client.py:191`); isolierte Durchläufe (wenig Arbeit) laufen durch, reale Lows-Flow-Läufe mit wenig Arbeit ebenfalls, aber unter Stress stoppt es. [Konsistent mit §6b: moderater Flow → kein Stopp bei A noch B.]

**Einschränkung [OFFEN]:** Der **endgültige Beweis** (hochflow-Live-Lauf der behobenen Version: läuft durch bzw. Watchdog heilt statt zu stehen) steht noch aus.

---

## 5. UMSETZUNG — Fix 1 + Fix 2 in `src/python/main.py`

### Fix 1 — On-Loop-Handler-Arbeit minimieren
- Per-Like-`[LIKE DEBUG]`-Diagnostik von `log.info` auf `log.debug` demoted:
  - `_enqueue_like_triggers` (Zeilen ~1659–1703): alle `[LIKE DEBUG]`-Zeilen (4×).
  - `on_like` (Zeilen ~2422–2472): `[LIKE DEBUG]`-Zeilen (4×) auf `log.debug`.
- `on_comment`: `event.user` wird **einmal pro Event** gelöst (`user = event.user` in try/except → `None` bei Fehler) und für die Fan-/Moderator-Checks wiederverwendet (`_ua(name, default)`-Helper) statt 4–5× `user_attr_safe(event, ...)` — jeder `event.user`-Zugriff ist eine Property, die `ExtendedUser.from_user` re-runt und bei unbekannten Proto-Feldern (z.B. `nickName`) werfen kann.

### Fix 2 — Auto-Heal im Watchdog
`_ws_stall_watchdog` ruft bei Erkennung (idle > 60s while live) jetzt zusätzlich zu `log.warning`:
```python
client = ctx.tiktok_client
if client is not None:
    try:
        await client.disconnect(close_client=False)
    except Exception:
        log.warning(...)
```
Wirkung: schließt die WS → `client.connect()` kehrt zurück → `_run_client_blocking` endet → (im echten Lauf `run_bot`) verbindet mit **frischer signierter URL** neu. Signierte URLs laufen ~30s ab, daher ist ein komplettes neues `connect()` sicherer als ein blinder Reconnect-Loop.

### Verifiziert
- `disconnect()` (`client.py:228`) schließt WS und awaited `_event_loop_task` → `connect()` kehrt zurück — Code gelesen.
- `ast.parse`-Syntax-Check OK; `ruff format` angewendet; `ruff check` 0 Findings.
- 1690 pytest-Tests pass.

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
- `live_ab_run2.log`: **NEU** — paralleler A/B 150s andykister: A 617 / B 641 Received-Events, kein Stopp, kein Watchdog-Feuer (§6b).
- `test_loop_ab2.log`: CURRENT 82 / OLD 77 Events in je 40s, kein Stopp.
- `test_stagesB/C.log`: 2×2-Matrix, kein Stopp in 4/4 Phasen (30–41 Events, gap 0.47–4.95s).
- `test_stagesA.log`: frühere (reproduzierbare? → NICHT reproduzierbar) Stopp-Begehung: LOG/BOTH stoppte nach ~9–12 Events — als flow-abhängig eingeordnet, NICHT als deterministischer Handler-Fehler.

---

## 8. NÄCHSTE SCHRITTE — für die nachfolgende KI

### A. [PRIO-1] Funktionsfähigen parallelen A/B — **ERLEDIGT (Lauf §6b)**
Die Harness (`ab_orch.py` + `ab_b.py`-Deadline + `_abcount`-Fix) funktioniert jetzt und lief erfolgreich (617/641, kein Stopp). **Was offen bleibt:** der Stopp wurde in keinem Fenster reproduziert, also steht der definitive Beweis (Stopp beobachtet ≤> Fix heilt) weiter aus. Für einen solchen Lauf: frischen `__pycache__/` löschen, sehr aktiven Account, dann `python ab_orch.py --user <acct> --duration <s>`.
1. **Stream-Ausgabe live** statt End-Puffer — erledigt.
2. **Exit-Garantie** — erledigt (ab_a `os._exit`; ab_b daemon-Deadline; Orchestrator `communicate(timeout)`+`kill`).
3. Metrik: `FINAL_EVENTS=…` + `events=… gap=…s` — erledigt (Zähler-Fix, §6b).
4. **Beide gleichzeitig starten** — erledigt (Threads, gleicher Live-Moment).

### B. Warum die bisherige Verifikation den Stopp nicht zuverlässig traf
- `andykister`'s Flow schwankt stark. Für einen gescheiten A/B braucht es einen Account, der **gerade live ist und konstant hohen Flow** (viele Likes/Comments/Sekunde) liefert. Vom Benutzer fragen, ob er einen solchen aktuell kennt (vorher wurde behauptet "der hat ständig flow", aber im Testfenster war kaum Flow).
- **429-Risiko**: TikTok ratelimed uns bei zu vielen blinden Verbindungen. Spärlich und zielgerichtet testen; nach einem 429 eine Pause (>1–2 min) einlegen.

### C. Zusätzliche, sinnvolle Maßnahme (falls Live-Test zu sporadisch)
- Fix 2 (Watchdog-Auto-Heal) machbar **auch ohne den Race zu reproduzieren**: den behobenen Bridge dauerhaft gegen den Ziel-Account laufen lassen; wenn er je stillsteht, verbindet der Watchdog automatisch neu statt stehenzubleiben. Das ist der operative Nutzen von Fix 2 parallel zur verbleibenden empirischen Bestätigung.

### D. Verifikation der Fix-1-Debug-Demotions
- Unter normalen Bedingungen (ohne `TIKTOK2MC_DEBUG`) dürfen **keine `[LIKE DEBUG]`-Zeilen** mehr auf INFO-Ebene erscheinen; unter `TIKTOK2MC_DEBUG=1` sollen sie weiterhin (auf DEBUG) erscheinen. In einem Live-Lauf einmal gegenprüfen (Bridge-Log bzw. Handler-Verhalten).

---

## 9. Kontakt-/Kontext-Regeln (AGENTS.md-Kurzabgleich)

- `src/python/main.py` ist die **sensitivste Datei** — Änderungen minimal und getestet.
- **Fix-Umsetzung wurde vom Benutzer ausdrücklich freigegeben** (Fix 1 + Fix 2 + Loop-A/B gewählt). Für weitere Eingriffe in Live-Verhalten wieder fragen.
- `tools/bridge_debug.py` = Debug-Launcher für echte main.py in einer Sandbox (Marker `[TIKTOK][RAW]`, `[TIKTOK][WATCHDOG]`; Webhook-Proben gegen einen nicht laufenden API-Server können `urllib.error`-Meldungen zeigen — unkritisch).
- Versionen nur in `src/core/version.py`; der Stopp/die Fixes berühren **kein** Repo-Artefakt außer `main.py`.
- **Nicht committet:** Der Git-Stand ist sauber (`git diff` = nur `src/python/main.py`, +43/−14, Fix 1+2). Nur committen, wenn der Benutzer es verlangt.
