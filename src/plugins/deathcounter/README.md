# Death Counter Plugin

Automatically detects player deaths and counts them. No setup needed beyond enabling.

## What it does

- Counts player deaths in real time on the overlay
- Publishes `death.milestone` events to the EventBus when configured milestones are reached
- Supports reset via the Event-Command Mapper

## Overlay URL

```
http://127.0.0.1:29185/api/v1/plugins/death-counter/overlay
```

## How to enable

1. Open the **Plugins** page in the Dashboard.
2. Toggle **Death Counter** on.

## Configuration

Configure via the Dashboard (Plugins → Death Counter) or edit `plugins/deathcounter/config.yaml` directly.

| Setting | Description | Default |
|---------|-------------|---------|
| `milestones` | Death counts at which a `death.milestone` event is emitted | `[]` |
| `signal_on` | Events published to the EventBus | `["milestone"]` |

### Theme settings

| Setting | Description | Default |
|---------|-------------|---------|
| `theme.background` | Background color | `#000000` |
| `theme.text` | Text color | `#ff4444` |
| `theme.accent` | Accent color | `#ff8888` |

## Event-Command Mapper integration

The death counter can be targeted in `data/event_commands.yaml`:

| Command | Description |
|---------|-------------|
| `player_death` | Increase the death counter by 1 |
| `add_death` | Add deaths to the counter (with `amount` arg) |
| `reset` | Reset the death counter to zero |

Example:

```yaml
event_commands:
  minecraft.player_death:
    - target: death-counter
      command: player_death
```
