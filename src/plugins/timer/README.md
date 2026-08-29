# Timer Plugin

A configurable count-up / count-down timer overlay for your TikTok2MC stream.

## What it does

- Counts **down** from a set time or **up** from zero
- Publishes lifecycle events (`timer.started`, `timer.paused`, `timer.resumed`, `timer.reset`, `timer.tick`, `timer.zero`, `timer.milestone`) to the EventBus
- Provides an overlay for OBS / streaming software
- Supports milestones, auto-start, and looping

## Overlay URL

```
http://127.0.0.1:29185/api/v1/plugins/timer/overlay
```

## How to enable

1. Open the **Plugins** page in the Dashboard.
2. Toggle **Timer** on.

## Configuration

Configure via the Dashboard (Plugins → Timer) or edit `plugins/timer/config.yaml` directly.

| Setting | Description | Default |
|---------|-------------|---------|
| `direction` | `down` (countdown) or `up` (count up) | `down` |
| `start_time` | Starting time in seconds | `600` |
| `time_step` | Seconds added/removed per tick | `1` |
| `auto_start` | Start automatically when the plugin loads | `false` |
| `loop` | When counting down, reset to start time instead of pausing at zero | `false` |
| `reset_on` | Events that trigger auto-reset: `zero`, `manual`, `command` | `["zero"]` |
| `signal_on` | Timer events published to the EventBus | `["zero", "started", "paused", "reset"]` |
| `milestones` | List of times (seconds) that emit `timer.milestone` events | `[]` |
| `format` | Display format: `mm:ss`, `hh:mm:ss`, or `seconds` | `mm:ss` |

### Theme settings

| Setting | Description | Default |
|---------|-------------|---------|
| `theme.background` | Background color | `#000000` |
| `theme.text` | Text color | `#89CFF0` |
| `theme.warning` | Warning color | `#FFD700` |
| `theme.blink` | Blink color | `#FF8C00` |
| `theme.danger` | Danger color | `#FF0000` |

## Control

- **Dashboard** — Start, pause, resume, reset, set time via the plugin's control panel.
- **Event-Command Mapper** — Automate timer actions based on Minecraft events (e.g., pause on player death, reset on timer zero).
- **Chat commands** — If configured, viewers can control the timer via TikTok chat.

## Event-Command Mapper integration

The timer can be targeted in `data/event_commands.yaml`:

| Command | Description |
|---------|-------------|
| `start` | Start the timer |
| `pause` | Pause the timer |
| `resume` | Resume a paused timer |
| `reset` | Reset the timer to its starting value |
| `add_time` | Add seconds to the current timer |
| `set_time` | Set the timer to a specific number of seconds |

Example:

```yaml
event_commands:
  minecraft.player_death:
    - target: timer
      command: pause
  minecraft.player_respawn:
    - target: timer
      command: resume
```
