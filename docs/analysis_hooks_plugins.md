# Analyse: Hook-System & Plugin-System in TikTok2Mc

> **Status:** Analysepapier (Stand: August 2026) — reine Dokumentation, keine Implementierung.
> **Methodik:** Alle Aussagen am Quellcode verifiziert (`src/core/*`, `src/python/main.py`, `src/core/api/routes/*`); Abweichungen zur Dev-Doku sind explizit markiert.
> **Bewertungsskala für Ideen:** „Ja" · „Ja, mit kleineren Erweiterungen" · „Nur mit strukturellen Änderungen" · „Aktuell nicht sinnvoll möglich"

---

## A) Systemüberblick (verifiziert)

TikTok2Mc ist eine Multi-Prozess-Anwendung:

| Prozess | Start | Rolle |
|---|---|---|
| **Supervisor** | `start.exe` → `src/python/start.py` | Hostet die FastAPI **im eigenen Prozess** (uvicorn-Task, Port 29185), startet Bridge/GUI/Plugins als `subprocess.Popen`, überwacht Signal-Dateien in `core/runtime/` |
| **Bridge** | Subprozess (`main.py`) | TikTokLive-Verbindung, Trigger-Engine-Aufrufe, RCON-Worker, Hook-Loader, Flask-Webhook (Port ~29188) |
| **API-Server** | im Supervisor-Prozess | EventBus, CommandQueue, Event-Command-Mapper (ECM), Plugin-Registry/Watcher, Overlays, SSE/WebSocket fürs GUI |
| **Plugins** | eigene Subprozesse | Kommunizieren **ausschließlich per HTTP** mit der API |
| **Hooks** | **kein eigener Prozess** | Werden beim Bridge-Start in den Bridge-Prozess geladen |

Zentrale Konsequenz dieses Designs: `event_bus` und `command_queue` (`core.api.eventbus` bzw. `core.api.plugin_overlay`) existieren **pro Prozess je einmal**. Alles, was der Bridge-Prozess lokal aufruft, erreicht den API-Prozess nicht — und umgekehrt. Das ist der rote Faden mehrerer kritischer Befunde (Abschnitt E).

---

## B) Hook-System — kritische Analyse

### B.1 Funktionsweise
- Discovery über `src/hooks/*/hook.json` sowie mit Plugins gebündelte Hooks; AST-Statische Prüfung der Imports (`core.hook_loader.ALLOWED_IMPORTS`): **nur** `time`, `random`, `logging`, `json`, `urllib`, `requests` plus `core.hook_api` / `core.plugin_config`.
- Ein Hook implementiert `register(api: HookAPI)` und registriert benannte Actions: `api.register_action(name, fn)`. Diese landen im globalen Dict `HOOK_ACTIONS` (erstes Registrieren gewinnt, kein Unregister).
- Ausführung: Eine Zeile `trigger:$mein_hook` in `data/actions.mca` ruft die Action synchron (via `asyncio.to_thread`) während des Trigger-Dispatch auf.
- Handler-Signatur: `(user, trigger, context)` — **`context` wird von `main.py` immer als leeres `{}` übergeben.** Strukturierte Ereignisdaten (Giftname, Anzahl, Combo-Flags, Rollen) sind nicht verfügbar. Einzige Ausnahme: Beim Kommentar-Trigger ist `user` ein Dict `{user, comment}` — der Kommentartext ist also indirekt erreichbar.
- Verfügbare Fähigkeiten via `HookAPI`: `rcon_enqueue`, `enqueue_trigger` (max. Ketten­tiefe 3, Banliste für `tiktok`/`connect`/`disconnect`), `send_overlay_text` (HTTP), `log`, Config-Kopie (`get_hook_config`, `config`), `get_valid_functions`.

### B.2 Stärken
1. **Geringste Latenz aller Erweiterungsarten:** in-process, kein HTTP-Hop, direkt im Trigger-Pfad.
2. **Robust isoliert:** Handler laufen im Executor-Thread; Exceptions werden vom CrashManager gemeldet, ohne die Bridge zu töten.
3. **Kleine, prüfbare Angriffsfläche:** Import-Whitelist + Manifest (`min_api_version`, `depends_on` vorhanden).
4. **Vollzugriff auf die Kernaktionen**, die auch `.mca`-Zeilen haben (`enqueue_trigger` = beliebige weitere Triggerketten).

