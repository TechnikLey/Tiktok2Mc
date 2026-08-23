# Analyse: Hook-System & Plugin-System in TikTok2Mc

> **Status:** Analysepapier mit **Umsetzungsstand** (Stand: August 2026).
> Die Original-Analyse ist vollständig erhalten; gelöste Befunde sind mit **[✅ ERLEDIGT]** bzw. **[TEILWEISE]** markiert, veränderte Urteile wurden aktualisiert.
> **Methodik:** Alle Aussagen am Quellcode verifiziert (`src/core/*`, `src/python/main.py`, `src/core/api/routes/*`); Abweichungen zur Dev-Doku sind explizit markiert.
> **Bewertungsskala für Ideen:** „Ja" · „Ja, mit kleineren Erweiterungen" · „Nur mit strukturellen Änderungen" · „Aktuell nicht sinnvoll möglich"
>
> **Umsetzungsstand (seit Original-Analyse):**
>
> | Commit | Baustein | Repariert |
> |---|---|---|
> | `f409595` | **PluginEventBridge** (`src/core/api/plugin_event_bridge.py`) | E.1 + E.2: echte `tiktok.*`-Events werden vom Bridge per HTTP auf den API-Bus weitergeleitet und als Kommandos an abonnierende Plugins zugestellt |
> | `f409595` | **`comment_handler` implementiert** (Manifest-Feld `comment_handler: {prefix, enabled}`) | E.3: Plugins können alle Kommentare (präfixfrei) empfangen |
> | `54fdb78` | **Veto-Vertrag** für Hook-Actions (`False` = Restkette abbrechen) + Integrationstest echte Zustellung | E.6, J.1 #3 |
> | `8ea4109` | **`POST /api/v1/triggers/dispatch`** — programmatische Trigger ohne GUI-Debounce | Grundlage I.2 |
> | `022fe7a` | **Namespaced Persistenz-API** (`data/plugin_data/<name>.json` + REST + `BasePlugin.store_*`) | Grundlage I.3 |
> | *(aktuell)* | **Strukturierter Hook-Kontext**: Event-Quellen bauen `_make_hook_context(...)` (gift/follow/like/comment/join/share/webhook/hook), Trigger-Queue trägt 4-Tupel mit Context, `execute_global_command(context)` reicht ihn an Hook-Actions weiter (+ `chain_depth`); `enqueue_trigger(context=...)` propagiert Daten in Folgetriggers | E.5 / J.2 Nr. 4 (Kontext-Teil): unlockt H.3 (Gift-Combos), Rollenfilter für H.2 |
| *(aktuell)* | **HookContext-Typ + Kommentar-Sonderfall aufgelöst**: Kontext ist `dict`-Subklasse mit fail-fast Attribut-Zugriff; `user` immer String, Kommentartext nur im Kontext; `{comment}`-Overlay liest aus dem Kontext | E.5 abgeschlossen; Datenvertrag konsistent über alle Events |
| *(aktuell)* | **Capability-Enforcement**: neues Manifest-Feld `permissions` (`rcon`/`triggers`/`overlay`/`store`) wird in `for_hook()`-Views erzwungen; verweigerte Aufrufe → `HOOK-0009` + sicherer Rückgabewert; `capabilities` bleiben Discovery-Tags; Shipped-Manifeste deklarieren ihre Berechtigungen | E.8 / J.2 Nr. 10: Isolation ist wirksam statt nur deklarativ |
| *(aktuell)* | **`api.request()`-Helper**: synchroner JSON-Request/Response gegen die Control Plane (GET/POST/PUT), geparster Body oder `None`, Permission `network`; Spotify-Control-Hook umgestellt (urllib-Boilerplate entfernt) | J.2 Nr. 8 (pragmatisch): Hooks können Zustand abfragen ohne DIY-HTTP |
| *(aktuell)* | **Webhook-Minecraft-Semantik konfigurierbar**: `minecraft_server_api.queue_pause_on_death` (Default `true`) gated die Queue-Pause bei `player_death`/`player_respawn`; Logik in testbarem `_apply_mc_queue_semantics()` | E.7: Fremdspiel mit gleichnamigen Events verfälscht die Queue nicht mehr |
| *(aktuell)* | **Generisches Event-Abo**: `event_subscriptions` akzeptiert jede Bus-Quelle (`minecraft.*`, `timer.*`, `server.*`, Plugin-Events, Catch-all `"*"`); Nicht-TikTok-Quellen kommen als `bus_event`-Kommando ohne `user`-Pflicht an | J.3 Nr. 14: Plugins hören auf System-/Plugin-Events ohne zentrale ECM-YAML-Pflege |
| *(aktuell)* | **Event-Katalog mit Version + Delivery-Validierung**: Katalog-Antwort mit `version`; unbekannte exakte Subscriptions → Bridge-Warnung; Kommandos außerhalb `accepted_commands` → Route-Warnung (warn-only) | J.3 Nr. 12: Deklarationen wirken zur Laufzeit, nicht nur im GUI-Wizard |
>
> Weiterhin offen: J.3 Nr. 11/13.

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
- Handler-Signatur: `(user, trigger, context)` — **[✅ ERLEDIGT: strukturierter `context` als `HookContext`]** Die Event-Quellen (Gift/Follow/Like/Kommentar/Join/Share/Webhook) bauen einen strukturierten Kontext (`event`, `source` + ereignisspezifische Keys wie `gift_name`/`streak`/`combo`, `comment`/Rollen-Flags, Like-Milestone-Daten), der an jede Hook-Action als drittes Argument übergeben wird; Details in Dev-Book ch04-03. `user` ist **immer** der reine Username-String — der frühere Kommentar-Dict-Sonderfall (`{user, comment}`) ist aufgelöst, der Kommentartext lebt ausschließlich im Kontext.
- Verfügbare Fähigkeiten via `HookAPI`: `rcon_enqueue`, `enqueue_trigger` (max. Ketten­tiefe 3, Banliste für `tiktok`/`connect`/`disconnect`), `send_overlay_text` (HTTP), `log`, Config-Kopie (`get_hook_config`, `config`), `get_valid_functions`.

