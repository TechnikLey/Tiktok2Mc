# Actions.mca Reference

The `data/actions.mca` defines what happens when a TikTok event arrives. It is the bridge between TikTok events and Minecraft actions.

## General Format

```
trigger: action1 ; action2 ; action3
```

- **Trigger**: An event name (`follow`, `join`, `comment`, `likes`, `like_2`, `share`), a gift ID (`5655`), or a custom name
- **Actions**: One or more semicolon-separated actions
- **File path**: `data/actions.mca` (fallback: `defaults/actions.mca`)

## Action Types

| Type | Example | Description |
|-----|----------|--------------|
| Vanilla | `/effect give @a speed 10 1` | Minecraft command via Datapack function |
| RCON | `!say Hello` | Command directly via RCON to the server |
| Hook | `$superjump` | Calls a registered hook handler |
| Overlay | `>>Title\|Subtitle\|5` | Display text in overlay |
| Named Overlay | `@gifts>>Title\|Text\|3` | Overlay on a specific channel |
| Shell | `&notepad.exe` | Execute command on host machine |

### Named Overlay

With `@name>>` you can display overlays on a specific channel:

```
follow: @default>>Welcome!|{user}|3 ; @gifts>>New Follower|{user}|3
```

### Multiplier

Actions can be repeated with `xN`:

```
follow: /give @a diamond x5 ; !say x3
```

The multiplier is noted at the end of the action.

## Comments and Deactivation

### Full Comments

Lines starting with `#` (after removing whitespace) are ignored:

```
# This is a comment
follow: /give @a diamond
```

### Disabled Triggers

Lines starting with `##` are parsed but marked as disabled:

```
## follow: /give @a diamond
```

### Inline Comments

In active lines, content after the first `#` is removed as a comment:

```
follow: /give @a diamond # this is a comment
```

## Processing

```
TikTok Event → on_comment() → trigger_worker()
    → execute_global_command(trigger, user)
        → Checks: Is trigger in script_actions?
            → Yes: For each action under trigger:
                → / → Minecraft command via Datapack
                → ! → RCON Queue
                → $ → HOOK_ACTIONS[action](user, action, {})
                → >> → Overlay text
                → & → Shell command
```

## Examples

```mca
# TikTok Standard Events
follow:  $greeting ; /give @a minecraft:bread 1
join:    >>Welcome!|{user}|3
likes:   $like-effect ; /playsound minecraft:entity.experience_orb.pickup master @a x3

# Gift IDs
5655:    $gift ; !tnt 2 0.1 2
16111:   $big-gift ; /give @a minecraft:diamond x2

# Inline Comment
share:   /give @a minecraft:emerald 1 # Reward for sharing

# Disabled Trigger
## likes: /kill @a

# Custom Triggers (only triggerable via hook)
bonus:   >>Bonus!|{user} has won|4 ; /effect give @a speed 30 1
```

## Trigger Names with Spaces

Trigger names with spaces are automatically wrapped in single quotes in `actions.mca`:

```
'my trigger': /say Hello
```

## Next Chapter

The [Event-Command-Mapper](./ch05-02-event-command-mapper.md) for loose coupling between plugins.
