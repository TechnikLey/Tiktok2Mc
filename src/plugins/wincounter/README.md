# Win Counter Plugin

Tracks wins and losses with configurable milestones.

## What it does

- Counts wins and publishes `win.milestone` and `win.record_low` events to the EventBus
- Configurable milestone thresholds (initial wins needed + increment per milestone)
- Provides an overlay for OBS / streaming software

## Overlay URL

```
http://127.0.0.1:29185/api/v1/plugins/win-counter/overlay
```

## How to enable

1. Open the **Plugins** page in the Dashboard.
2. Toggle **Win Counter** on.

## Configuration

Configure via the Dashboard (Plugins → Win Counter) or edit `plugins/wincounter/config.yaml` directly.

| Setting | Description | Default |
|---------|-------------|---------|
| `initial_needed` | Wins required for the first milestone | `10` |
| `milestone_increment` | Additional wins needed for each next milestone | `10` |
| `signal_on` | Events published to the EventBus | `["milestone", "record_low"]` |

### Theme settings

| Setting | Description | Default |
|---------|-------------|---------|
| `theme.background` | Background color | `#000000` |
| `theme.text` | Text color | `#ffffff` |
| `theme.muted` | Muted color | `#aaaaaa` |
| `theme.danger` | Danger color | `#ff4444` |
| `theme.separator` | Separator color | `#444444` |

## Usage

Use the Event-Command Mapper to add wins automatically (e.g., when the timer hits zero).

## Event-Command Mapper integration

The win counter can be targeted in `data/event_commands.yaml`:

| Command | Description |
|---------|-------------|
| `add_win` | Increase the win count (with `amount` arg) |
| `remove_win` | Decrease the win count (with `amount` arg) |

Example:

```yaml
event_commands:
  timer.zero:
    - target: win-counter
      command: add_win
      args:
        amount: 1
```