### B.2 Stärken
1. **Geringste Latenz aller Erweiterungsarten:** in-process, kein HTTP-Hop, direkt im Trigger-Pfad.
2. **Robust isoliert:** Handler laufen im Executor-Thread; Exceptions werden vom CrashManager gemeldet, ohne die Bridge zu töten.
3. **Kleine, prüfbare Angriffsfläche:** Import-Whitelist + Manifest (`min_api_version`, `depends_on` vorhanden).
4. **Vollzugriff auf die Kernaktionen**, die auch `.mca`-Zeilen haben (`enqueue_trigger` = beliebige weitere Triggerketten).

### B.3 Schwächen / harte Grenzen
1. ~~**Kein Veto**~~ **[✅ ERLEDIGT — `54fdb78`]** Rückgabewerte des Handlers werden jetzt ausgewertet: `False` bricht die Restkette ab (spätere `$`-Actions, Overlay, Vanilla, RCON, Shell), `None`/`True` verhält sich wie bisher (rückwärtskompatibel). Damit sind Filter-/Moderations-Gates (H.1/H.2) möglich.
2. **Kein Ereigniszugang:** Hooks können nur durch `$`-Zeilen in `actions.mca` feuern. Es gibt kein `subscribe(event)` — Reaktion auf `tiktok.gift` & Co. nur über den Umweg einer `.mca`-Zeile. *(unverändert; gilt weiterhin)*
3. **Kein Lifecycle:** Keine Callbacks für Stream-Start/-Ende, keine Timer/Hintergrundtasks, keine Initialisierung mit garantiertem Aufrufkontext jenseits von `register()`. **[✅ ERLEDIGT: `api.on_live_start/on_live_end` + `register_lifecycle` in HookAPI, gefeuert aus Bridge on_connect/on_live_end]**
4. **Kein Runtime-Reload:** Aktivieren/Deaktivieren erfordert Bridge-Neustart (auch laut `routes/hooks.py`). Die Reload-Signal-Dateien decken nur config/actions/comment_commands/chatbot ab — **nicht Hooks**. **[✅ ERLEDIGT: `reload_hooks` Signal + Bridge-Watcher + `_request_hook_reload` in enable/disable/config-PUT + `POST /reload hooks=true`; Full-Reload aller Hooks]**
5. **Whitelist schneidet legitime Anwendungsfälle ab:** keine `os`/`subprocess`/Audio-/DB-Libs. Gleichzeitig erlaubt `requests` vollen Netzwerkzugriff aus dem Bridge-Prozess — das Sicherheitsversprechen ist also asymmetrisch (Prozess isolation fehlt komplett). *(unverändert → J.2 Nr. 10)*
6. ~~**Keine Zustands-/Persistenzdienste**~~ **[✅ ERLEDIGT — `022fe7a`]** Hooks nutzen die namespaced Persistenz-API per HTTP (`urllib`/`requests` aus der Whitelist): eigener Namespace unter `data/plugin_data/<hook-name>.json`, dokumentiert in Dev-Book ch04-03.
7. **Kein Publish:** Ein Hook kann nichts auf den EventBus legen; Kommunikation mit Plugins wäre nur über den undokumentierten Direktaufruf der REST-API per `requests` möglich. *(unverändert)*