### B.3 Schwächen / harte Grenzen
1. **Kein Veto:** Rückgabewerte des Handlers werden ignoriert; ein Hook kann einen bereits dispatchten Trigger **nicht abbrechen** oder filtern. Skript-Actions laufen zwar vor dem Enqueue der RCON-/Vanilla-Befehle, aber es gibt keinen Vertrag „False = Kette abbrechen".
2. **Kein Ereigniszugang:** Hooks können nur durch `$`-Zeilen in `actions.mca` feuern. Es gibt kein `subscribe(event)` — Reaktion auf `tiktok.gift` & Co. nur über den Umweg einer `.mca`-Zeile.
3. **Kein Lifecycle:** Keine Callbacks für Stream-Start/-Ende, keine Timer/Hintergrundtasks, keine Initialisierung mit garantiertem Aufrufkontext jenseits von `register()`.
4. **Kein Runtime-Reload:** Aktivieren/Deaktivieren erfordert Bridge-Neustart (auch laut `routes/hooks.py`). Die Reload-Signal-Dateien decken nur config/actions/comment_commands/chatbot ab — **nicht Hooks**.
5. **Whitelist schneidet legitime Anwendungsfälle ab:** keine `os`/`subprocess`/Audio-/DB-Libs. Gleichzeitig erlaubt `requests` vollen Netzwerkzugriff aus dem Bridge-Prozess — das Sicherheitsversprechen ist also asymmetrisch (Prozess isolation fehlt komplett).
6. **Keine Zustands-/Persistenzdienste:** Datei-I/O nur über die Whitelist-Module selbst organisiert (json + eigene Pfade).
7. **Kein Publish:** Ein Hook kann nichts auf den EventBus legen; Kommunikation mit Plugins wäre nur über den undokumentierten Direktaufruf der REST-API per `requests` möglich.

**Fazit Hook-System:** Als schneller, einfacher Aktions-Erweiterungspunkt gut gelungen; als *Ereignis*-Erweiterungsebene ungeeignet (keine Events, kein Kontext, kein Veto). Die Doku positioniert Hooks korrekt als „Aktionen statt Reaktionen".

---

## C) Plugin-System — kritische Analyse

### C.1 Funktionsweise
- Subprozess pro Plugin, gesteuert über Signal-Dateien `core/runtime/plugin_{action}_{name}`; Registry persistiert in `data/api_plugin_registry.json`; Watcher pollt alle 10 s auf neue Verzeichnisse.
- `BasePlugin` bietet: `PLUGIN_NAME`, Pflicht-Override `get_overlay_html()`, Schema-getriebene Config (`config_schema` in `plugin.json` → GUI-Editor), thread-safe `state`/`push_state()` (SSE an Overlay-Seite), Command-Long-Poll (`GET /plugins/{name}/commands?wait=1`), Tick-Thread (1 s), Heartbeat (30 s), `api_post`/`api_get` Helfer.
- Manifest-Felder: `capabilities`, `depends_on` (Topo-Sort beim Launch), `event_subscriptions`, `emitted_events`, `accepted_commands` (GUI-Reaktionskatalog), Plattform-/Update-Metadaten.
- Ereignispfad 2 (funktional): ECM liest `defaults/event_commands.yaml` + `data/event_commands.yaml` und mappt **API-Bus**-Events auf Plugin-Kommandos.
- Kommentar→Plugin: ausschließlich über Gruppen in `data/comment_commands.yaml` (`handler: plugin`, `plugin_name`, Präfix **muss nicht-leer sein**, Befehls-Whitelist, Rollenfilter, Cooldowns).

### C.2 Stärken
1. **Sauberste Isolation im Projekt:** eigener Prozess, Sandbox-Ressourcenlimits vorhanden (Standard: aus), Crash eines Plugins berührt Bridge/API nicht.
2. **Reifes Fundament:** Registry + Health-Monitor + Heartbeats, Dependency-Auflösung, schema-validierte Konfiguration mit GUI, Overlay-Kanal mit State-SSE, Token-Verschlüsselung via `secure_storage` (vom Spotify-Plugin vorgemacht).
3. **Volle Python-Freiheit im Plugin:** alle Bibliotheken nutzbar (Spotify zeigt OAuth + externe REST-API produktiv).
4. **Long-Poll (`wait=1`)** macht die Kommando-Zustellung near-realtime trotz HTTP.
5. **Loser Kopplungsgrad über Events:** Plugins publishen eigene Events (`POST /events`), andere konsumieren sie via ECM — Timer/Deathcounter zeigen das Muster.

