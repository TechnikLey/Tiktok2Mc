# TikTok-Chatbot

Der TikTok-Chatbot ist eine **First-Party-Kernfunktion** (kein Plugin oder Hook), die automatisch Nachrichten in den TikTok-Livechat schreibt: Er bedankt sich bei Geschenken und Follows und antwortet auf Keyword-Kommentare. Er läuft im API-/Control-Plane-Prozess, abonniert den zentralen `event_bus` und sendet über die authentifizierte TikTok-Web-Session.

## Architekturüberblick

| Komponente | Ort | Zweck |
|---|---|---|
| Kernmodul | `src/core/tiktok_chatbot.py` | `TikTokChatbot`: Config-Parsing, Regel-Matching, Send-Warteschlange, Spam-Schutz |
| Session-Store | `src/core/chatbot_session.py` | Verschlüsselte Session-Verwaltung (`data/chatbot_session.json`, Fernet via SecureStorage), Reload-Signal |
| Status-Tracker | `src/core/api/chatbot_status.py` | Status-Snapshot im Speicher (verbunden, Zähler, letzter Fehler) |
| API-Routen | `src/core/api/routes/chatbot.py` | `GET/PUT /api/v1/chatbot/config`, `GET /api/v1/chatbot/status`, `GET/PUT/DELETE /api/v1/chatbot/session` |
| GUI-Tab | `templates/gui/chatbot-editor.js` | Dashboard-Editor (Toggle, Antworten, Anmeldung, Status) |

Zentrale Entwurfsentscheidungen:

- **Kern, kein Hook:** Der Chatbot ist Produktfunktionalität wie der Port-Scanner — er darf nicht vom Nutzer entfernbar sein und braucht direkten Zugriff auf den `TikTokLiveClient`.
- **Eigene Config-Datei:** `config/chatbot.yaml` ist bewusst von der globalen `config.yaml` getrennt.
- **Event-Bus-Abo:** Der Bot konsumiert Events neben der TriggerEngine, ohne die Bridge-Queues anzutasten.

## Antwort-Regeln (`replies`)

Antworten werden als geordnete Regelliste konfiguriert. **Die erste passende Regel gewinnt** — ein Event erzeugt nie mehr als eine Nachricht.

```yaml
replies:
  - on: gift
    match: ""            # leer = jedes Geschenk; sonst Gift-Name
    message: "Danke {user} für {gift}!"
  - on: follow
    message: "Willkommen {user}!"
  - on: join
    message: "Hey {user}, schön dass du da bist!"
  - on: keyword
    match: "discord"     # Kommentar entspricht oder beginnt damit
    message: "{comment} -> Komm auf unseren Discord!"
```

- Erlaubte `on`-Werte: `gift`, `follow`, `join`, `keyword` (siehe `REPLY_EVENTS`).
- Platzhalter werden über eine sichere Map eingesetzt: `{user}`, `{gift}`, `{comment}`. Unbekannte Platzhalter bleiben wörtlich stehen.
- Regeln mit unbekannten Event-Typen oder leerer Nachricht werden beim Parsen verworfen.

## Spam-Schutz

Jede ausgehende Nachricht läuft durch eine Warteschlange mit:

- Mindestabstand zwischen zwei Nachrichten (`min_interval_s`)
- Minuten-Limit (`max_per_minute`)
- begrenzter Warteschlange (`max_queue`) — Überlauf wird verworfen
- optionaler Duplikat-Unterdrückung (`dedupe_identical`)
- Maximallängen-Kürzung (`max_len`)

Diese Limits existieren, weil TikTok den Chat streng limitiert; halte die Defaults konservativ.

## Session-Management

 Zwei Anmeldevarianten schreiben denselben verschlüsselten Store:

1. **Manuell:** Der Nutzer fügt das `sessionid`-Cookie (plus optional `tt_target_idc`) in die GUI ein → `PUT /api/v1/chatbot/session`.
2. **Webview:** Der GUI-Prozess öffnet ein QtWebEngine-Fenster auf `tiktok.com/login`; nach erfolgreichem Login werden die Cookies extrahiert (`extract_session_cookies()`) und gespeichert.

Beide Pfade enden mit `request_bridge_reload()`, das das Signal `core/runtime/reload_chatbot` ablegt, damit die Bridge Session und Config ohne Neustart neu lädt.

> [!NOTE]
> Die Session-Datei verlässt nie das Gerät und wird von der API nur maskiert zurückgegeben.

## Tests

- Python: `tests/test_core/test_tiktok_chatbot.py` (Config-Parsing, Regel-Matching, Spam-Schutz), `tests/test_api/test_chatbot_routes.py` (Routen + Reload-Signal).
- GUI: `templates/gui/tests/chatbot-editor.test.js`.
