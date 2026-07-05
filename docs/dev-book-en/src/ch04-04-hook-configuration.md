# Hook Configuration

Configuration for hooks is stored in the `config.yaml` in the hook directory and defined through the `config_schema` in `hook.json`.

## Defining a Schema

In `hook.json` under `config_schema`:

```json
{
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "duration",
        "type": "integer",
        "default": 10,
        "label": "Effect Duration (seconds)",
        "help": "How long the effect lasts",
        "category": "Effects"
      },
      {
        "key": "color",
        "type": "color",
        "default": "#ff4444",
        "label": "Effect Color",
        "category": "Effects"
      },
      {
        "key": "mode",
        "type": "select",
        "default": "normal",
        "options": ["normal", "enhanced"],
        "label": "Mode",
        "category": "General"
      }
    ]
  }
}
```

Supported field types: `boolean`, `integer`, `string`, `color`, `select`

## Automatic Generation

If the `config.yaml` is missing, it is automatically generated from the schema on first startup (with default values). Missing or invalid fields are repaired ("Healing").

> [!NOTE]
> The `enabled` field is managed automatically by the system, even if it is not defined in the schema. Set `enabled: false` in the `config.yaml` to disable the hook.

## Access in the Hook

```python
def register(api: HookAPI):
    def handler(user, trigger, context):
        cfg = api.get_hook_config("jump")
        duration = cfg.get("duration", 10)
        mode = cfg.get("mode", "normal")

        if mode == "enhanced":
            duration *= 2

        api.rcon_enqueue([f"effect give @a jump_boost {duration} 5 true"])

    api.register_action("superjump", handler)
```

## config.yaml Storage Location

```
src/hooks/<name>/config.yaml
```

For plugin-bundled hooks:

```
src/plugins/<plugin>/hooks/<name>/config.yaml
```

## Next Chapter

Learn about [Import Restrictions](./ch04-05-import-restrictions.md) for hooks.
