# Troubleshooting

This chapter helps you with common problems during plugin and hook development.

## Plugin Not Recognized

**Symptom**: The plugin does not appear in the plugin list.

**Possible Causes**:

1. **plugin.json missing or invalid** – Check if the `plugin.json` exists in the plugin directory and contains valid JSON.
2. **Wrong path** – The `entry_point` in `plugin.json` must be correct relative to the project root.
3. **Plugin watcher not running** – Restart the system.

## Plugin Does Not Start

**Symptom**: The plugin is displayed but does not start.

**Possible Causes**:

1. **Dependency not met** – A plugin listed in `depends_on` is not enabled.
2. **Import error** – Check the logs for import errors.

## Hook Not Loading

**Symptom**: The `$` command does not work.

**Possible Causes**:

1. **register() function missing** – Every hook needs `def register(api):` at the top level.
2. **Import not allowed** – Only use allowed modules (see [Import Restrictions](./ch04-05-import-restrictions.md)).
3. **Action name incorrect** – The name in `api.register_action()` must match the `$` command in `actions.mca`.

## Events Not Arriving

**Symptom**: A plugin is not receiving TikTok events.

**Possible Causes**:

1. **Event subscriptions missing** – Declare `event_subscriptions` in `plugin.json`.
2. **Wrong handler name** – Register the handler for `"tiktok_event"`.
3. **TikTok not connected** – Make sure the TikTok connection is active.

## Overlay Not Displayed

**Symptom**: The overlay shows nothing or stays black.

**Possible Causes**:

1. **get_overlay_html() not implemented** – This method must be overridden.
2. **Wrong URL** – Check the overlay URL in OBS.
3. **SSE connection interrupted** – The SSE client should reconnect automatically. Check the browser console for errors.

## Testing Triggers Without TikTok

You can test triggers without a TikTok connection:

```bash
# Send a single follow event
python tests/send_trigger.py --event tiktok.follow --user TestUser

# Show all available options
python tests/send_trigger.py --help
```

The script sends a simulated TikTok event via the API to the EventBus. Your plugin must be enabled and declare the corresponding `event_subscription`.

Or via the trigger tester interface in the GUI.

## Checking Logs

The system logs provide insight into most problems:

- **Plugin logs**: Stored in the `logs/` directory.
- **Console output**: Shows errors when loading plugins and hooks.
- **Health Monitor**: Shows the health status of all components.

## Common Error Messages

| Message | Meaning |
|---|---|
| `[HOOK] has no register() function — skipped` | The hook is missing the `register()` function |
| `[HOOK] Duplicate action 'name' — first registration kept` | The action name is already taken |
| `[HOOK] enqueue_trigger() blocked — chain depth exceeds maximum` | Infinite loop detected, trigger locked |
| `[HOOK] Error in action 'name': ...` | Error in the handler function |
