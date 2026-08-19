# Configuration

Each plugin has its own configuration in `config.yaml`. The system ensures the configuration is always valid — even if the file is missing or corrupted.

## The config.yaml

```yaml
threshold: 10
theme:
  background: "#000000"
  text: "#ff4444"
```

## Automatic Generation

If no `config.yaml` exists but a `config_schema` is defined in the `plugin.json`, the system automatically generates a configuration with default values.

Missing fields are added. Invalid values are replaced with defaults ("Healing").

## The Configuration Schema

Define in `plugin.json` under `config_schema` which fields your plugin expects:

```json
{
  "config_schema": {
    "version": 1,
    "fields": [
      {
        "key": "threshold",
        "type": "integer",
        "default": 10,
        "min": 1,
        "label": "Threshold",
        "help": "An event is triggered at this value",
        "category": "Events"
      },
      {
        "key": "theme.background",
        "type": "color",
        "default": "#000000",
        "label": "Background Color",
        "category": "Theme"
      },
      {
        "key": "api_key",
        "type": "string",
        "default": "",
        "secret": true,
        "label": "API Key",
        "help": "Masked in the GUI",
        "category": "Authentication"
      },
      {
        "key": "mode",
        "type": "select",
        "default": "normal",
        "options": ["normal", "turbo", "slow"],
        "label": "Mode",
        "category": "General"
      },
      {
        "key": "milestones",
        "type": "array",
        "default": [10, 50, 100],
        "item_schema": {"type": "integer", "min": 1},
        "label": "Milestones",
        "category": "Events"
      }
    ]
  }
}
```

### Supported Field Types

| Type | Description |
|-----|--------------|
| `boolean` | True/False |
| `integer` | Whole number (optional with `min`, `max`) |
| `number` | Floating point number (optional with `min`, `max`) |
| `string` | Text (optional with `pattern` regex) |
| `color` | Hex color, e.g., `#ff4444` |
| `select` | Selection from `options` list. The `options` field is required for this type. |
| `array` | List of elements (with `item_schema`). The `item_schema` field defines the type and validation of contained elements. |
| `object` | Nested object (with `item_schema` for field definitions) |

### Field Properties

| Property | Type | Description |
|-------------|-----|--------------|
| `key` | String | Key in the config (dots for nesting: `theme.background`) |
| `type` | String | Data type (see supported types above) |
| `default` | Any | Default value if the field is missing in the config |
| `label` | String | Display name in the GUI |
| `help` | String | Help text / tooltip |
| `category` | String | Category for GUI grouping (default: `"General"`) |
| `advanced` | Boolean | If `true`, hide in the advanced view (default: `false`) |
| `required` | Boolean | If `true`, the field must be set (default: `false`) |
| `secret` | Boolean | If `true`, the value is masked in the GUI (e.g., for API keys, default: `false`) |
| `min` | Integer | Minimum value (only for `integer`) |
| `max` | Integer | Maximum value (only for `integer`) |
| `options` | Array | Allowed values (only for `select`) |
| `item_schema` | Object | Schema for array elements (only for `array`). Supports `type`, `min`, `max`, and `options`. |
| `widget` | String | GUI widget hint, e.g., `"textarea"` or `"color"` |

## Access in Code

```python
class MyPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        cfg = self.config

        self._threshold = cfg.get("threshold", 10)
        self._mode = cfg.get("mode", "normal")
        bg = cfg.get("theme", {}).get("background", "#000000")
```

> [!NOTE]
> `self.config` returns a **copy** of the configuration. Changes do not affect the saved file.

## Plugin Activation

Whether a plugin runs is managed via the GUI, the interactive console (`enable <name>` / `disable <name>`), or `POST /api/v1/plugins/{name}/enable` / `disable` and stored in `data/api_plugin_registry.json`. A plugin does **not** activate itself through its config. Plugins start disabled by default and must be explicitly enabled by the user.

## Next Chapter

The complete [Plugin API Reference](./ch03-04-plugin-api.md) describes all methods of `BasePlugin`.
