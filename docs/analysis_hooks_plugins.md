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
> | `f409595` | **PluginEventBridge** (`src/core/api/plugin_event_bridge.py`) | Echte `tiktok.*`-Events werden vom Bridge per HTTP auf den API-Bus weitergeleitet und als Kommandos an abonnierende Plugins zugestellt; der Kommentarfeed (`comment_handler`) ist implementiert |
> | `54fdb78` | **Veto-Vertrag** für Hook-Actions (`False` = Restkette abbrechen) + Integrationstest echte Zustellung | Filter-/Moderations-Gates sind möglich |
> | `8ea4109` | **`POST /api/v1/triggers/dispatch`** — programmatische Trigger ohne GUI-Debounce | Sauberer Inbound für Scheduler/externe Systeme |
> | `022fe7a` | **Namespaced Persistenz-API** (`data/plugin_data/<name>.json` + REST + `BasePlugin.store_*`) | Persistenz ohne Kollisionsrisiko |
> | *(aktuell)* | **Strukturierter Hook-Kontext**: Event-Quellen bauen `_make_hook_context(...)` (gift/follow/like/comment/join/share/webhook/hook), Trigger-Queue trägt 4-Tupel mit Context, `execute_global_command(context)` reicht ihn an Hook-Actions weiter; `enqueue_trigger(context=...)` propagiert Daten in Folgetriggers; `HookContext` ist eine `dict`-Subklasse mit fail-fast Attribut-Zugriff, `user` immer String | Datengetriebene Hooks (Gift-Combos, Moderationsfilter mit Rollen-Flags) werden möglich |
> | *(aktuell)* | **Capability-Enforcement**: neues Manifest-Feld `permissions` (`rcon`/`triggers`/`overlay`/`store`/`network`/`events`) wird in `for_hook()`-Views erzwungen; verweigerte Aufrufe → `HOOK-0009` + sicherer Rückgabewert; `capabilities` bleiben Discovery-Tags; Shipped-Manifeste deklarieren ihre Berechtigungen | Isolation ist wirksam statt nur deklarativ |
> | *(aktuell)* | **`api.request()`-Helper**: synchroner JSON-Request/Response gegen die Control Plane (GET/POST/PUT), geparster Body oder `None`, Permission `network`; Spotify-Control-Hook umgestellt (urllib-Boilerplate entfernt) | Hooks können Zustand abfragen ohne DIY-HTTP |
> | *(aktuell)* | **Webhook-Minecraft-Semantik konfigurierbar**: `minecraft_server_api.queue_pause_on_death` (Default `true`) gated die Queue-Pause bei `player_death`/`player_respawn`; Logik in testbarem `_apply_mc_queue_semantics()` | Fremdspiel mit gleichnamigen Events verfälscht die Queue nicht mehr |
> | *(aktuell)* | **Generisches Event-Abo**: `event_subscriptions` akzeptiert jede Bus-Quelle (`minecraft.*`, `timer.*`, `server.*`, Plugin-Events, Catch-all `"*"`); Nicht-TikTok-Quellen kommen als `bus_event`-Kommando ohne `user`-Pflicht an | Plugins hören auf System-/Plugin-Events ohne zentrale ECM-YAML-Pflege |
> | *(aktuell)* | **Event-Katalog mit Version + Delivery-Validierung**: Katalog-Antwort mit `version`; unbekannte exakte Subscriptions → Bridge-Warnung; Kommandos außerhalb `accepted_commands` → Route-Warnung (warn-only) | Deklarationen wirken zur Laufzeit, nicht nur im GUI-Wizard |
> | *(aktuell)* | **Dashboard-UI-Erweiterungspunkte**: Manifest-Feld `dashboard_ui`; Plugin liefert `get_dashboard_html()` → `POST /plugins/{name}/dashboard-html`, ausgeliefert unter `GET /plugins/{name}/dashboard`; Web-Dashboard erzeugt dynamisch Sidebar-Tabs mit Iframe (lazy-load, „In neuem Tab öffnen“); Referenzimplementierung death-counter | Plugins bekommen Tabs im Dashboard |
> | *(aktuell)* | **RCON-Hintertür autorisiert + dokumentiert**: Config-Gate `rcon.http_command_api` (**Default `false`**) gated `POST /rcon/command` (`403 MC-0012` bei Deaktivierung); Warn-Doku zum Queue/Throttling-Bypass in ch03-04 (EN+DE) | Endpunkt ist dokumentiert und standardmäßig deaktiviert |
> | *(aktuell)* | **Plugin-Queries mit Korrelations-IDs**: `POST /plugins/{name}/query` → reservierter Befehl `__query__` in der CommandQueue → `on_query()` im Plugin → Antwort per `query-response`; optionale `"queries"`-Deklaration, `504 PLUGIN-0018`/`502 PLUGIN-0019`, Helper `self.query_plugin()`; Referenz death-counter; Discovery via `GET /plugins/queries` | Request/Response zwischen Extensions; strukturierte serverseitige Abfragen möglich |
> | *(aktuell)* | **Hook-Event-Zugang**: `api.register_event(pattern, fn)` (Patterns wie Plugins) mit Bridge-Fan-Out im Hintergrund-Executor; `api.publish_event(type, data)` mit neuer Permission `events` und Namespacing-Zwang (`<hook>.*`) gegen Event-Fälschung | Hooks sind jetzt vollwertige Ereignis-Erweiterungsebene |
> | *(aktuell)* | **Prozess-Sandbox-Profile**: Built-in-Profile `light`/`moderate`/`strict` in `core/sandbox.py`; global wählbar via `plugin_sandbox.profile`, pro Plugin überschreibbar via `"sandbox_profile"` im plugin.json; Legacy-Rohwerte bleiben Fallback | Sandbox ist ohne Hand-Tuning nutzbar |
> | *(aktuell)* | **Graceful Shutdown für Plugins**: `BasePlugin.on_stop()`-Vertrag — Disable/Restart/Unregister liefern das reservierte Kommando `__shutdown__` über die CommandQueue (erreicht nie User-Handler), der Polling-Loop ruft `on_stop()` auf und beendet den Prozess sauber; `atexit`-Fallback in `run()`; Routen warten ~1 s Schonfrist vor dem harten Stoppsignal | Plugins können Queues flushen und Zustand persistieren statt hart gekillt zu werden |
> | *(aktuell)* | **Hook-Unload-Lifecycle**: neue Lifecycle-Ebene `"unload"` via `api.on_unload(fn)`; Callbacks laufen beim Runtime-Reload/Entladen **vor** dem Löschen aller Registrierungen (Ressourcen freigeben) | Hooks haben einen definierten Teardown-Punkt |
> | *(aktuell)* | **Hook-Timer**: `api.register_timer(interval, fn)` — periodische Arbeit ohne `threading`-Import auf dem gemeinsamen Scheduler-Thread des Loaders (Missed-Ticks werden übersprungen, Exceptions isoliert als neuer Code `HOOK-0010`); Scheduler startet/stopt mit dem Hook-Lifecycle | Zeitbasierte Hook-Klassen (Aggregatoren, Debouncer, geplante Prüfungen) sind ohne Plugin-Umweg möglich |
> | *(aktuell)* | **Generischer Event-Ingest**: `POST /api/v1/events/ingest` publiziert ein namespaced Event mit freier Payload auf den Bus **und** löst optional im selben Aufruf eine actions.mca-Triggerkette aus (`trigger`/`user`/`gift_id`/`gift_name`, ohne Debounce, mit History); dokumentiert in ch03-04 (EN+DE) | Ein strukturierter Inbound speist Bus UND Trigger-Welt — Grundlage für Game-Connector/OBS/Automation |
> | *(aktuell)* | **Event-Namespace-Schutz auf der API**: `POST /events` lehnt die reservierten Kernfamilien `tiktok.*`/`minecraft.*` ohne Header `X-T2M-Source: bridge` ab (`403`, neuer Code `API-0009`); Bridge sendet den Header in allen Publishern | Plugins können Kern-Events nicht mehr fälschen — dieselbe Garantie, die Hooks schon auf HookAPI-Ebene hatten |
> | *(aktuell)* | **Permission-Modell für Plugins (opt-in)**: `permissions` in plugin.json (`store`, `network`, `plugins`, `events`) wirkt als Whitelist auf die BasePlugin-API-Oberfläche (`api_*`, `store_*`, `send_command`/`query_plugin`, neues `publish_event`); fehlt das Feld, läuft das Plugin unbeschränkt (rückwärtskompatibel); Verweigerung = `PLUGIN-0020` + sicherer Fallback; eigene Kernkanäle (Polling, Heartbeat, Overlay/Dashboard-Registrierung, `push_state`) bleiben ungesperrt; Feld auch im `PluginManifest`/Registry-Modell | Konsistentes Berechtigungsmodell über beide Erweiterungsebenen; Deklaration dokumentiert Absichten und begrenzt die Angriffsfläche |
> | *(aktuell)* | **Eigene Endpunkte pro Plugin (generisches RPC)**: `POST /plugins/{name}/rpc` (`method`/`path`/`body`/`timeout`) stellt REST-artige Aufrufe als reserviertes Kommando `__rpc__` zu und antwortet über den Query-Response-Kanal (Korrelations-IDs, 504/502 wie Queries); BasePlugin-Seite ist der überschreibbare Vertrag `on_rpc(method, path, body)` | Jede Erweiterung hat eine eigene REST-Oberfläche ohne Server-Änderungen — Dashboard-Callbacks, Webhooks in Plugins und reiche Interaktionen passen nicht mehr ins Command-Schema |
>
> Weiterhin offen: nichts aus dieser Liste.

