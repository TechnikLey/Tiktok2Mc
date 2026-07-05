# Example Plugin

**A learning and reference plugin for the TikTok2MC plugin system**

Version: v1.0.0

This plugin demonstrates all key features of the `BasePlugin` framework:

- `BasePlugin` subclassing with `PLUGIN_NAME`
- Configuration loading from `config.yaml` / `plugin.json`
- Theme system (`load_plugin_theme`, `theme_css`)
- Command handlers via `register_handler()` and `on_command()`
- Tick loop (`on_tick()` for periodic background work)
- API communication (`api_post`, `api_get`, `push_state`, `send_command`)
- Event publishing to the EventBus
- State management and persistence
- Overlay HTML with EventSource live streaming
- Window state save/load
- Health monitor integration (automatic)

**Note:** This plugin is excluded from release builds by `build.py`.