### C.3 Schwächen / harte Grenzen
1. **Der dokumentierte Ereignispfad 1 ist tot (kritisch, s. E.1):** `event_subscriptions` funktioniert im realen Mehrprozess-Betrieb nicht. Kein einziges ausgeliefertes Plugin nutzt ihn — das Feature ist ungetestet eingeschlossen.
2. **Kommentarfeed nicht abonnierbar:** Alle Kommentare (ohne Präfix) erreichen kein Plugin. Der dokumentierte Manifest-Switch `comment_handler` (prefix/enabled) ist **in keinem Python-Modul implementiert** — reiner Doku-/Code-Drift.
3. **Fire-and-forget überall:** `send_command` hat keine Antwortwarteschlange, keine Korrelations-IDs; Request/Response zwischen Extensions ist nicht modelliert.
4. **Keine eigenen Endpunkte:** Das REST-Interface pro Plugin ist fix (commands/overlay/stream/state/config). Eigene Abfrage-Routen („gib mir das Leaderboard") sind nicht möglich; interaktive UIs bleiben auf statisches Overlay-HTML + SSE-State beschränkt.
5. **Keine Dashboard-Integrationspunkte:** Plugins bekommen keine Tabs/Routen im Web-Dashboard — nur Overlay-Seiten und Schema-Config-Seiten.
6. **Persistenz DIY und kollisionsgefährdet:** gemeinsames `data/`-Verzeichnis, keine namespaced Storage-API.
7. **`capabilities` rein informativ:** Nirgends wird geprüft; kombiniert mit standardmäßig deaktivierter Sandbox ist das Isolationsmodell opt-in.
8. **Undokumentierte Hintertüren:** `POST /api/v1/rcon/command` (generischer RCON-Endpunkt des API-Prozesses) umgeht Queue/Throttling der Bridge — nützlich, aber weder dokumentiert noch autorisiert.

**Fazit Plugin-System:** Architektonisch die richtige Ebene für alles Schwergewichtige (Threads, Audio, OAuth, Persistenz) — aber der versprochene Ereigniseingang ist defekt, und Interaktions-/UI-Möglichkeiten enden hart an der fixen API-Oberfläche.

---

## D) Kern-Schnittstellen & Datenflüsse (verifiziert)

```
                    ┌─────────────────────────── Bridge-Prozess ───────────────────────────┐
 TikTok Live ──────►│ _handle_*_events ──► Queues ──► actions.mca / RCON / Overlay         │
                    │        │                                                             │
                    │        ├─► _publish_tiktok_event ──► [LOKALER] event_bus             │
                    │        │                                   │                         │
                    │        │                        _event_bridge_worker                 │
                    │        │                        (filtert "tiktok.*", enqueue in      │
                    │        │                         [LOKALE] command_queue!)  ✗ tot     │
                    │        └─► minecraft.*-Events ──HTTP POST──►  API-Prozess-Bus  ✓      │
                    └──────────────────────────────────────────────────────────────────────┘
                                                       │
   GUI ◄── SSE/WS ──┐                                  ▼
                    │                       [API] event_bus ──► ECM (YAML) ──► [API] command_queue
   Test-Trigger ────┘                            ▲                                  │
   (routes/triggers.py publishen direkt!)        │                                  ▼
   Plugins publishen via POST /events ───────────┘                    GET /plugins/{name}/commands?wait=1
                                                                      (Plugin-Subprozess)
```

Belegstellen: `main.py` importiert Bus/Queue als Modul-Globals (lokale Instanzen); `_publish_tiktok_event` (~L1197) published nur lokal; `_event_bridge_worker` (~L1337) enqueued lokal; `routes/triggers.py` (Test-Trigger) published dagegen **direkt auf den API-Bus**; ECM läuft im API-Prozess.

Wichtige Randnotiz: Der API-Prozess kann `actions.mca`-Trigger auslösen — über `POST /api/v1/triggers/execute` → `TriggerService` → `TriggerEngine` → HTTP-POST an den Bridge-Webhook (`/custom_trigger`, Port via `RESOLVED_PORT_WEBHOOK_PORT`, Fallback 29188). Einschränkungen: 1,5-s-Debounce (singleton, teilt sich mit dem GUI-Event-Tester!), Payload nur `user`/`gift_id`.

---

## E) Kritische Befunde & Inkonsistenzen

| # | Befund | Beleg | Wirkung |
|---|---|---|---|
| E.1 | **Cross-Process-Defekt:** `_event_bridge_worker` legt `tiktok_event`-Kommandos in die Bridge-lokale `CommandQueue`; Plugins pollen aber die Queue des API-Prozesses. | `main.py` L47/L1197/L1337 vs. `plugin_overlay.py` + `base_plugin._API_BASE` | Dokumentierter „Pfad 1" (`event_subscriptions`) liefert im Betrieb **nie** etwas aus |
| E.2 | **Echte `tiktok.*`-Events erreichen den API-Bus nie.** Nur Test-Trigger erscheinen dort (direkter Publish in `routes/triggers.py`). | grep `publish` in `main.py` vs. `routes/triggers.py` L55–57/85/116 | ECM-Mappings für `tiktok.comment` etc. feuern bei **Testkommentaren, aber nie bei echten** — tückische Inkonsistenz; GUI-Livefeed/TikTokLiveTracker sehen Realverkehr nicht |
| E.3 | **`comment_handler` dokumentiert, nicht implementiert.** | Dev-Book ch03-05/ch03-02 vs. grep in `src/**.py`: 0 Treffer | Doku verspricht Feature, das es nicht gibt |
| E.4 | Kein shipped Plugin nutzt `event_subscriptions`; keine Tests zu `_event_bridge_worker`. | grep in `src/plugins`, `tests` | Defekt blieb unbemerkt |
| E.5 | **Hook-Kontext immer `{}`**, keine strukturierten Ereignisdaten. | `main.py` (`execute_global_command(..., {})`) | Hooks können nicht datengetrieben arbeiten |
| E.6 | **Kein Veto-/Rückgabevertrag** für Hook-Actions. | `hook_api.execute_global_command` ignoriert Rückgaben | Filter/Moderation als Hook unmöglich |
| E.7 | Minecraft-Semantik im generischen Webhook: `player_death`/`player_respawn` pausieren die MC-Queue **unabhängig von der Quelle**. | Bridge `/webhook`-Handler | Fremdspiel, das gleichnamige Events sendet, verfälscht das Verhalten |
| E.8 | `capabilities` werden nicht erzwungen; Sandbox default aus; Hooks dürfen `requests`. | `sandbox.py`, `hook_loader.py` | Isolation ist deklarativ, nicht wirksam |

---

## F) Vorgabe 1: TTS zum Vorlesen von Kommentaren

### F.1 Anforderungsprofil
Alle Kommentare (Text, Nutzer, ggf. Rollen) empfangen → TTS-Engine (lokal z. B. pyttsx3/SAPI, oder Cloud) → Wiedergabe mit Warteschlange, Priorität, Cooldown, Mute-Schalter, Config-UI.

### F.2 Passende Ebene
**Plugin** — Audio-Playback blockiert, braucht eigene Threads/Queue, Persistenz und Schema-Config. Ein Hook scheidet praktisch aus: Die Import-Whitelist verbietet `pyttsx3`/Audio-Libs ebenso wie `subprocess` (lokales TTS-Programm starten).

### F.3 Wie käme das Plugin an ALLE Kommentare? (heutiger Stand)
| Weg | Bewertung |
|---|---|
| `comment_commands.yaml`-Gruppe | ❌ Präfix muss **nicht-leer** sein (`startswith`-Check) — „alle Kommentare" nicht abbildbar; Mechanismus ist für Befehle, nicht für einen Feed gedacht |
| `event_subscriptions: ["tiktok.comment"]` | ❌ tot (E.1); selbst bei Fix: Code legt den Text zwar ins Event (`comment=`-Extra), Doku behauptet das Gegenteil (Doc-Bug) |
| ECM-Mapping `tiktok.comment → tts/say` | ❌ für echte Kommentare wirkungslos (E.2); feuert nur bei GUI-Testkommentaren |
| Hook nach `comment:`-Zeile in actions.mca | ⚠️ Text wäre via `user`-Dict erreichbar, aber TTS technisch whiteliste-bedingt unmöglich (B.3.5) |
| Core anpassen (Bridge published tiktok.* per HTTP wie minecraft.*) | ✅ der saubere Weg; Muster existiert bereits für `minecraft.*`-Events |

### F.4 Urteil
**„Nur mit strukturellen Änderungen"** — nicht wegen TTS selbst (trivial als Plugin), sondern weil der Kommentar-*Eingang* fehlt bzw. defekt ist. Mit Reparatur von E.1/E.2 (ein Fix, zwei Probleme) wird daraus **„Ja"**: Plugin mit `requests`-Poll? Nein — mit ECM-Mapping oder gefixtem `event_subscriptions`, danach ist die TTS-Logik reines Plugin-DIY (Queue, Cooldowns, Engine-Wahl).

**Wiederverwendbarer Baustein:** die prozessübergreifende Event-Zustellung (siehe J, Pflicht #1) — profitieren würde *jede* ereignisgetriebene Erweiterung (Soundboard, Leaderboard, Statistiken, …).

---

## G) Vorgabe 2: Spiele-Integration ohne RCON

### G.1 Inbound (Spiel → TikTok2Mc)
| Kanal | Funktioniert? | Probleme |
|---|---|---|
| Bridge `/webhook` (`minecraft.{event}` → API-Bus → ECM → Plugins) | ✅ heute | Namen sind Minecraft-brandet; E.7: `player_death` pausiert die echte MC-Queue — Namenskollision mit Seiteneffekten; separates Auth-/Port-Thema |
| Bridge `/custom_trigger` | ✅ heute | Führt nur **vordefinierte** actions.mca-Trigger aus; Payload nur `user`-String; keine strukturierten Daten; undokumentierter Port |
| API `POST /events` | ✅ heute | Erreicht Plugins (via ECM), aber **nie actions.mca** — der Bus liegt im anderen Prozess als die Trigger-Queues |
| API `POST /triggers/execute` | ✅ heute | 1,5-s-Debounce (Singleton, geteilt mit GUI-Tester), nur `user`/`gift_id`, semantisch ein Testendpunkt |

### G.2 Outbound (TikTok2Mc → Spiel)
- `&`-Shell-Zeilen: Prozess-Spawn pro Trigger, kein Protokoll, kein Lifecycle.
- `$`-Hook/Skript oder Plugin mit `requests`/Websockets: technisch frei, aber **alles DIY** — Reconnect, Auth, Health, Retry, Circuit-Breaker. Ein wiederverwendbares Muster (Circuit-Breaker) existiert intern nur im Overlay-Manager.

### G.3 Urteil
**Einzelintegration als Plugin: „Ja, mit Einschränkungen"** (Transport komplett DIY, Inbound nur über Minecraft-branded Webhook mit Kollisionsrisiko).
**Eine generische „Game-Connector"-Architektur: „Nur mit strukturellen Änderungen":** es fehlen (a) ein typisierter, generischer Inbound, der sowohl Bus **als auch** Trigger-Engine speist, (b) die Entkopplung der Minecraft-Spezialfälle vom Webhook, (c) ein Outbound-Kanal-Konzept (konfigurierbare Ziele inkl. Retry/Breaker).

**Wiederverwendbare Bausteine:** generischer Inbound-Endpoint + Outbound-Channels (J, sinnvoll #6/#7) — identisch nützlich für Discord-Notifier, Home-Assistant, OBS-Steuerung usw.

---

## H) Eigene Hook-Ideen (bewertet)

### H.1 Anti-Spam-/Rate-Limit-Gate (Veto-Hook)
- **Idee:** Hook registriert `$gate_<trigger>` als erste Zeile jeder Kette; zählt Events pro Nutzer/Fenster und soll bei Überschreitung die Restkette verwerfen.
- **Technik:** in-process State, `time`/`random` aus Whitelist — Zähllogik trivial.
- **Blocker:** kein Veto-Vertrag (E.6). Zählen ja, **verwerfen nein**.
- **Urteil: „Nur mit strukturellen Änderungen"** (aber minimal: definierte Semantik für Handler-Rückgabe `False` = Restkette abbrechen).
- **Fehlende Bausteine:** Veto-Vertrag; optional strukturierter Action-Kontext (Konfiguration per `context` statt globaler Hook-Config).

### H.2 Schimpfwort-Moderator für Kommentarzeilen
- **Idee:** `$profanity_check` vor Kommentar-Reaktionen; soll unangebrachte Kommentare von allen Folgeaktionen ausschließen.
- **Technik:** Text erreichbar (H-Kontext-Exception bei `comment:`-Triggern, `user["comment"]`), Regex-Listen in hook.json-Config ladbar.
- **Blocker:** derselbe Veto-Blocker; zusätzlich bräuchten Moderationsentscheidungen strukturierten Kontext (Rollen-Flags liegen im `user`-Dict nur für Kommentare, sonst nirgends).
- **Urteil: „Nur mit strukturellen Änderungen"** (Veto + Kommentar-Datenvertrag).
- **Wiederverwendbarkeit:** hoch — Veto + Kontext ermöglichen auch Permission-Gates und A/B-Filter.

### H.3 Gift-Combo-Detektor (Milestone-in-Fenster)
- **Idee:** Erkennt „X gleiche Gifts in Y Sekunden durch Nutzer Z" und stößt Bonus-Trigger an.
- **Technik:** Zeitfenster-Logik ideal für in-process Hook; Auslösen per `enqueue_trigger` vorhanden.
- **Blocker:** Hook sieht **keine** Giftmetadaten (Name, Anzahl, `repeat_end`-Flag) — `context={}`, `user`=String (E.5). Kombos sind ohne Eingabedaten nicht erkennbar.
- **Urteil: „Aktuell nicht sinnvoll möglich"** als Hook; nach Einführung eines strukturierten Action-Kontexts: „Ja".
- **Lehrstück:** zeigt exemplarisch, dass dem Hook-System der **Datenvertrag** fehlt, nicht die Rechenlogik.

---

## I) Eigene Plugin-Ideen (bewertet)

### I.1 Discord/Webhook-Notifier
- **Idee:** Mappt Bus-Events (Follows, Milestones, Serverstatus) auf Discord-Webhooks; Template-Nachrichten, Rate-Limit, kanalbezogene Routen.
- **Heute möglich:** Für alles auf dem API-Bus **ja** — ECM-Mapping + `requests`, Muster wie Timer/Deathcounter; Tokens via `secure_storage`.
- **Blocker:** echte `tiktok.*`-Events fehlen (E.2) — Follow/Gift-Benachrichtigungen gehen nicht.
- **Urteil: „Ja, mit Einschränkungen"** (nach E.1/E.2-Fix: uneingeschränkt „Ja").
- **Fehlende Bausteine:** Event-Fix (Pflicht); QOL: generischer Notification-Dispatcher, damit Overlay/Sound/Discord eine gemeinsame Sende-Infrastruktur nutzen.

### I.2 Scheduler/Cron für actions.mca
- **Idee:** Zeitgesteuerte Trigger („alle 30 min `bonus_drop`", tägliche Reset-Aktionen) mit Cron-Syntax in plugin.yaml.
- **Heute möglich:** Überraschend weit — `POST /api/v1/triggers/execute` → `TriggerEngine` → Bridge ist die existierende, korrekte Röhre zu actions.mca.
- **Caveats:** 1,5-s-Debounce des geteilten Singletons (kollidiert mit GUI-Event-Tester), Payload nur `user`/`gift_id`, Endpunkt semantisch „Test".
- **Urteil: „Ja, mit kleineren Erweiterungen"** (dedizierter Service/Endpoint ohne Debounce, saubere Payload-Felder — kleine, risikoarme Änderung an bestehender Architektur).
- **Wiederverwendbarkeit:** sehr hoch — Basis für jede automatisierte Ablaufsteuerung.

### I.3 Viewer-Leaderboard mit Persistenz
- **Idea:** Aggregiert Gifts/Follows/Kommentarpunkte pro Viewer, SQLite/JSON, Overlay-Top-10, saisonale Resets.
- **Blocker-Kette:** (1) echte Gift/Follow-Events erreichen kein Plugin (E.1/E.2); (2) Persistenz DIY im geteilten `data/`; (3) Abfragen/Sortierungen können nicht serverseitig beantwortet werden — keine eigenen REST-Routen; Overlay-HTML bleibt statisch+SSE; Dashboard-Tab unmöglich.
- **Urteil: „Nur mit strukturellen Änderungen"** (Event-Fix + namespaced Storage + irgendein Query/UI-Punkt).
- **Lehrstück:** demonstriert drei fehlende Bausteine gleichzeitig — deshalb als Idea bewusst drin.

---

## J) Noch fehlende Bausteine für zukünftige Flexibilität

### J.1 Zwingend erforderlich (Pflicht — Defekte/blockierend)
1. **Prozessübergreifende Ereignisweiterleitung Bridge → API:** echte `tiktok.*`-Events auf den API-Bus publishen (HTTP-POST wie bei `minecraft.*` — Muster existiert) **oder** `CommandQueue.enqueue` im Bridge-Prozess per HTTP an die API-Queue proxen. Repariert zugleich den toten `event_subscriptions`-Pfad (E.1+E.2 in einem Zug).
2. **Entscheidung zu `comment_handler`:** implementieren oder aus Doku/Manifest entfernen (E.3). Bis dahin ist „Plugin erhält alle Kommentare" unerreichbar.
3. **Tests für die Ereigniszustellung:** mindestens ein Integrationstest, der ein echtes `tiktok.comment` bis zum Plugin-Kommando verfolgt (E.4 — genau deshalb blieb E.1 unbemerkt).

### J.2 Sinnvoll (hoher Nutzen für mehrere Ideen)
4. **Veto-/Rückgabevertrag für Hook-Actions** (+ strukturierter `context` statt `{}`): ermöglicht H.1, H.2, Permission-Gates, Filterketten.
5. **Hook-Runtime-Reload/Lifecycle:** Enable/Disable ohne Bridge-Restart (Reload-Signal-Mechanik erweitern); `on_live_start/end`-Callbacks.
6. **Generischer Outbound-Kanal:** konfigurierbare HTTP/WS-Ziele mit Retry/Circuit-Breaker (Overlay-Muster generalisieren) — Grundlage für G.3, I.1 und alle externen Integrationen.
7. **Trigger-Zugriff für Erweiterungen:** dedizierter Service/Endpoint auf `TriggerEngine` ohne GUI-Debounce, mit definiertem Payload — Grundlage für I.2.
8. **Request/Response zwischen Extensions:** Korrelations-IDs/Antwortqueue statt reinem Fire-and-forget.
9. **Namespaced Persistenz-API** pro Plugin/Hook (statt geteilter `data/`).
10. **Capability-Enforcement:** `capabilities` prüfen oder streichen; Sandbox-Profile; Hook-Netzzugriff bewusst entscheiden (B.3.5/E.8).

### J.3 Nice-to-have (QOL+)
11. Dashboard-UI-Erweiterungspunkte (Tabs/Routen für Plugins) — löst I.3s UI-Anteil.
12. Einheitliches Event-Schema/-Katalog mit Versionierung; `emitted_events`/`accepted_commands` für Delivery statt nur GUI-Katalog nutzen.
13. Notification-Dispatcher (Overlay/Sound/TTS/Discord als austauschbare Kanäle).
14. Generisches Event-Abo über **alle** Quellen (heute: `event_subscriptions` nur für `tiktok.*`, sonst zwingend zentrale ECM-YAML-Handpflege).

---

## K) Fazit

Die Zwei-Ebenen-Architektur ist im Kern **richtig und durchdacht**: Hooks für schnelle Aktionen im Trigger-Pfad, Plugins für alles Schwergewichtige in Isolation. Das Fundament (Registry, Manifeste, Schema-Config, Health-Monitor, TriggerEngine als Single Source of Truth, secure_storage) ist solide und wiederverwendbar.

Was die versprochene Flexibilität aktuell **ausbremst**, sind keine Designfehler, sondern:
1. **Zwei Zustellungsdefekte** (E.1/E.2), die die dokumentierte Ereignisfähigkeit faktisch abschalten — mit einem Fix adressierbar;
2. **fehlende Verträge** (Veto, Kontext, Request/Response, Persistenz, Outbound), die jede ernsthaftere Idee in DIY-Treibhausarbeit treiben (F, G, H, I belegen das einzeln);
3. **Doku-/Code-Drift** (`comment_handler`, tote Pfade), die Vertrauen in die Erweiterungsversprechen untergräbt.

**Empfohlene Reihenfolge:** J.1 (Pflicht-Fixes, klein & hoher Hebel) → J.2 Nr. 4/7 (Veto + Trigger-Zugriff; unlocken H.1/H.2/I.2 sofort) → J.2 Nr. 6/9 (Outbound + Persistenz; unlocken G/I.1/I.3) → J.3 nach Bedarf.