---

## Systemüberblick (verifiziert)

TikTok2Mc ist eine Multi-Prozess-Anwendung:

| Prozess | Start | Rolle |
|---|---|---|
| **Supervisor** | `start.exe` → `src/python/start.py` | Hostet die FastAPI **im eigenen Prozess** (uvicorn-Task, Port 29185), startet Bridge/GUI/Plugins als `subprocess.Popen`, überwacht Signal-Dateien in `core/runtime/` |
| **Bridge** | Subprozess (`main.py`) | TikTokLive-Verbindung, Trigger-Engine-Aufrufe, RCON-Worker, Hook-Loader, Flask-Webhook (Port ~29188) |
| **API-Server** | im Supervisor-Prozess | EventBus, CommandQueue, Event-Command-Mapper (ECM), Plugin-Registry/Watcher, Overlays, SSE/WebSocket fürs GUI |
| **Plugins** | eigene Subprozesse | Kommunizieren **ausschließlich per HTTP** mit der API |
| **Hooks** | **kein eigener Prozess** | Werden beim Bridge-Start in den Bridge-Prozess geladen |

Zentrale Konsequenz dieses Designs: `event_bus` und `command_queue` (`core.api.eventbus` bzw. `core.api.plugin_overlay`) existieren **pro Prozess je einmal**. Alles, was der Bridge-Prozess lokal aufruft, erreicht den API-Prozess nicht — und umgekehrt. Das ist der rote Faden mehrerer kritischer Befunde (siehe „Kritische Befunde & Inkonsistenzen").

---

## Hook-System — kritische Analyse

### Funktionsweise
- Discovery über `src/hooks/*/hook.json` sowie mit Plugins gebündelte Hooks; AST-Statische Prüfung der Imports (`core.hook_loader.ALLOWED_IMPORTS`): **nur** `time`, `random`, `logging`, `json`, `urllib`, `requests` plus `core.hook_api` / `core.plugin_config`.
- Ein Hook implementiert `register(api: HookAPI)` und registriert benannte Actions: `api.register_action(name, fn)`. Diese landen im globalen Dict `HOOK_ACTIONS` (erstes Registrieren gewinnt, kein Unregister).
- Ausführung: Eine Zeile `trigger:$mein_hook` in `data/actions.mca` ruft die Action synchron (via `asyncio.to_thread`) während des Trigger-Dispatch auf.
- Handler-Signatur: `(user, trigger, context)` — **[✅ ERLEDIGT: strukturierter `context` als `HookContext`]** Die Event-Quellen (Gift/Follow/Like/Kommentar/Join/Share/Webhook) bauen einen strukturierten Kontext (`event`, `source` + ereignisspezifische Keys wie `gift_name`/`streak`/`combo`, `comment`/Rollen-Flags, Like-Milestone-Daten), der an jede Hook-Action als drittes Argument übergeben wird; Details in Dev-Book ch04-03. `user` ist **immer** der reine Username-String — der frühere Kommentar-Dict-Sonderfall (`{user, comment}`) ist aufgelöst, der Kommentartext lebt ausschließlich im Kontext.
- Verfügbare Fähigkeiten via `HookAPI`: `rcon_enqueue`, `enqueue_trigger` (max. Ketten­tiefe 3, Banliste für `tiktok`/`connect`/`disconnect`), `send_overlay_text` (HTTP), `log`, Config-Kopie (`get_hook_config`, `config`), `get_valid_functions`.

### Stärken
1. **Geringste Latenz aller Erweiterungsarten:** in-process, kein HTTP-Hop, direkt im Trigger-Pfad.
2. **Robust isoliert:** Handler laufen im Executor-Thread; Exceptions werden vom CrashManager gemeldet, ohne die Bridge zu töten.
3. **Kleine, prüfbare Angriffsfläche:** Import-Whitelist + Manifest (`min_api_version`, `depends_on` vorhanden).
4. **Vollzugriff auf die Kernaktionen**, die auch `.mca`-Zeilen haben (`enqueue_trigger` = beliebige weitere Triggerketten).

### Schwächen / harte Grenzen
1. ~~**Kein Veto**~~ **[✅ ERLEDIGT — `54fdb78`]** Rückgabewerte des Handlers werden jetzt ausgewertet: `False` bricht die Restkette ab (spätere `$`-Actions, Overlay, Vanilla, RCON, Shell), `None`/`True` verhält sich wie bisher (rückwärtskompatibel). Damit sind Filter-/Moderations-Gates möglich.
2. ~~**Kein Ereigniszugang:** Hooks können nur durch `$`-Zeilen in `actions.mca` feuern. Es gibt kein `subscribe(event)` — Reaktion auf `tiktok.gift` & Co. nur über den Umweg einer `.mca`-Zeile.~~ **[✅ ERLEDIGT]** `api.register_event(pattern, fn)`: Patterns wie bei Plugins (`"tiktok.gift"`, `"tiktok.*"`, `"*"`); Fan-Out erfolgt in der Bridge beim Publish (`_notify_hooks_of_event`, Hintergrund-Executor — blockiert nie Trigger-/TikTok-Threads), Exceptions pro Hook isoliert (HOOK-0008); Teil des Runtime-Reloads (`clear_hook_registrations`). Tests in `tests/test_core/test_hook_events.py`; Doku ch04-03 (EN+DE).
3. ~~**Kein Lifecycle:** Keine Callbacks für Stream-Start/-Ende, keine Timer/Hintergrundtasks, keine Initialisierung mit garantiertem Aufrufkontext jenseits von `register()`.~~ **[✅ ERLEDIGT: `api.on_live_start/on_live_end` + `register_lifecycle` in HookAPI, gefeuert aus Bridge on_connect/on_live_end]**
4. ~~**Kein Runtime-Reload:** Aktivieren/Deaktivieren erfordert Bridge-Neustart. Die Reload-Signal-Dateien decken nur config/actions/comment_commands/chatbot ab — nicht Hooks.~~ **[✅ ERLEDIGT: `reload_hooks` Signal + Bridge-Watcher + `_request_hook_reload` in enable/disable/config-PUT + `POST /reload hooks=true`; Full-Reload aller Hooks]**
5. **Whitelist schneidet legitime Anwendungsfälle ab:** keine `os`/`subprocess`/Audio-/DB-Libs. Gleichzeitig erlaubt `requests` vollen Netzwerkzugriff aus dem Bridge-Prozess — das Sicherheitsversprechen ist also asymmetrisch. **[TEILWEISE gelöst]** Prozess-Sandbox-Profile sind jetzt verfügbar (`light`/`moderate`/`strict`, global + pro Plugin) — aber opt-in und die Import-Whitelist bleibt unverändert.
6. ~~**Keine Zustands-/Persistenzdienste**~~ **[✅ ERLEDIGT — `022fe7a`]** Hooks nutzen die namespaced Persistenz-API per HTTP (`urllib`/`requests` aus der Whitelist): eigener Namespace unter `data/plugin_data/<hook-name>.json`, dokumentiert in Dev-Book ch04-03.
7. ~~**Kein Publish:** Ein Hook kann nichts auf den EventBus legen; Kommunikation mit Plugins wäre nur über den undokumentierten Direktaufruf der REST-API per `requests` möglich.~~ **[✅ ERLEDIGT]** `api.publish_event(type, data)` (neue Permission `events`): POST an `/api/v1/events`, Typ **muss** unter dem eigenen Hook-Namen namespaced sein (`"<hook>.<ding>"`) — Fälschung von Kern-Events wie `tiktok.gift` wird abgelehnt. Plugins konsumieren die Events via `event_subscriptions` wie eingebaute.

**Fazit Hook-System:** Als schneller, einfacher Aktions-Erweiterungspunkt gut gelungen; als *Ereignis*-Erweiterungsebene jetzt **vollwertig** (Veto, strukturierter Kontext, `register_event`-Abos, `publish_event` mit Namespacing-Zwang) — damit sind auch datengetriebene Hooks (Combos über Events statt `.mca`-Umweg) direkt umsetzbar.

---

## Plugin-System — kritische Analyse

### Funktionsweise
- Subprozess pro Plugin, gesteuert über Signal-Dateien `core/runtime/plugin_{action}_{name}`; Registry persistiert in `data/api_plugin_registry.json`; Watcher pollt alle 10 s auf neue Verzeichnisse.
- `BasePlugin` bietet: `PLUGIN_NAME`, Pflicht-Override `get_overlay_html()`, Schema-getriebene Config (`config_schema` in `plugin.json` → GUI-Editor), thread-safe `state`/`push_state()` (SSE an Overlay-Seite), Command-Long-Poll (`GET /plugins/{name}/commands?wait=1`), Tick-Thread (1 s), Heartbeat (30 s), `api_post`/`api_get` Helfer.
- Manifest-Felder: `capabilities`, `depends_on` (Topo-Sort beim Launch), `event_subscriptions`, `emitted_events`, `accepted_commands` (GUI-Reaktionskatalog), Plattform-/Update-Metadaten.
- Ereignispfad 2 (funktional): ECM liest `defaults/event_commands.yaml` + `data/event_commands.yaml` und mappt **API-Bus**-Events auf Plugin-Kommandos.
- Kommentar→Plugin: ausschließlich über Gruppen in `data/comment_commands.yaml` (`handler: plugin`, `plugin_name`, Präfix **muss nicht-leer sein**, Befehls-Whitelist, Rollenfilter, Cooldowns).

### Stärken
1. **Sauberste Isolation im Projekt:** eigener Prozess, Sandbox-Ressourcenlimits vorhanden (Standard: aus), Crash eines Plugins berührt Bridge/API nicht.
2. **Reifes Fundament:** Registry + Health-Monitor + Heartbeats, Dependency-Auflösung, schema-validierte Konfiguration mit GUI, Overlay-Kanal mit State-SSE, Token-Verschlüsselung via `secure_storage` (vom Spotify-Plugin vorgemacht).
3. **Volle Python-Freiheit im Plugin:** alle Bibliotheken nutzbar (Spotify zeigt OAuth + externe REST-API produktiv).
4. **Long-Poll (`wait=1`)** macht die Kommando-Zustellung near-realtime trotz HTTP.
5. **Loser Kopplungsgrad über Events:** Plugins publishen eigene Events (`POST /events`), andere konsumieren sie via ECM — Timer/Deathcounter zeigen das Muster.

### Schwächen / harte Grenzen
1. ~~**Der dokumentierte Ereignispfad 1 ist tot**~~ **[✅ ERLEDIGT — `f409595`]** Der Bridge published echte `tiktok.*`-Events per HTTP (`POST /api/v1/events`, gleiches Muster wie `minecraft.*`) auf den API-Bus; der neue **PluginEventBridge**-Service (API-Prozess) matcht `event_subscriptions` (exakt + `prefix.*`) und legt `tiktok_event`-Kommandos in die CommandQueue, die Plugins pollen. Integrationstest deckt den Pfad ab.
2. ~~**Kommentarfeed nicht abonnierbar / `comment_handler` nur Doku**~~ **[✅ ERLEDIGT — `f409595`]** `comment_handler: {prefix, enabled}` ist implementiert: Bei `tiktok.comment` wird ein `comment`-Kommando mit `{text, username}` (Präfix gestript, Default `$`) zugestellt; dokumentiert in ch03-05/ch03-01.
3. ~~**Fire-and-forget überall:** `send_command` hat keine Antwortwarteschlange, keine Korrelations-IDs; Request/Response zwischen Extensions ist nicht modelliert.~~ **[✅ ERLEDIGT — Plugin↔Plugin-Queries]** `POST /plugins/{name}/query` mit Korrelations-ID: Zustellung als reservierter Befehl `__query__` über die CommandQueue, BasePlugin routet an `on_query()` und POSTet die Antwort zurück (`POST /plugins/{name}/query-response`); optionale Manifest-Deklaration `"queries": [...]` (unbekannte Queries → sofort 404); Timeouts `504 PLUGIN-0018`, Handler-Fehler `502 PLUGIN-0019`; Helper `self.query_plugin(target, query, args)`. Referenzimplementierung: death-counter (`"deaths"`). Tests in `tests/test_api/test_plugin_query.py`.
4. **Keine eigenen Endpunkte:** Das REST-Interface pro Plugin ist fix (commands/overlay/stream/state/config + dashboard/data/query). Frei definierte Abfrage-Routen sind nicht möglich. **[WEITGEHEND gelöst]** Interaktive UIs haben eine eigene Dashboard-Seite, und strukturierte serverseitige Abfragen laufen über den Query-Kanal (`on_query` + `"queries"`-Deklaration) — nur frei wählbare URL-Schemata/Payload-Formate bleiben Rest.
5. ~~**Keine Dashboard-Integrationspunkte:** Plugins bekommen keine Tabs/Routen im Web-Dashboard — nur Overlay-Seiten und Schema-Config-Seiten.~~ **[✅ ERLEDIGT]** Manifest-Feld `dashboard_ui` + `get_dashboard_html()`/`register_dashboard()`; API serviert `GET /plugins/{name}/dashboard`; das Web-Dashboard erzeugt dynamische Sidebar-Tabs mit Iframe (lazy). Referenzimplementierung: death-counter.
6. ~~**Persistenz DIY und kollisionsgefährdet**~~ **[✅ ERLEDIGT — `022fe7a`]** Namespaced Persistenz-API: je Extension eine JSON-Datei unter `data/plugin_data/<name>.json`; REST (`GET/PUT/DELETE /plugins/{name}/data[/{key}]`) + `BasePlugin.store_get/store_set/store_delete/store_all`.
7. **`capabilities` rein informativ:** Nirgends wird geprüft; kombiniert mit standardmäßig deaktivierter Sandbox ist das Isolationsmodell opt-in. **[TEILWEISE gelöst]** Sandbox-Profile (`light`/`moderate`/`strict`) machen das Aktivieren ohne Hand-Tuning trivial — Standard bleibt weiterhin aus (bewusste Entscheidung); `capabilities` bleiben Discovery-Tags.
8. ~~**Undokumentierte Hintertüren:** `POST /api/v1/rcon/command` (generischer RCON-Endpunkt des API-Prozesses) umgeht Queue/Throttling der Bridge — nützlich, aber weder dokumentiert noch autorisiert.~~ **[✅ ERLEDIGT]** Endpunkt ist der Transport der Dashboard-Konsole; neu: Config-Gate `rcon.http_command_api` — **standardmäßig deaktiviert** (`false`, Sicherheits-/Stabilitäts-Standard), Konsole-Tab benötigt explizite Aktivierung; bei Deaktivierung antwortet die Route mit `403 MC-0012` (neuer Error-Code), Queue-Pfad bleibt unangetastet. Dokumentiert in ch03-04 (EN+DE) inkl. expliziter Warnung vor Queue/Throttling-Bypass; Tests in `tests/test_api/test_rcon_gate.py`.

**Fazit Plugin-System:** Architektonisch die richtige Ebene für alles Schwergewichtige (Threads, Audio, OAuth, Persistenz). **Der Ereigniseingang funktioniert jetzt** (echte Events + Kommentarfeed), Persistenz ist als namespaced Service vorhanden, mit den Dashboard-Tabs haben Plugins einen eigenen UI-Ort im Web-Dashboard und mit dem Query-Kanal können Erweiterungen serverseitig Daten von Plugins abfragen — verbleibende Grenze ist nur noch die Freiheit eigener URL-Schemata/Payload-Formate.

---

## Kern-Schnittstellen & Datenflüsse

### Original-Flussdiagramm (Stand **vor** Fix `f409595`)

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

### Aktueller Fluss (seit `f409595`)

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

## Kritische Befunde & Inkonsistenzen

| Befund | Beleg | Wirkung | Status |
|---|---|---|---|
| **Cross-Process-Defekt:** `_event_bridge_worker` legt `tiktok_event`-Kommandos in die Bridge-lokale `CommandQueue`; Plugins pollen aber die Queue des API-Prozesses. | `main.py` L47/L1197/L1337 vs. `plugin_overlay.py` + `base_plugin._API_BASE` | Dokumentierter „Pfad 1" (`event_subscriptions`) lieferte im Betrieb **nie** etwas aus | **[✅ ERLEDIGT `f409595`]** Bridge published per HTTP; PluginEventBridge enqueued in die API-Queue |
| **Echte `tiktok.*`-Events erreichen den API-Bus nie.** Nur Test-Trigger erscheinen dort (direkter Publish in `routes/triggers.py`). | grep `publish` in `main.py` vs. `routes/triggers.py` L55–57/85/116 | ECM-Mappings für `tiktok.comment` etc. feuern bei **Testkommentaren, aber nie bei echten** — tückische Inkonsistenz; GUI-Livefeed/TikTokLiveTracker sehen Realverkehr nicht | **[✅ ERLEDIGT `f409595`]** echte Events landen auf dem Bus (`source: "bridge"`) |
| **`comment_handler` dokumentiert, nicht implementiert.** | Dev-Book ch03-05/ch03-02 vs. grep in `src/**.py`: 0 Treffer | Doku verspricht Feature, das es nicht gibt | **[✅ ERLEDIGT `f409595`]** implementiert (`CommentHandlerConfig`, Prefix-Strip, Default `$`) |
| Kein shipped Plugin nutzt `event_subscriptions`; keine Tests zum alten `_event_bridge_worker`. | grep in `src/plugins`, `tests` | Defekt blieb unbemerkt | **[✅ ERLEDIGT `54fdb78`]** Integrationstest + Unit-Tests für die Zustellung (`test_plugin_event_bridge.py`) |
| **Hook-Kontext immer `{}`**, keine strukturierten Ereignisdaten. | `main.py` (`execute_global_command(..., {})`) | Hooks können nicht datengetrieben arbeiten | **[✅ ERLEDIGT]** `_make_hook_context` an allen Event-Quellen, 4-Tupel in der Trigger-Queue, Kontext an Hook-Actions; `enqueue_trigger(context=...)` für Verkettung |
| **Kein Veto-/Rückgabevertrag** für Hook-Actions. | `hook_api.execute_global_command` ignoriert Rückgaben | Filter/Moderation als Hook unmöglich | **[✅ ERLEDIGT `54fdb78`]** Veto-Vertrag: `False` = Restkette abbrechen |
| ~~Minecraft-Semantik im generischen Webhook: `player_death`/`player_respawn` pausieren die MC-Queue **unabhängig von der Quelle**.~~ | Bridge `/webhook`-Handler | ~~Fremdspiel, das gleichnamige Events sendet, verfälscht das Verhalten~~ | **[✅ ERLEDIGT]** Neuer Config-Gate `minecraft_server_api.queue_pause_on_death` (Default `true`, rückwärtskompatibel): ohne Opt-in keine Queue-Pause; `minecraft.{event}` wird weiterhin generisch publiziert, Semantik liegt in `_apply_mc_queue_semantics()` (unit-testbar). |
| ~~`capabilities` werden nicht erzwungen; Sandbox default aus; Hooks dürfen `requests`.~~ | `sandbox.py`, `hook_loader.py` | ~~Isolation ist deklarativ, nicht wirksam~~ | **[✅ ERLEDIGT]** API-Ebene: `permissions`-Feld (`rcon`/`triggers`/`overlay`/`store`/`network`/`events`) wird pro Hook-View erzwungen (`HOOK-0009`, sicherer Rückgabewert); `capabilities` bleiben Discovery-Tags. Prozessebene: Sandbox-Profile verfügbar. Direkter `requests`/urllib-Netzzugriff bleibt erlaubt (dokumentiert). |

---

## Ideenbewertung: TTS zum Vorlesen von Kommentaren

### Anforderungsprofil
Alle Kommentare (Text, Nutzer, ggf. Rollen) empfangen → TTS-Engine (lokal z. B. pyttsx3/SAPI, oder Cloud) → Wiedergabe mit Warteschlange, Priorität, Cooldown, Mute-Schalter, Config-UI.

### Passende Ebene
**Plugin** — Audio-Playback blockiert, braucht eigene Threads/Queue, Persistenz und Schema-Config. Ein Hook scheidet praktisch aus: Die Import-Whitelist verbietet `pyttsx3`/Audio-Libs ebenso wie `subprocess` (lokales TTS-Programm starten).

### Wie kommt das Plugin an ALLE Kommentare?
| Weg | Bewertung |
|---|---|
| `comment_commands.yaml`-Gruppe | ❌ Präfix muss **nicht-leer** sein (`startswith`-Check) — „alle Kommentare" nicht abbildbar; Mechanismus ist für Befehle, nicht für einen Feed gedacht |
| `event_subscriptions: ["tiktok.comment"]` | ✅ funktioniert seit `f409595` (PluginEventBridge); Text liegt als `data.comment` im Event |
| `comment_handler: {prefix, enabled}` | ✅ neu implementiert (`f409595`) — präfixfreier Kommentarfeed als `comment`-Kommando `{text, username}` |
| ECM-Mapping `tiktok.comment → tts/say` | ✅ feuert jetzt auch bei **echten** Kommentaren |
| Hook nach `comment:`-Zeile in actions.mca | ⚠️ Text wäre via Kontext erreichbar, aber TTS technisch whiteliste-bedingt unmöglich |

### Urteil
Original-Urteil war **„Nur mit strukturellen Änderungen"** — der fehlende Kommentar-*Eingang* war der Blocker.

**[AKTUALISIERT]** Seit `f409595` lautet das Urteil: **„Ja"** — Plugin mit `event_subscriptions: ["tiktok.comment"]` oder `comment_handler` empfängt alle Kommentare; die TTS-Logik selbst ist reines Plugin-DIY (Queue, Cooldowns, Engine-Wahl). Persistenz für Mute-Listen etc. über die namespaced Store-API.

---

## Ideenbewertung: Spiele-Integration ohne RCON

### Inbound (Spiel → TikTok2Mc)
| Kanal | Funktioniert? | Probleme |
|---|---|---|
| Bridge `/webhook` (`minecraft.{event}` → API-Bus → ECM → Plugins) | ✅ heute | Namen sind Minecraft-brandet; `player_death` pausierte die echte MC-Queue (jetzt per Config-Gate lösbar) — Namenskollision mit Seiteneffekten; separates Auth-/Port-Thema |
| Bridge `/custom_trigger` | ✅ heute | Führt nur **vordefinierte** actions.mca-Trigger aus; Payload nur `user`-String; keine strukturierten Daten; undokumentierter Port |
| API `POST /events` | ✅ heute | Erreicht Plugins (via ECM), aber **nie actions.mca** — der Bus liegt im anderen Prozess als die Trigger-Queues |
| API `POST /triggers/execute` | ✅ heute | 1,5-s-Debounce (Singleton, geteilt mit GUI-Tester), nur `user`/`gift_id`, semantisch ein Testendpunkt |
| API `POST /triggers/dispatch` **[NEU `8ea4109`]** | ✅ heute | Kein Debounce, kein Test-Flag, voller Payload (`trigger`/`user`/`gift_id`/`gift_name`) — der saubere Inbound für externe Systeme |

### Outbound (TikTok2Mc → Spiel)
- `&`-Shell-Zeilen: Prozess-Spawn pro Trigger, kein Protokoll, kein Lifecycle.
- `$`-Hook/Skript oder Plugin mit `requests`/Websockets: technisch frei, aber **alles DIY** — Reconnect, Auth, Health, Retry, Circuit-Breaker. Ein wiederverwendbares Muster (Circuit-Breaker) existiert intern nur im Overlay-Manager.

### Urteil
**Einzelintegration als Plugin: „Ja, mit Einschränkungen"** (Transport komplett DIY, Inbound nur über Minecraft-branded Webhook mit Kollisionsrisiko).
**Eine generische „Game-Connector"-Architektur: „Nur mit strukturellen Änderungen":** es fehlen (a) ein typisierter, generischer Inbound, der sowohl Bus **als auch** Trigger-Engine speist, (b) die Entkopplung der Minecraft-Spezialfälle vom Webhook, (c) ein Outbound-Kanal-Konzept (konfigurierbare Ziele inkl. Retry/Breaker).

**Wiederverwendbare Bausteine:** generischer Inbound-Endpoint (Trigger-Dispatch ✅ vorhanden, Outbound-Channels ✅ `4aa4711`) — identisch nützlich für Discord-Notifier, Home-Assistant, OBS-Steuerung usw.

---

## Eigene Hook-Ideen (bewertet)

### Anti-Spam-/Rate-Limit-Gate (Veto-Hook)
- **Idee:** Hook registriert `$gate_<trigger>` als erste Zeile jeder Kette; zählt Events pro Nutzer/Fenster und soll bei Überschreitung die Restkette verwerfen.
- **Technik:** in-process State, `time`/`random` aus Whitelist — Zähllogik trivial.
- ~~**Blocker:** kein Veto-Vertrag.~~ **[GELÖST `54fdb78`]**
- **Original-Urteil:** „Nur mit strukturellen Änderungen" (Veto-Semantik fehlte).
- **[AKTUALISIERT] Urteil: „Ja"** — Handler gibt `False` zurück, Restkette wird verworfen; Beispiel in Dev-Book ch04-03 (EN+DE).

### Schimpfwort-Moderator für Kommentarzeilen
- **Idee:** `$profanity_check` vor Kommentar-Reaktionen; soll unangebrachte Kommentare von allen Folgeaktionen ausschließen.
- **Technik:** Text liegt strukturiert im Kontext (`comment` + Rollen-Flags), Regex-Listen in hook.json-Config ladbar.
- ~~**Blocker:** Veto-Vertrag fehlte~~ **[GELÖST `54fdb78`]**; ~~strukturierte Rollen-Flags im Kontext fehlen~~ **[GELÖST: strukturierter Kontext liefert `is_moderator`/`is_super_fan`/`in_fanclub`]**.
- **Original-Urteil:** „Nur mit strukturellen Änderungen" (Veto + Kommentar-Datenvertrag).
- **[AKTUALISIERT] Urteil: „Ja"** — Veto funktioniert, Kommentartext und Rollen-Flags liegen strukturiert im Kontext (`comment`, `is_moderator`, `is_super_fan`, `in_fanclub`).

### Gift-Combo-Detektor (Milestone-in-Fenster)
- **Idee:** Erkennt „X gleiche Gifts in Y Sekunden durch Nutzer Z" und stößt Bonus-Trigger an.
- **Technik:** Zeitfenster-Logik ideal für in-process Hook; Auslösen per `enqueue_trigger` vorhanden; Beispiel in Dev-Book ch04-03 (EN+DE).
- ~~**Blocker:** Hook sah **keine** Giftmetadaten (Name, Anzahl, Combo-Flag) — `context={}`~~ **[GELÖST: strukturierter Kontext]** — `context` enthält jetzt `event: "gift"`, `gift_name`, `gift_id`, `streak` (Combo-Länge), `combo`; Bonus-Ketten können ihre eigenen Daten per `enqueue_trigger(context=...)` mitnehmen.
- **Original-Urteil:** „Aktuell nicht sinnvoll möglich"; nach Einführung eines strukturierten Action-Kontexts: „Ja".
- **[AKTUALISIERT] Urteil: „Ja"** — alle benötigten Eingabedaten liegen im Kontext.
- **Lehrstück:** zeigt exemplarisch, dass dem Hook-System der **Datenvertrag** fehlte, nicht die Rechenlogik.

---

## Eigene Plugin-Ideen (bewertet)

### Discord/Webhook-Notifier
- **Idee:** Mappt Bus-Events (Follows, Milestones, Serverstatus) auf Discord-Webhooks; Template-Nachrichten, Rate-Limit, kanalbezogene Routen.
- ~~**Blocker:** echte `tiktok.*`-Events fehlen~~ **[GELÖST `f409595`]**
- **Original-Urteil:** „Ja, mit Einschränkungen".
- **[AKTUALISIERT] Urteil: „Ja"** — alle `tiktok.*`-Events sind auf dem API-Bus; ECM-Mapping + `requests`, Tokens via `secure_storage`. Alternativ existiert der generische Notification-Dispatcher mit eingebautem Discord-Kanal.

### Scheduler/Cron für actions.mca
- **Idee:** Zeitgesteuerte Trigger („alle 30 min `bonus_drop`", tägliche Reset-Aktionen) mit Cron-Syntax in plugin.yaml.
- ~~**Caveats:** Debounce des geteilten Singletons, Payload nur `user`/`gift_id`, Endpunkt semantisch „Test"~~ **[GELÖST `8ea4109`: `POST /triggers/dispatch`]**
- **Original-Urteil:** „Ja, mit kleineren Erweiterungen".
- **[AKTUALISIERT] Urteil: „Ja"** — Scheduler-Plugin ruft `/triggers/dispatch` auf eigenem Zeitplan; kein Kollisionsrisiko mit dem GUI-Tester mehr.

### Viewer-Leaderboard mit Persistenz
- **Idea:** Aggregiert Gifts/Follows/Kommentarpunkte pro Viewer, SQLite/JSON, Overlay-Top-10, saisonale Resets.
- **Original-Blocker-Kette:** (1) echte Gift/Follow-Events erreichen kein Plugin; (2) Persistenz DIY im geteilten `data/`; (3) Abfragen/Sortierungen können nicht serverseitig beantwortet werden — keine eigenen REST-Routen; Overlay-HTML bleibt statisch+SSE; Dashboard-Tab unmöglich.
- **Status:** (1) ✅ `f409595`, (2) ✅ `022fe7a` (namespaced Store), (3) ✅ **erledigt** (Dashboard-Tab mit State-SSE + Query-Kanal für serverseitige Top-10-Abfragen).
- **Original-Urteil:** „Nur mit strukturellen Änderungen".
- **[AKTUALISIERT] Urteil: „Ja"** — Aggregation + Persistenz sind Plugin-DIY mit Board-Mitteln; das Dashboard/Overlay zeigt die Top-10 live per State-Push, externe Abfragen laufen über `on_query`.

---

## Noch fehlende Bausteine für zukünftige Flexibilität

### Zwingend erforderlich (Pflicht — Defekte/blocking) — **[ALLE ERLEDIGT]**
1. ~~**Prozessübergreifende Ereignisweiterleitung Bridge → API**~~ **[✅ `f409595`]** Bridge published echte `tiktok.*`-Events per HTTP auf den API-Bus; neuer **PluginEventBridge**-Service matcht `event_subscriptions` und enqueued in die API-CommandQueue. Repariert die beiden Zustellungsdefekte.
2. ~~**Entscheidung zu `comment_handler`**~~ **[✅ `f409595`]** implementiert (`prefix`/`enabled`, Default `$`) statt entfernt.
3. ~~**Tests für die Ereigniszustellung**~~ **[✅ `54fdb78`]** Integrationstest (echter EventBus → Bridge-Loop → echte CommandQueue) + Unit-Tests in `tests/test_core/test_plugin_event_bridge.py`.

### Sinnvoll (hoher Nutzen für mehrere Ideen)
4. ~~**Veto-/Rückgabevertrag für Hook-Actions**~~ — **[✅ ERLEDIGT]** Veto-Vertrag (`54fdb78`: `False` = Restkette abbrechen) **plus strukturierter `context` als `HookContext` (dict-Subklasse mit fail-fast Attribut-Zugriff)**: Event-Quellen bauen `_make_hook_context(...)` (gift/follow/like/comment/join/share, `source: tiktok|webhook|hook`), die Trigger-Queue trägt 4-Tupel `(trigger, user, depth, context)`, `execute_global_command` übergibt ihn unverändert an jede Hook-Action; `HookAPI.enqueue_trigger(context=...)` propagiert Daten in Folgetriggers. **Breaking seit v1.0.0:** `user` ist immer ein String (Kommentar-Dict-Sonderfall entfernt), `chain_depth` wird nicht exponiert. Unlockt den Gift-Combo-Detektor endgültig + Rollenfilter für den Schimpfwort-Moderator.
5. **Hook-Runtime-Reload/Lifecycle:** Enable/Disable ohne Bridge-Restart (Reload-Signal-Mechanik erweitern); `on_live_start/end`-Callbacks. **[✅ ERLEDIGT (Commits: HookAPI Lifecycle + Reload + Bridge Watcher + API Endpoints)]**
6. ~~**Generischer Outbound-Kanal**~~ — **[✅ `4aa4711`]** `OutboundDispatcher` im API-Prozess: EventBus → konfigurierbare HTTP-Channels (`outbound:` in config.yaml; Formate `raw`/`discord`, Event-Patterns wie `event_subscriptions`), Retry + Circuit-Breaker pro Channel (`OverlayClient` wiederverwendet), Health-Lifecycle; REST `GET /outbound/channels` (URLs maskiert) + `POST /outbound/channels/{name}/test` (reine Probe); dokumentiert in ch03-04 (EN+DE). Grundlage für Notifier/Game-Connector geschaffen.
7. ~~**Trigger-Zugriff für Erweiterungen**~~ — **[✅ `8ea4109`]** `POST /api/v1/triggers/dispatch`: kein Debounce, definierter Payload (`trigger`/`user`/`gift_id`/`gift_name`), History-Aufzeichnung; dokumentiert in ch03-04 (EN+DE). Grundlage für den Scheduler geschaffen.
8. ~~**Request/Response zwischen Extensions:** Korrelations-IDs/Antwortqueue statt reinem Fire-and-forget.~~ **[✅ ERLEDIGT]** Zwei Stufen: `api.request(path, payload=None, method=None, timeout=5)` im HookAPI (synchroner JSON-Call gegen die Control Plane, geparster Body oder `None`, nie Exceptions; Permission `network`) für Hook→Control-Plane; volle Korrelations-IDs zwischen Plugins über den Query-Kanal (`POST /plugins/{name}/query` + `on_query()`, siehe oben).
9. ~~**Namespaced Persistenz-API pro Plugin/Hook**~~ — **[✅ `022fe7a`]** `PersistenceService` (`data/plugin_data/<name>.json`, atomar), REST `GET/PUT/DELETE /plugins/{name}/data[/{key}]`, `BasePlugin.store_*`-Helper; dokumentiert in ch03-04/ch04-03 (EN+DE).
10. ~~**Capability-Enforcement:** `capabilities` prüfen oder streichen; Sandbox-Profile; Hook-Netzzugriff bewusst entscheiden.~~ **[✅ ERLEDIGT]** API-Ebene: `permissions`-Feld in hook.json wird in den `for_hook()`-Views erzwungen (`HOOK-0009` + sichere Rückgabewerte); `capabilities` bleiben Discovery-Tags. Prozessebene: **Sandbox-Profile jetzt verfügbar** — Built-in-Profile `light`/`moderate`/`strict`, global via `plugin_sandbox.profile` oder pro Plugin via `"sandbox_profile"` im plugin.json (Legacy-Rohwerte als Fallback, `PluginSandbox.from_config/from_profile/resolve_plugin_sandbox`). Direkter Netzzugriff via `requests`/urllib bleibt erlaubt und dokumentiert.

### Nice-to-have (QOL+)
11. ~~Dashboard-UI-Erweiterungspunkte (Tabs/Routen für Plugins)~~ **[✅ ERLEDIGT]** Manifest-Feld `dashboard_ui` (in `GET /plugins` sichtbar); `BasePlugin.get_dashboard_html()`/`register_dashboard()` registrieren die Seite per `POST /plugins/{name}/dashboard-html`, ausgeliefert unter `GET /plugins/{name}/dashboard` (gleiche Origin → relative `/api/v1`-Aufrufe: State-SSE, Commands, Store). Das Web-Dashboard erzeugt dynamische Sidebar-Tabs mit lazy Iframe + „In neuem Tab öffnen"; Tabs nur für aktivierte Plugins. Referenzimplementierung: death-counter (+1/+10/Reset über den Command-Queue-Pfad). Tests: `tests/test_api/test_plugin_dashboard.py`, `templates/gui/tests/plugin-pages.test.js`; Doku ch03-02/ch03-04 (EN+DE). Echte frei definierte REST-Routen pro Plugin bleiben Zukunftsthema.
12. ~~**Einheitliches Event-Schema/-Katalog mit Versionierung; `emitted_events`/`accepted_commands` für Delivery statt nur GUI-Katalog nutzen.~~ **[✅ ERLEDIGT (pragmatisch)]** Katalog-Antwort trägt `CATALOG_VERSION` (`version: 1`); `collect_known_event_keys()` (Core + alle `emitted_events`) dient als Delivery-Registry — unbekannte exakte Subscriptions erzeugen eine Bridge-Warnung (Tippfehler-Schutz, Wildcards ausgenommen); `POST /plugins/{name}/command` warnt bei Kommandos außerhalb der deklarierten `accepted_commands` (warn-only, TTL-Cache, Zustellung bleibt unangetastet). Vollständige Schemata pro Event (Payload-JSON-Schema) bleiben Zukunftsthema.
13. ~~**Notification-Dispatcher (Overlay/Sound/TTS/Discord als austauschbare Kanäle).**~~ **[✅ ERLEDIGT]** `NotificationDispatcher` (`core/api/notification_dispatcher.py`, Singleton) mit Channel-Registry `CHANNEL_HANDLERS` — eingebaut: `log`, `overlay` (direkt via `core.overlay.send_overlay_text`, kein HTTP-Umweg), `sound` (winsound, Windows), `tts` (PowerShell SAPI, Windows-guarded), `discord` (Webhook-POST, maskierte URLs in Logs). REST: `POST /api/v1/notifications` (`{title, body?, level?, channels?}` → `{sent, failed, skipped}`, Fan-out via `asyncio.to_thread` + gather), `GET /notifications/channels`, `POST /notifications/reload`. Config-Abschnitt `notifications:` bewusst **nicht** in `defaults/config.yaml` — Benachrichtigungen sind rein caller-getrieben (Inline-Parameter pro Request); wer will, kann den Abschnitt manuell als Default-Quelle ergänzen. Fehlercodes `NOTIF-0001`/`NOTIF-0002` warn-only — Zustellprobleme werfen nie. Plugins senden via `BasePlugin.api_request("notifications", payload={...})` (Body-Rückgabe, Parität zu `api.request`; `api_post` bleibt als Fire-and-forget-Variante), Hooks über `api.request("notifications", payload=...)` (mit `network`-Berechtigung). **Autarkie-Prinzip:** `channels` akzeptiert zusätzlich ein Mapping `{name: params}` — Inline-Parameter werden über die globale Channel-Config gemischt (Inline gewinnt), ein nur im Request genannter Channel braucht keinen globalen Eintrag; Plugins/Hooks holen alle Versand-Einstellungen aus ihrer eigenen Schema-Config und bleiben damit vollständig self-contained (Enduser konfigurieren im Plugin-GUI-Formular, nie in YAML). TTS als Vollfeature (Queueing, Stimmen) bleibt Plugin-Thema. Dokumentiert in ch03-04 (EN+DE).
14. ~~**Generisches Event-Abo über alle Quellen** (heute: `event_subscriptions` nur für `tiktok.*`, sonst zwingend zentrale ECM-YAML-Handpflege).~~ **[✅ ERLEDIGT]** `event_subscriptions` akzeptiert jetzt **jede** Bus-Quelle (exakt, Prefix-Wildcard oder Catch-all `"*"`); TikTok-Events bleiben beim `tiktok_event`-Vertrag (mit `user`), alle anderen Quellen (`minecraft.*`, `server.*`, Plugin-Events) kommen als neues `bus_event`-Kommando (`event_type` + `data`, kein `user`) in die CommandQueue. ECM bleibt für Aktionsverkettung; Docs ch03-02/ch03-05 (EN+DE) aktualisiert.

---

## Fazit

Die Zwei-Ebenen-Architektur ist im Kern **richtig und durchdacht**: Hooks für schnelle Aktionen im Trigger-Pfad, Plugins für alles Schwergewichtige in Isolation. Das Fundament (Registry, Manifeste, Schema-Config, Health-Monitor, TriggerEngine als Single Source of Truth, secure_storage) ist solide und wiederverwendbar.

Was die versprochene Flexibilität ursprünglich **ausbremste**, waren keine Designfehler, sondern:
1. **Zwei Zustellungsdefekte**, die die dokumentierte Ereignisfähigkeit faktisch abschalteten — mit einem Fix adressierbar;
2. **fehlende Verträge** (Veto, strukturierter Kontext, Request/Response, Persistenz, Outbound), die jede ernsthaftere Idee in DIY-Treibhausarbeit trieben;
3. **Doku-/Code-Drift** (`comment_handler`, tote Pfade), die Vertrauen in die Erweiterungsversprechen untergräbt.

Alle drei Punkte sind inzwischen behoben.

### Umsetzungsstand (August 2026)

**Erledigt:** alle Pflicht-Fixes (Event-Zustellung, `comment_handler`, Integrationstest), Veto-Vertrag, strukturierter Hook-Kontext (`HookContext`), Trigger-Dispatch-Endpoint, namespaced Persistenz-API, generischer Outbound-Kanal (Webhooks/Discord), Hook-Runtime-Reload/Lifecycle, Capability-Enforcement (`permissions`), Request/Response-Helper (`api.request()`), Webhook-Minecraft-Semantik (Config-Gate), generisches Event-Abo (`bus_event`), Event-Katalog-Version + Delivery-Validierung, Dashboard-Tabs für Plugins (`dashboard_ui`/`get_dashboard_html()`), RCON-HTTP-Gate (`rcon.http_command_api`, MC-0012), Plugin-Queries mit Korrelations-IDs (`on_query`/`query_plugin`, PLUGIN-0018/0019), Hook-Event-Zugang (`register_event`-Abos + `publish_event` mit `events`-Permission und Namespacing-Zwang), Prozess-Sandbox-Profile (`light`/`moderate`/`strict`, global + per-Plugin) — sowie aus der Capability-Matrix-Nachfolge: **Graceful Shutdown für Plugins** (`on_stop()` + `__shutdown__`-Kommando + Grace-Period), **Hook-Unload-Lifecycle** (`api.on_unload`), **Hook-Timer** (`api.register_timer`, `HOOK-0010`), **generischer Event-Ingest** (`POST /events/ingest`, Bus + Trigger in einem Aufruf) und **Event-Namespace-Schutz auf der API** (`X-T2M-Source: bridge`, `API-0009`) sowie das **Permission-Modell für Plugins** (opt-in `permissions`-Whitelist auf der BasePlugin-API-Oberfläche, `PLUGIN-0020`, inkl. `publish_event`-Helper; Tests in `test_base_plugin.py::TestBasePluginPermissions`) sowie **eigene Endpunkte pro Plugin** (generischer RPC-Kanal `POST /plugins/{name}/rpc` → `on_rpc()`; Tests in `tests/test_api/test_plugin_rpc.py`, `test_base_plugin.py::TestBasePluginRpc`). Tests: `tests/test_core/test_hook_lifecycle_timers.py`, `tests/test_api/test_events_ingest.py`, Erweiterungen in `test_base_plugin.py`/`test_plugins.py`.

Die Ideen TTS (Kommentar-Vorlesen), Rate-Limit-Gate, Schimpfwort-Moderator, Gift-Combo-Detektor, Discord-Notifier und Scheduler sind damit **praktisch umsetzbar**; ein Viewer-Leaderboard kann Zustand per `api.request()` abfragen, System-Events per `bus_event` empfangen, per Query-Kanal Top-10 serverseitig bereitstellen und live als Dashboard-Tab zeigen. Eigene Spiele binden sich über `/events/ingest` an (Bus + Trigger ohne Minecraft-branded Webhook), und zeitbasierte Logik ist in Hooks wie Plugins erstklassig möglich.

**Verbleibende Roadmap (aus der Capability-Matrix):**
1. WebSocket-Anschluss pro Erweiterung (HIGH; eigentliche Routen sind über den generischen RPC-Kanal abgedeckt)
2. Event-Payload-Schemata + Versionsvertrag im Event-Katalog (HIGH)
3. Netzwerk-Client-Bibliothek (Retry/Circuit-Breaker) als Plugin-API exportieren (MEDIUM)
4. UI-Extension-Points für Hooks; Hook↔Hook-Query (MEDIUM/LOW)
