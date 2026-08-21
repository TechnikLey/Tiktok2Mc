# TikTok Chatbot

The TikTok Chatbot is a **first-party core feature** (not a plugin or hook) that posts automatic messages into the TikTok live chat: it thanks viewers for gifts and follows and replies to keyword comments. It lives in the API/control-plane process, subscribes to the central `event_bus` and sends via the authenticated TikTok web session.

## Architecture Overview

| Component | Location | Purpose |
|---|---|---|
| Core module | `src/core/tiktok_chatbot.py` | `TikTokChatbot`: config parsing, reply matching, send queue, spam protection |
| Session store | `src/core/chatbot_session.py` | Encrypted session handling (`data/chatbot_session.json`, Fernet via SecureStorage), reload signal |
| Status tracker | `src/core/api/chatbot_status.py` | In-memory status snapshot (connected, counters, last error) |
| API routes | `src/core/api/routes/chatbot.py` | `GET/PUT /api/v1/chatbot/config`, `GET /api/v1/chatbot/status`, `GET/PUT/DELETE /api/v1/chatbot/session` |
| GUI tab | `templates/gui/chatbot-editor.js` | Dashboard editor (toggle, replies, login, status) |

Key design decisions:

- **Core, not hook:** The chatbot is product functionality like the port scanner — it must not be user-removable and needs direct `TikTokLiveClient` access.
- **Own config file:** `config/chatbot.yaml` is intentionally separate from the global `config.yaml`.
- **Event bus subscription:** The bot consumes events next to the TriggerEngine without touching bridge queues.

## Reply Rules (`replies`)

Replies are configured as an ordered rule list. **The first matching rule wins** — one event never produces more than one message.

```yaml
replies:
  - on: gift
    match: ""            # empty = any gift; otherwise gift name
    message: "Thanks {user} for {gift}!"
  - on: follow
    message: "Welcome {user}!"
  - on: join
    message: "Hey {user}, glad you're here!"
  - on: keyword
    match: "discord"     # comment equals or starts with this
    message: "{comment} -> Join our Discord!"
```

- Supported `on` values: `gift`, `follow`, `join`, `keyword` (see `REPLY_EVENTS`).
- Placeholders are rendered through a safe map: `{user}`, `{gift}`, `{comment}`. Unknown placeholders stay literal.
- Rules with unknown event types or empty messages are dropped at parse time.

## Spam Protection

Every outgoing message passes a queue with:

- minimum interval between two messages (`min_interval_s`)
- per-minute rate limit (`max_per_minute`)
- bounded queue (`max_queue`) — overflow is dropped
- optional duplicate suppression (`dedupe_identical`)
- maximum length truncation (`max_len`)

These limits exist because TikTok rate-limits chat aggressively; keep defaults conservative.

## Session Management

Two sign-in variants write the same encrypted store:

1. **Manual:** the user pastes the `sessionid` cookie (plus optional `tt_target_idc`) in the GUI → `PUT /api/v1/chatbot/session`.
2. **Webview:** the GUI process opens a QtWebEngine window on `tiktok.com/login`; after a successful login the cookies are extracted (`extract_session_cookies()`) and stored.

Both paths end with `request_bridge_reload()`, which drops the `core/runtime/reload_chatbot` signal so the bridge hot-reloads the session and config without a restart.

> [!NOTE]
> The session file never leaves the device and is only ever returned masked by the API.

## Testing

- Python: `tests/test_core/test_tiktok_chatbot.py` (config parsing, reply matching, spam protection), `tests/test_api/test_chatbot_routes.py` (routes + reload signal).
- GUI: `templates/gui/tests/chatbot-editor.test.js`.