**Fazit Hook-System:** Als schneller, einfacher Aktions-Erweiterungspunkt gut gelungen; als *Ereignis*-Erweiterungsebene ungeeignet (kein `subscribe`) — **Veto und strukturierter Kontext existieren inzwischen**, wodurch Aktion-Gates, Moderationsfilter und datengetriebene Hooks (Combos, Milestones) realistisch geworden sind. Die Doku positioniert Hooks korrekt als „Aktionen statt Reaktionen".

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
1. ~~**Der dokumentierte Ereignispfad 1 ist tot**~~ **[✅ ERLEDIGT — `f409595`]** Der Bridge published echte `tiktok.*`-Events per HTTP (`POST /api/v1/events`, gleiches Muster wie `minecraft.*`) auf den API-Bus; der neue **PluginEventBridge**-Service (API-Prozess) matcht `event_subscriptions` (exakt + `prefix.*`) und legt `tiktok_event`-Kommandos in die CommandQueue, die Plugins pollen. Integrationstest deckt den Pfad ab.
2. ~~**Kommentarfeed nicht abonnierbar / `comment_handler` nur Doku**~~ **[✅ ERLEDIGT — `f409595`]** `comment_handler: {prefix, enabled}` ist implementiert: Bei `tiktok.comment` wird ein `comment`-Kommando mit `{text, username}` (Präfix gestript, Default `$`) zugestellt; dokumentiert in ch03-05/ch03-01.
3. **Fire-and-forget überall:** `send_command` hat keine Antwortwarteschlange, keine Korrelations-IDs; Request/Response zwischen Extensions ist nicht modelliert. *(Hook→Control-Plane inzwischen via `api.request()` gelöst → J.2 Nr. 8; Plugin↔Plugin-Korrelations-IDs bleiben offen)*
4. **Keine eigenen Endpunkte:** Das REST-Interface pro Plugin ist fix (commands/overlay/stream/state/config). Eigene Abfrage-Routen („gib mir das Leaderboard") sind nicht möglich; interaktive UIs bleiben auf statisches Overlay-HTML + SSE-State beschränkt. *(unverändert)*
5. **Keine Dashboard-Integrationspunkte:** Plugins bekommen keine Tabs/Routen im Web-Dashboard — nur Overlay-Seiten und Schema-Config-Seiten. *(unverändert → J.3 Nr. 11)*
6. ~~**Persistenz DIY und kollisionsgefährdet**~~ **[✅ ERLEDIGT — `022fe7a`]** Namespaced Persistenz-API: je Extension eine JSON-Datei unter `data/plugin_data/<name>.json`; REST (`GET/PUT/DELETE /plugins/{name}/data[/{key}]`) + `BasePlugin.store_get/store_set/store_delete/store_all`.
7. **`capabilities` rein informativ:** Nirgends wird geprüft; kombiniert mit standardmäßig deaktivierter Sandbox ist das Isolationsmodell opt-in. *(unverändert → J.2 Nr. 10)*
8. **Undokumentierte Hintertüren:** `POST /api/v1/rcon/command` (generischer RCON-Endpunkt des API-Prozesses) umgeht Queue/Throttling der Bridge — nützlich, aber weder dokumentiert noch autorisiert. *(unverändert)*

**Fazit Plugin-System:** Architektonisch die richtige Ebene für alles Schwergewichtige (Threads, Audio, OAuth, Persistenz). **Der Ereigniseingang funktioniert jetzt** (echte Events + Kommentarfeed), und Persistenz ist als namespaced Service vorhanden — verbleibende Grenzen sind Interaktion (Request/Response, eigene Routen) und Dashboard-Integration.

---

## D) Kern-Schnittstellen & Datenflüsse

### D.1 Original-Flussdiagramm (Stand **vor** Fix `f409595`)

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
    (routes/triggers.py publishen direkt!)       │                                  ▼
    Plugins publishen via POST /events ──────────┘                    GET /plugins/{name}/commands?wait=1
                                                                      (Plugin-Subprozess)
```

### D.2 Aktueller Fluss (seit `f409595`)

```
                    ┌─────────────────────────── Bridge-Prozess ───────────────────────────┐
 TikTok Live ──────►│ _handle_*_events ──► Queues ──► actions.mca / RCON / Overlay         │
                    │        │                                                             │
                    │        └─► _publish_tiktok_event / minecraft.*-Events                │
                    │            = HTTP POST /api/v1/events  (beide Event-Familien)  ✓     │
                    └──────────────────────────────────────────────────────────────────────┘
                                                       │
   GUI ◄── SSE/WS ──┐                                  ▼
                    │                 [API] event_bus ──┬─► ECM (YAML) ──────────────┐
   Test-/Dispatch-  │                                   │                            ▼
   Trigger ─────────┘                                   ▼               [API] command_queue ◄─┘
   Plugins publishen via POST /events ─────────► PluginEventBridge ── enqueues ─┘
                                                (event_subscriptions → tiktok_event,
                                                 comment_handler → comment)
```

Belegstellen (aktuell): `_publish_tiktok_event` (`main.py`) forwarded per HTTP via `_post_tiktok_event_api`; der frühere Bridge-lokale `_event_bridge_worker` ist entfernt; neu: `src/core/api/plugin_event_bridge.py` (API-Prozess, startet im Lifespan von `server.py`, registriert beim Health-Monitor als `plugin_event_bridge`). ECM läuft unverändert im API-Prozess; Integrationstest in `tests/test_core/test_plugin_event_bridge.py::TestEndToEndDelivery`.

**Randnotiz Trigger-Zugriff:** Der API-Prozess kann `actions.mca`-Trigger auf zwei Wegen auslösen:
1. `POST /api/v1/triggers/execute` (GUI-Event-Tester) — mit 1,5-s-Debounce (Singleton, mit dem GUI-Tester geteilt), semantisch „Test".
2. **[NEU, `8ea4109`]** `POST /api/v1/triggers/dispatch` — programmatischer Pfad für Erweiterungen: kein Debounce, kein Test-Flag, voller Payload (`trigger`, `user`, `gift_id`, `gift_name`), Aufzeichnung in der Trigger-History (`GET /triggers/history`). Beide Wege laufen über `TriggerService` → `TriggerEngine` → Bridge-Webhook `/custom_trigger` (Port via `RESOLVED_PORT_WEBHOOK_PORT`, Fallback 29188).

---

## E) Kritische Befunde & Inkonsistenzen

| # | Befund | Beleg | Wirkung | Status |
|---|---|---|---|---|
| E.1 | **Cross-Process-Defekt:** `_event_bridge_worker` legt `tiktok_event`-Kommandos in die Bridge-lokale `CommandQueue`; Plugins pollen aber die Queue des API-Prozesses. | `main.py` L47/L1197/L1337 vs. `plugin_overlay.py` + `base_plugin._API_BASE` | Dokumentierter „Pfad 1" (`event_subscriptions`) liefert im Betrieb **nie** etwas aus | **[✅ ERLEDIGT `f409595`]** Bridge published per HTTP; PluginEventBridge enqueued in die API-Queue |
| E.2 | **Echte `tiktok.*`-Events erreichen den API-Bus nie.** Nur Test-Trigger erscheinen dort (direkter Publish in `routes/triggers.py`). | grep `publish` in `main.py` vs. `routes/triggers.py` L55–57/85/116 | ECM-Mappings für `tiktok.comment` etc. feuern bei **Testkommentaren, aber nie bei echten** — tückische Inkonsistenz; GUI-Livefeed/TikTokLiveTracker sehen Realverkehr nicht | **[✅ ERLEDIGT `f409595`]** echte Events landen auf dem Bus (`source: "bridge"`) |
| E.3 | **`comment_handler` dokumentiert, nicht implementiert.** | Dev-Book ch03-05/ch03-02 vs. grep in `src/**.py`: 0 Treffer | Doku verspricht Feature, das es nicht gibt | **[✅ ERLEDIGT `f409595`]** implementiert (`CommentHandlerConfig`, Prefix-Strip, Default `$`) |
| E.4 | Kein shipped Plugin nutzt `event_subscriptions`; keine Tests zu `_event_bridge_worker`. | grep in `src/plugins`, `tests` | Defekt blieb unbemerkt | **[✅ ERLEDIGT `54fdb78`]** Integrationstest + Unit-Tests für die Zustellung (`test_plugin_event_bridge.py`) |
| E.5 | **Hook-Kontext immer `{}`**, keine strukturierten Ereignisdaten. | `main.py` (`execute_global_command(..., {})`) | Hooks können nicht datengetrieben arbeiten | **[✅ ERLEDIGT]** `_make_hook_context` an allen Event-Quellen, 4-Tupel in der Trigger-Queue, Kontext inkl. `chain_depth` an Hook-Actions; `enqueue_trigger(context=...)` für Verkettung |
| E.6 | **Kein Veto-/Rückgabevertrag** für Hook-Actions. | `hook_api.execute_global_command` ignoriert Rückgaben | Filter/Moderation als Hook unmöglich | **[✅ ERLEDIGT `54fdb78`]** Veto-Vertrag: `False` = Restkette abbrechen; Kontext-Teil durch den strukturierten Context ebenfalls erledigt |
| E.7 | ~~Minecraft-Semantik im generischen Webhook: `player_death`/`player_respawn` pausieren die MC-Queue **unabhängig von der Quelle**.~~ **[✅ ERLEDIGT]** Neuer Config-Gate `minecraft_server_api.queue_pause_on_death` (Default `true`, rückwärtskompatibel): ohne Opt-in keine Queue-Pause; `minecraft.{event}` wird weiterhin generisch publiziert, Semantik liegt in `_apply_mc_queue_semantics()` (unit-testbar). | Bridge `/webhook`-Handler | ~~Fremdspiel, das gleichnamige Events sendet, verfälscht das Verhalten~~ | **[✅ ERLEDIGT]** |
| E.8 | ~~`capabilities` werden nicht erzwungen; Sandbox default aus; Hooks dürfen `requests`.~~ **[✅ TEIL-ERLEDIGT]** Neues Feld `permissions` (`rcon`/`triggers`/`overlay`/`store`) wird pro Hook-View erzwungen (`HOOK-0009`, sicherer Rückgabewert); `capabilities` bleiben Discovery-Tags. Direkter `requests`/urllib-Netzzugriff bleibt erlaubt (dokumentiert) — echte Sandbox weiterhin offen. | `sandbox.py`, `hook_loader.py` | ~~Isolation ist deklarativ, nicht wirksam~~ API-Isolation jetzt wirksam; Prozess-Sandbox unangetastet | **[✅ API-Ebene]** |

---

## F) Vorgabe 1: TTS zum Vorlesen von Kommentaren

### F.1 Anforderungsprofil
Alle Kommentare (Text, Nutzer, ggf. Rollen) empfangen → TTS-Engine (lokal z. B. pyttsx3/SAPI, oder Cloud) → Wiedergabe mit Warteschlange, Priorität, Cooldown, Mute-Schalter, Config-UI.

### F.2 Passende Ebene
**Plugin** — Audio-Playback blockiert, braucht eigene Threads/Queue, Persistenz und Schema-Config. Ein Hook scheidet praktisch aus: Die Import-Whitelist verbietet `pyttsx3`/Audio-Libs ebenso wie `subprocess` (lokales TTS-Programm starten).

### F.3 Wie käme das Plugin an ALLE Kommentare? (Stand: jetzt)
| Weg | Bewertung |
|---|---|
| `comment_commands.yaml`-Gruppe | ❌ Präfix muss **nicht-leer** sein (`startswith`-Check) — „alle Kommentare" nicht abbildbar; Mechanismus ist für Befehle, nicht für einen Feed gedacht |
| `event_subscriptions: ["tiktok.comment"]` | ✅ funktioniert seit `f409595` (PluginEventBridge); Text liegt als `data.comment` im Event |
| `comment_handler: {prefix, enabled}` | ✅ neu implementiert (`f409595`) — präfixfreier Kommentarfeed als `comment`-Kommando `{text, username}` |
| ECM-Mapping `tiktok.comment → tts/say` | ✅ feuert jetzt auch bei **echten** Kommentaren (E.2 behoben) |
| Hook nach `comment:`-Zeile in actions.mca | ⚠️ Text wäre via `user`-Dict erreichbar, aber TTS technisch whiteliste-bedingt unmöglich (B.3.5) |

### F.4 Urteil
Original-Urteil war **„Nur mit strukturellen Änderungen"** — der fehlende Kommentar-*Eingang* war der Blocker.

**[AKTUALISIERT]** Seit `f409595` lautet das Urteil: **„Ja"** — Plugin mit `event_subscriptions: ["tiktok.comment"]` oder `comment_handler` empfängt alle Kommentare; die TTS-Logik selbst ist reines Plugin-DIY (Queue, Cooldowns, Engine-Wahl). Persistenz für Mute-Listen etc. über die namespaced Store-API.

---

## G) Vorgabe 2: Spiele-Integration ohne RCON

### G.1 Inbound (Spiel → TikTok2Mc)
| Kanal | Funktioniert? | Probleme |
|---|---|---|
| Bridge `/webhook` (`minecraft.{event}` → API-Bus → ECM → Plugins) | ✅ heute | Namen sind Minecraft-brandet; E.7: `player_death` pausiert die echte MC-Queue — Namenskollision mit Seiteneffekten; separates Auth-/Port-Thema |
| Bridge `/custom_trigger` | ✅ heute | Führt nur **vordefinierte** actions.mca-Trigger aus; Payload nur `user`-String; keine strukturierten Daten; undokumentierter Port |
| API `POST /events` | ✅ heute | Erreicht Plugins (via ECM), aber **nie actions.mca** — der Bus liegt im anderen Prozess als die Trigger-Queues |
| API `POST /triggers/execute` | ✅ heute | 1,5-s-Debounce (Singleton, geteilt mit GUI-Tester), nur `user`/`gift_id`, semantisch ein Testendpunkt |
| API `POST /triggers/dispatch` **[NEU `8ea4109`]** | ✅ heute | Kein Debounce, kein Test-Flag, voller Payload (`trigger`/`user`/`gift_id`/`gift_name`) — der saubere Inbound für externe Systeme |

### G.2 Outbound (TikTok2Mc → Spiel)
- `&`-Shell-Zeilen: Prozess-Spawn pro Trigger, kein Protokoll, kein Lifecycle.
- `$`-Hook/Skript oder Plugin mit `requests`/Websockets: technisch frei, aber **alles DIY** — Reconnect, Auth, Health, Retry, Circuit-Breaker. Ein wiederverwendbares Muster (Circuit-Breaker) existiert intern nur im Overlay-Manager.

### G.3 Urteil
**Einzelintegration als Plugin: „Ja, mit Einschränkungen"** (Transport komplett DIY, Inbound nur über Minecraft-branded Webhook mit Kollisionsrisiko).
**Eine generische „Game-Connector"-Architektur: „Nur mit strukturellen Änderungen":** es fehlen (a) ein typisierter, generischer Inbound, der sowohl Bus **als auch** Trigger-Engine speist, (b) die Entkopplung der Minecraft-Spezialfälle vom Webhook, (c) ein Outbound-Kanal-Konzept (konfigurierbare Ziele inkl. Retry/Breaker).

**Wiederverwendbare Bausteine:** generischer Inbound-Endpoint (Trigger-Dispatch ✅ vorhanden, Outbound-Channels ✅ `4aa4711`, J.2 Nr. 6) — identisch nützlich für Discord-Notifier, Home-Assistant, OBS-Steuerung usw.

---

## H) Eigene Hook-Ideen (bewertet)

### H.1 Anti-Spam-/Rate-Limit-Gate (Veto-Hook)
- **Idee:** Hook registriert `$gate_<trigger>` als erste Zeile jeder Kette; zählt Events pro Nutzer/Fenster und soll bei Überschreitung die Restkette verwerfen.
- **Technik:** in-process State, `time`/`random` aus Whitelist — Zähllogik trivial.
- ~~**Blocker:** kein Veto-Vertrag (E.6).~~ **[GELÖST `54fdb78`]**
- **Original-Urteil:** „Nur mit strukturellen Änderungen" (Veto-Semantik fehlte).
- **[AKTUALISIERT] Urteil: „Ja"** — Handler gibt `False` zurück, Restkette wird verworfen; Beispiel in Dev-Book ch04-03 (EN+DE).

### H.2 Schimpfwort-Moderator für Kommentarzeilen
- **Idee:** `$profanity_check` vor Kommentar-Reaktionen; soll unangebrachte Kommentare von allen Folgeaktionen ausschließen.
- **Technik:** Text liegt strukturiert im Kontext (`comment` + Rollen-Flags), Regex-Listen in hook.json-Config ladbar.
- ~~**Blocker:** Veto-Vertrag fehlte~~ **[GELÖST `54fdb78`]**; ~~strukturierte Rollen-Flags im Kontext fehlen~~ **[GELÖST: strukturierter Kontext liefert `is_moderator`/`is_super_fan`/`in_fanclub`]**.
- **Original-Urteil:** „Nur mit strukturellen Änderungen" (Veto + Kommentar-Datenvertrag).
- **[AKTUALISIERT] Urteil: „Ja"** — Veto funktioniert, Kommentartext und Rollen-Flags liegen strukturiert im Kontext (`comment`, `is_moderator`, `is_super_fan`, `in_fanclub`).

### H.3 Gift-Combo-Detektor (Milestone-in-Fenster)
- **Idee:** Erkennt „X gleiche Gifts in Y Sekunden durch Nutzer Z" und stößt Bonus-Trigger an.
- **Technik:** Zeitfenster-Logik ideal für in-process Hook; Auslösen per `enqueue_trigger` vorhanden; Beispiel in Dev-Book ch04-03 (EN+DE).
- ~~**Blocker:** Hook sieht **keine** Giftmetadaten (Name, Anzahl, Combo-Flag) — `context={}`~~ **[GELÖST: strukturierter Kontext]** — `context` enthält jetzt `event: "gift"`, `gift_name`, `gift_id`, `streak` (Combo-Länge), `combo`; Bonus-Ketten können ihre eigenen Daten per `enqueue_trigger(context=...)` mitnehmen.
- **Original-Urteil:** „Aktuell nicht sinnvoll möglich"; nach Einführung eines strukturierten Action-Kontexts: „Ja".
- **[AKTUALISIERT] Urteil: „Ja"** — alle benötigten Eingabedaten liegen im Kontext.
- **Lehrstück:** zeigt exemplarisch, dass dem Hook-System der **Datenvertrag** fehlte, nicht die Rechenlogik.

---

## I) Eigene Plugin-Ideen (bewertet)

### I.1 Discord/Webhook-Notifier
- **Idee:** Mappt Bus-Events (Follows, Milestones, Serverstatus) auf Discord-Webhooks; Template-Nachrichten, Rate-Limit, kanalbezogene Routen.
- ~~**Blocker:** echte `tiktok.*`-Events fehlen (E.2)~~ **[GELÖST `f409595`]**
- **Original-Urteil:** „Ja, mit Einschränkungen".
- **[AKTUALISIERT] Urteil: „Ja"** — alle `tiktok.*`-Events sind auf dem API-Bus; ECM-Mapping + `requests`, Tokens via `secure_storage`. QOL-Baustein generischer Notification-Dispatcher bleibt offen (J.3 Nr. 13).

### I.2 Scheduler/Cron für actions.mca
- **Idee:** Zeitgesteuerte Trigger („alle 30 min `bonus_drop`", tägliche Reset-Aktionen) mit Cron-Syntax in plugin.yaml.
- ~~**Caveats:** Debounce des geteilten Singletons, Payload nur `user`/`gift_id`, Endpunkt semantisch „Test"~~ **[GELÖST `8ea4109`: `POST /triggers/dispatch`]**
- **Original-Urteil:** „Ja, mit kleineren Erweiterungen".
- **[AKTUALISIERT] Urteil: „Ja"** — Scheduler-Plugin ruft `/triggers/dispatch` auf eigenem Zeitplan; kein Kollisionsrisiko mit dem GUI-Tester mehr.

### I.3 Viewer-Leaderboard mit Persistenz
- **Idea:** Aggregiert Gifts/Follows/Kommentarpunkte pro Viewer, SQLite/JSON, Overlay-Top-10, saisonale Resets.
- **Original-Blocker-Kette:** (1) echte Gift/Follow-Events erreichen kein Plugin (E.1/E.2); (2) Persistenz DIY im geteilten `data/`; (3) Abfragen/Sortierungen können nicht serverseitig beantwortet werden — keine eigenen REST-Routen; Overlay-HTML bleibt statisch+SSE; Dashboard-Tab unmöglich.
- **Status:** (1) ✅ `f409595`, (2) ✅ `022fe7a` (namespaced Store), (3) **offen** (eigene Routen/Dashboard-Tab, J.3 Nr. 11).
- **Original-Urteil:** „Nur mit strukturellen Änderungen".
- **[AKTUALISIERT] Urteil: „Ja, mit Einschränkungen"** — Aggregation + Persistenz sind jetzt Plugin-DIY mit Board-Mitteln; das Overlay liest den Store per SSE/State-Push. Serverseitige Queries bleiben ein Nice-to-have.

---

## J) Noch fehlende Bausteine für zukünftige Flexibilität

### J.1 Zwingend erforderlich (Pflicht — Defekte/blocking) — **[ALLE ERLEDIGT]**
1. ~~**Prozessübergreifende Ereignisweiterleitung Bridge → API**~~ **[✅ `f409595`]** Bridge published echte `tiktok.*`-Events per HTTP auf den API-Bus; neuer **PluginEventBridge**-Service matcht `event_subscriptions` und enqueued in die API-CommandQueue. Repariert E.1+E.2.
2. ~~**Entscheidung zu `comment_handler`**~~ **[✅ `f409595`]** implementiert (`prefix`/`enabled`, Default `$`) statt entfernt.
3. ~~**Tests für die Ereigniszustellung**~~ **[✅ `54fdb78`]** Integrationstest (echter EventBus → Bridge-Loop → echte CommandQueue) + Unit-Tests in `tests/test_core/test_plugin_event_bridge.py`.

### J.2 Sinnvoll (hoher Nutzen für mehrere Ideen)
4. ~~**Veto-/Rückgabevertrag für Hook-Actions**~~ — **[✅ ERLEDIGT]** Veto-Vertrag (`54fdb78`: `False` = Restkette abbrechen) **plus strukturierter `context` als `HookContext` (dict-Subklasse mit fail-fast Attribut-Zugriff)**: Event-Quellen bauen `_make_hook_context(...)` (gift/follow/like/comment/join/share, `source: tiktok|webhook|hook`), die Trigger-Queue trägt 4-Tupel `(trigger, user, depth, context)`, `execute_global_command` übergibt ihn unverändert an jede Hook-Action; `HookAPI.enqueue_trigger(context=...)` propagiert Daten in Folgetriggers. **Breaking seit v1.0.0:** `user` ist immer ein String (Kommentar-Dict-Sonderfall entfernt), `chain_depth` wird nicht exponiert. Unlockt H.3 endgültig + Rollenfilter für H.2.
5. **Hook-Runtime-Reload/Lifecycle:** Enable/Disable ohne Bridge-Restart (Reload-Signal-Mechanik erweitern); `on_live_start/end`-Callbacks. **[✅ ERLEDIGT (Commits: HookAPI Lifecycle + Reload + Bridge Watcher + API Endpoints)]**
6. ~~**Generischer Outbound-Kanal**~~ — **[✅ `4aa4711`]** `OutboundDispatcher` im API-Prozess: EventBus → konfigurierbare HTTP-Channels (`outbound:` in config.yaml; Formate `raw`/`discord`, Event-Patterns wie `event_subscriptions`), Retry + Circuit-Breaker pro Channel (`OverlayClient` wiederverwendet), Health-Lifecycle; REST `GET /outbound/channels` (URLs maskiert) + `POST /outbound/channels/{name}/test` (reine Probe); dokumentiert in ch03-04 (EN+DE). Grundlage G.3/I.1 geschaffen.
7. ~~**Trigger-Zugriff für Erweiterungen**~~ — **[✅ `8ea4109`]** `POST /api/v1/triggers/dispatch`: kein Debounce, definierter Payload (`trigger`/`user`/`gift_id`/`gift_name`), History-Aufzeichnung; dokumentiert in ch03-04 (EN+DE). Grundlage I.2 geschaffen.
8. ~~**Request/Response zwischen Extensions:** Korrelations-IDs/Antwortqueue statt reinem Fire-and-forget.~~ **[✅ ERLEDIGT (pragmatisch)]** `api.request(path, payload=None, method=None, timeout=5)` im HookAPI: synchroner JSON-Call gegen die Control Plane (GET ohne Payload, POST/PUT mit), geparster Body oder `None`, nie Exceptions; Permission `network`; Spotify-Control-Hook nutzt ihn bereits (Boilerplate-urllib entfernt). Volle Korrelations-IDs/Antwortqueues zwischen Plugins bleiben Zukunftsthema — für Hook→Control-Plane-Abfragen reicht das.
9. ~~**Namespaced Persistenz-API pro Plugin/Hook**~~ — **[✅ `022fe7a`]** `PersistenceService` (`data/plugin_data/<name>.json`, atomar), REST `GET/PUT/DELETE /plugins/{name}/data[/{key}]`, `BasePlugin.store_*`-Helper; dokumentiert in ch03-04/ch04-03 (EN+DE).
10. ~~**Capability-Enforcement:** `capabilities` prüfen oder streichen; Sandbox-Profile; Hook-Netzzugriff bewusst entscheiden (B.3.5/E.8).~~ **[✅ ERLEDIGT (API-Ebene)]** Neues Feld `permissions` in hook.json (`rcon`/`triggers`/`overlay`/`store`) wird in den `for_hook()`-Views erzwungen — verweigerte Aufrufe loggen `HOOK-0009` und liefern sichere Rückgabewerte. `capabilities` bleiben unverändert Discovery-Tags (Saubere Trennung: Angebot vs. Rechte). Direkter Netzzugriff via `requests`/urllib bleibt erlaubt und dokumentiert; Prozess-Sandbox-Profile weiterhin offen.

### J.3 Nice-to-have (QOL+)
11. Dashboard-UI-Erweiterungspunkte (Tabs/Routen für Plugins) — löst I.3s UI-Anteil.
12. ~~**Einheitliches Event-Schema/-Katalog mit Versionierung; `emitted_events`/`accepted_commands` für Delivery statt nur GUI-Katalog nutzen.~~ **[✅ ERLEDIGT (pragmatisch)]** Katalog-Antwort trägt `CATALOG_VERSION` (`version: 1`); `collect_known_event_keys()` (Core + alle `emitted_events`) dient als Delivery-Registry — unbekannte exakte Subscriptions erzeugen eine Bridge-Warnung (Tippfehler-Schutz, Wildcards ausgenommen); `POST /plugins/{name}/command` warnt bei Kommandos außerhalb der deklarierten `accepted_commands` (warn-only, TTL-Cache, Zustellung bleibt unangetastet). Vollständige Schemata pro Event (Payload-JSON-Schema) bleiben Zukunftsthema.
13. ~~**Notification-Dispatcher (Overlay/Sound/TTS/Discord als austauschbare Kanäle).**~~ **[✅ ERLEDIGT]** `NotificationDispatcher` (`core/api/notification_dispatcher.py`, Singleton) mit Channel-Registry `CHANNEL_HANDLERS` — eingebaut: `log`, `overlay` (direkt via `core.overlay.send_overlay_text`, kein HTTP-Umweg), `sound` (winsound, Windows), `tts` (PowerShell SAPI, Windows-guarded), `discord` (Webhook-POST, maskierte URLs in Logs). REST: `POST /api/v1/notifications` (`{title, body?, level?, channels?}` → `{sent, failed, skipped}`, Fan-out via `asyncio.to_thread` + gather), `GET /notifications/channels`, `POST /notifications/reload`. Config-Abschnitt `notifications:` bewusst **nicht** in `defaults/config.yaml` — Benachrichtigungen sind rein caller-getrieben (Inline-Parameter pro Request); wer will, kann den Abschnitt manuell als Default-Quelle ergänzen. Fehlercodes `NOTIF-0001`/`NOTIF-0002` warn-only — Zustellprobleme werfen nie. Plugins senden via `BasePlugin.api_request("notifications", payload={...})` (Body-Rückgabe, Parität zu `api.request`; `api_post` bleibt als Fire-and-forget-Variante), Hooks über `api.request("notifications", payload=...)` (mit `network`-Berechtigung). **Autarkie-Prinzip:** `channels` akzeptiert zusätzlich ein Mapping `{name: params}` — Inline-Parameter werden über die globale Channel-Config gemischt (Inline gewinnt), ein nur im Request genannter Channel braucht keinen globalen Eintrag; Plugins/Hooks holen alle Versand-Einstellungen aus ihrer eigenen Schema-Config und bleiben damit vollständig self-contained (Enduser konfigurieren im Plugin-GUI-Formular, nie in YAML). TTS als Vollfeature (Queueing, Stimmen) bleibt Plugin-Thema (Idee F). Dokumentiert in ch03-04 (EN+DE).
14. ~~**Generisches Event-Abo über alle Quellen** (heute: `event_subscriptions` nur für `tiktok.*`, sonst zwingend zentrale ECM-YAML-Handpflege).~~ **[✅ ERLEDIGT]** `event_subscriptions` akzeptiert jetzt **jede** Bus-Quelle (exakt, Prefix-Wildcard oder Catch-all `"*"`); TikTok-Events bleiben beim `tiktok_event`-Vertrag (mit `user`), alle anderen Quellen (`minecraft.*`, `timer.*`, `server.*`, Plugin-Events) kommen als neues `bus_event`-Kommando (`event_type` + `data`, kein `user`) in die CommandQueue. ECM bleibt für Aktionsverkettung; Docs ch03-02/ch03-05 (EN+DE) aktualisiert.

---

## K) Fazit

Die Zwei-Ebenen-Architektur ist im Kern **richtig und durchdacht**: Hooks für schnelle Aktionen im Trigger-Pfad, Plugins für alles Schwergewichtige in Isolation. Das Fundament (Registry, Manifeste, Schema-Config, Health-Monitor, TriggerEngine als Single Source of Truth, secure_storage) ist solide und wiederverwendbar.

Was die versprochene Flexibilität ursprünglich **ausbremste**, waren keine Designfehler, sondern:
1. **Zwei Zustellungsdefekte** (E.1/E.2), die die dokumentierte Ereignisfähigkeit faktisch abschalteten — mit einem Fix adressierbar;
2. **fehlende Verträge** (Veto ~~und Kontext~~ ✅, ~~Request/Response~~ ✅ via `api.request()`; Persistenz/Outbound ✅), die jede ernsthaftere Idee in DIY-Treibhausarbeit trieben (F, G, H, I belegen das einzeln);
3. **Doku-/Code-Drift** (`comment_handler`, tote Pfade), die Vertrauen in die Erweiterungsversprechen untergräbt.

### Umsetzungsstand (August 2026)

**Erledigt:** alle J.1-Pflicht-Fixes (Event-Zustellung, `comment_handler`, Integrationstest), Veto-Vertrag, strukturierter Hook-Kontext (`HookContext`), Trigger-Dispatch-Endpoint, namespaced Persistenz-API, generischer Outbound-Kanal (Webhooks/Discord), Hook-Runtime-Reload/Lifecycle, Capability-Enforcement (`permissions`), Request/Response-Helper (`api.request()`), Webhook-Minecraft-Semantik (Config-Gate), generisches Event-Abo (`bus_event`), Event-Katalog-Version + Delivery-Validierung. Die Ideen F (TTS), H.1–H.3 (Gates/Moderation/Combos), I.1 (Notifier via Outbound) und I.2 (Scheduler) sind damit **praktisch umsetzbar**; I.3 (Leaderboard) kann Zustand jetzt per `api.request()` abfragen und System-Events per `bus_event` empfangen.

**Verbleibende Roadmap (empfohlene Reihenfolge):**
1. ~~J.2 Nr. 5 — Hook-Runtime-Reload/Lifecycle~~ **[✅ ERLEDIGT]**
2. ~~E.5/J.2 Nr. 4-Rest — strukturierter Hook-`context`~~ **[✅ ERLEDIGT]** (inkl. `HookContext`-Typ + Kommentar-Sonderfall aufgelöst)
3. ~~J.2 Nr. 10 — Capability-Enforcement~~ **[✅ ERLEDIGT]** (`permissions`-Feld, API-Ebene; Prozess-Sandbox bleibt offen)
4. ~~J.2 Nr. 8 — Request/Response (`api.request()`-Helper) + E.7 (Webhook-Semantik)~~ **[✅ ERLEDIGT]**
5. ~~J.3 nach Bedarf (Nr. 11–14)~~ → **Nr. 14 [✅ ERLEDIGT]** (generisches Event-Abo), **Nr. 12 [✅ ERLEDIGT]** (Katalog-Version + Delivery-Validierung), **Nr. 13 [✅ ERLEDIGT]** (Notification-Dispatcher); offen: Nr. 11 (Dashboard-UI-Erweiterungspunkte); E.7-Restthema „Prozess-Sandbox-Profile" nur bei Bedarf
