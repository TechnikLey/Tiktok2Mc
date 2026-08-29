# Test Sandbox

Interactive developer sandbox for the TikTok2MC plugin system. **Not included
in release builds** (excluded in `build.py` together with `example_plugin`).

While `example_plugin` is the read-only reference template, this plugin is a
*living* example: start it, open its dashboard tab and watch every framework
feature in action.

## What it demonstrates

| Feature | Where | How to try it |
|---|---|---|
| Commands | `register_handler()` | Dashboard buttons or `POST /api/v1/plugins/test/command {"command": "ping"}` |
| State + live overlay | `push_state()` / EventSource `/plugins/test/stream` | Watch the overlay/dashboard counter while clicking |
| Events with schema | `publish_event("test.*", ...)` | `ping` / `echo` / milestone bumps; payloads validated against `data_schema` in `plugin.json` |
| Queries | `on_query()` | `POST /api/v1/plugins/test/query {"query": "stats"}` (also polled live in the dashboard tab) |
| Generic RPC | `on_rpc()` | `POST /api/v1/plugins/test/rpc {"method": "GET", "path": "/stats"}` |
| Persistent store | `store_get()` / `store_set()` | Counter and last message survive a plugin restart |
| Tick loop | `on_tick()` | Uptime updates in state every 5 s |
| Graceful shutdown | `on_stop()` | Disable/restart the plugin — state is persisted |
| Dashboard UI | `dashboard_ui: true` + `get_dashboard_html()` | "Test Sandbox" tab in the web dashboard |

## Permissions used

- `events` — publishing `test.pong`, `test.echo`, `test.bump_milestone`
- `store` — persisting/restoring session state

## Files

- `main.py` — heavily commented plugin implementation
- `plugin.json` — manifest: permissions, queries, emitted events (+ schemas), accepted commands, config schema
- `config.yaml` — user-editable config overriding `config_schema` defaults
