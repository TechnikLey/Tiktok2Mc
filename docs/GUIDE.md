# TikTok to Minecraft Integration

Connect your TikTok Live stream to a Minecraft server. When viewers send gifts, follow you, or hit like milestones, Minecraft commands are triggered in real-time on your server.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Configuration](#configuration)
  - [Comment Commands](#comment-commands)
- [Setting Up Actions](#setting-up-actions)
  - [HTTP Actions (http_actions.txt)](#http-actions-http_actionstxt)
- [Minecraft Server](#minecraft-server)
- [Plugins and Overlays](#plugins-and-overlays)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)

---

## How It Works

When you go live on TikTok, the tool connects to your stream automatically. It watches for these types of events:

- **Gifts** -- A viewer sends a TikTok gift.
- **Follows** -- A viewer follows your account.
- **Likes** -- Viewers accumulate a certain number of likes.
- **Comments** -- A viewer writes a comment in the live chat.
- **Joins** -- A viewer joins the live stream.
- **Shares** -- A viewer shares the live stream.

Each event is linked to a Minecraft command that you define. For example, you could set it up so that every time someone sends a Rose gift, a Creeper spawns next to the player.

The tool includes a built-in Minecraft server (version 1.21.11), so you do not need to download one separately. On Windows, Java is also included. On Linux, the tool will find Java on your system or offer to install it automatically.

---

## Configuration

All settings are stored in `config/config.yaml`. Open this file with any text editor.

> [!WARNING]
> When editing this file, do not use the Tab key. Always use the  spacebar for indentation. Also, always keep a space after colons (for example `User: myname`, not `User:myname`).

### Your TikTok Username

Find this section and enter your TikTok username (without the @ symbol):

```yaml
TikTok:
  User: your_tiktok_username
```

### RCON Password

RCON is the connection between the tool and the Minecraft server. You should change the default password:

```yaml
RCON:
  Enable: true
  Password: ABC1234
```

Replace `ABC1234` with any password you like. Do **not** disable RCON (keep `Enable: true`), otherwise the tool cannot send commands to the Minecraft server.

### Control Method (DCS vs ICS)

This setting controls how the tool communicates with your streaming software:

```yaml
control_method: DCS
```

- **DCS** -- Use this if you stream with **OBS Studio**, vMix, or Streamlabs Desktop. This is the recommended option.
- **ICS** -- Use this if you stream with **TikTok Live Studio** or Twitch Studio.

If you are unsure, use DCS.

### Server Memory (RAM)

The Minecraft server needs RAM to run. By default, it uses 4 GB:

```yaml
Java:
  Xms: 4G
  Xmx: 4G
```

- `Xms` is the memory the server starts with.
- `Xmx` is the maximum memory the server can use.

If your computer has limited RAM (for example 8 GB total), lower these values (for example `2G` or `1G`). If you have 12 GB or more, the default of 4G is fine.

> [!NOTE]
> Setting the RAM too low can negatively affect the performance of the Minecraft server. This may cause lag, chunk loading issues, or server crashes -- especially with multiple players or complex actions running at the same time.

### Plugins and Overlays

You can enable or disable individual features in the config file. Each plugin has an `Enable` setting:

```yaml
GUI:
  Enable: false

Update:
  Enable: true

DeathCounter:
  Enable: true

WinCounter:
  Enable: true

Timer:
  Enable: true

LikeGoal:
  Enable: true

Overlaytxt:
  Enable: true
```

Set any of these to `false` if you do not need them.

### Console Visibility

The `log_level` setting controls how many windows are shown when the tool starts:

```yaml
Console:
  log_level: 2
```

- **0** -- Hides everything.
- **1** -- Hides console windows but keeps GUI and overlay features active.
- **2** -- Shows only the main windows (recommended).
- **3** -- Also shows background services.
- **4** -- Shows all running processes (for debugging).
- **5** -- Shows every process, even disabled ones (for debugging).

For normal use, keep this at 2.

### Comment Commands

The `CommentCommands` feature lets viewers send Minecraft commands directly to your server by writing a comment that starts with a configurable prefix character.

> [!WARNING]
> This sends raw commands directly to your Minecraft server via RCON. Anyone with the required role can execute commands. **Always use a Whitelist when `AllowedRoles` includes `all`, `fanclub`, or `superfan`.**

```yaml
CommentCommands:
  Enable: false
  Prefix: "!"
  AllowedRoles:
    - moderator
  Whitelist: []
  Blacklist:
    - op
    - deop
    - stop
    - ban
    - kick
    - whitelist
```

**Enable** -- Set to `true` to activate this feature.

**Prefix** -- The character a comment must start with to be treated as a command. Can be any character, for example `!`, `/`, or `#`. With `Prefix: "!"`, a viewer writing `!say Hello` sends the command `say Hello` to Minecraft.

**AllowedRoles** -- Controls who is allowed to use comment commands:

| Role | Description |
|------|-------------|
| `all` | Every viewer in the live chat |
| `moderator` | Stream moderators |
| `superfan` | Viewers with Superfan status |
| `fanclub` | Fanclub members |

You can combine multiple roles -- a viewer only needs to match one:

```yaml
AllowedRoles:
  - moderator
  - superfan
```

**Whitelist and Blacklist** -- Only the **first word** of the comment (the base command, e.g. `say` from `say Hello World`) is checked against these lists.

| Whitelist | Blacklist | Result |
|-----------|-----------|--------|
| Empty | Empty | ALL commands are allowed -- use with caution! |
| Empty | Filled | All commands allowed EXCEPT those in the Blacklist |
| Filled | Empty | ONLY commands whose base word is in the Whitelist |
| Both filled | -- | Must be in Whitelist AND NOT in Blacklist |

Example -- allow only `say` and `give`, always block dangerous commands:

```yaml
CommentCommands:
  Enable: true
  Prefix: "!"
  AllowedRoles:
    - moderator
  Whitelist:
    - say
    - give
  Blacklist:
    - op
    - deop
    - stop
    - ban
    - kick
    - whitelist
```

With this setup, a moderator writing `!say Hello stream` sends `say Hello stream` to Minecraft. A moderator writing `!op Notch` is blocked because `op` is in the Blacklist. A non-moderator viewer is blocked at the role check and never reaches the Whitelist or Blacklist at all.

> [!NOTE]
> Comment Commands are separate from the `comment` trigger in `actions.mca`. The `comment` trigger fires for every comment regardless of prefix. Comment Commands only activate when the prefix matches and the viewer has the required role.

---

## Setting Up Actions

### What is actions.mca?

The file `data/actions.mca` is where you define what happens in Minecraft when a TikTok event occurs. Each line in this file links a TikTok event (like a specific gift) to a Minecraft command.

### How to Write an Action

Each line in `actions.mca` follows this pattern:

```
Trigger:TypeCommand
```

- **Trigger** -- What causes the action (a gift ID, `follow`, or a like trigger name).
- **:** -- A colon separates the trigger from the command. No spaces around it.
- **Type** -- The first character(s) of the command. This tells the tool what kind of command it is:
  - `/` for standard Minecraft commands
  - `!` for Minecraft server plugin commands
  - `$` for special built-in actions
  - `>>` for overlay text (see [Overlay Text](#overlay-text))
  - `@Name>>` for overlay text sent to a specific named overlay window (see [Multiple Overlays](#multiple-overlays))
- **Command** -- The actual command to run.

> [!WARNING]
> The type character (`/`, `!`, `$`, or `>>`) is required. If you leave it out, the command will not work.

For example:

```
follow:/give @a minecraft:golden_apple 7   # Correct -- starts with /
follow:give @a minecraft:golden_apple 7    # Wrong -- missing the / before the command
```

Here, `follow` is the trigger, `/` is the type (Minecraft command), and `give @a minecraft:golden_apple 7` is the command. Together they mean: When someone follows, give every player 7 golden apples.

### Trigger Types

There are five types of triggers:

**Gift ID** -- A number that represents a specific TikTok gift. Each gift has a unique ID. Example:

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~
```

**follow** -- Triggers when someone follows your TikTok account. Example:

```
follow:/give @a minecraft:golden_apple 7
```

**join** -- Triggers every time a viewer joins the live stream. Example:

```
join:>>Welcome!|{user} just joined the stream!|3
```

**comment** -- Triggers every time a viewer writes a comment in the live chat.

> [!WARNING]
> The `comment` trigger fires for **every** comment. On active streams this can be very frequent. Avoid complex or expensive commands here.
> [!WARNING]
> The `join` trigger fires for every viewer that joins the stream, which can be very frequent on busy streams. Use with caution to avoid overwhelming your server with commands.

Example:

```
comment:>>New comment!|{user} commented!|2
```

**likes** and **like_2** -- Trigger based on accumulated likes. See [Like Triggers](#like-triggers) for details.

---

#### Using Trigger Names or IDs

You can use either **trigger IDs** or **trigger names** in your `actions.mca` file.

The available gifts are defined in `core/gifts.json`, for example:

```json
{
  "name": "Tom the Tomato",
  "coins": 1,
  "id": 16379
},
{
  "name": "Cool",
  "coins": 1,
  "id": 16212
}
```

---

##### Example Usage

Both of the following lines in `actions.mca` do the same thing:

```mcfunction
16212:/give @a minecraft:diamond 5
Cool:/give @a minecraft:diamond 5
```

When the gift **"Cool"** is received, all players will get 5 diamonds.

---

##### Priority Rule

> [!IMPORTANT]
> * The system checks **names first**, then **IDs**.
> * If a **name match is found**, the corresponding command is executed.
> * The line using the **ID will be ignored** in that case.
>
> If you use both a name and its ID in `actions.mca`, only the **name-based trigger** will run.

---

##### Handling Names with Spaces

Gift names that contain spaces must be wrapped in single quotes `' '`.

###### Example:

```
'Tom the Tomato':/give @a minecraft:carrot 10
```

Without quotes, the trigger will not work correctly.

---

### Command Types

Every command must start with one of these symbols:

**`/` -- Minecraft commands.** Standard Minecraft commands, like you would type in the game chat.

```
follow:/give @a minecraft:golden_apple 7
```

**`!` -- Plugin commands.** Commands for Minecraft server plugins (not vanilla Minecraft). Example:

```
5655:!tnt 2 0.1 2 Notch
```


> [!NOTE]
> #### !tnt Command (Plugin)
> The `!tnt` command is a server plugin command that spawns multiple TNT entities. It has four forms:
> 
> | Syntax | Description |
> |--------|-------------|
> | `!tnt <Amount>` | Spawns TNT with the delay set in `config.yml`. |
> | `!tnt <Amount> <Player>` | Spawns TNT for a specific player. |
> | `!tnt <Amount> <Delay> <Fuse>` | Spawns TNT with a custom delay and fuse. |
> | `!tnt <Amount> <Delay> <Fuse> <Player>` | Spawns TNT with a custom delay and fuse for a specific player. |
> 
> **Parameters:**
> - **Amount** -- How many TNT to spawn.
> - **Delay** -- Time in seconds between each TNT spawn (e.g. `0.1` for fast spawning).
> - **Fuse** -- Time in seconds before each TNT explodes after spawning.
> - **Player** -- The player name to spawn the TNT at.
> 
> **Example:**
> ```
> 5655:!tnt 2 0.1 2 Notch
> ```
> This spawns 2 TNT at the player `Notch`, with 0.1 seconds between each spawn and a 2-second fuse.

**`$` -- Special built-in actions.** Currently, only `$random` is available. See [The Random Action](#the-random-action).

**`>>` -- Overlay text.** Sends text to the stream overlay. See [Overlay Text](#overlay-text) for details. Example:

```
follow:>>Neuer Follower!|{user} folgt dir!|5
```

**`@Name>>` -- Named overlay text.** Same as `>>`, but targets a specific named overlay window. Replace `Name` with the name of one of your configured overlays. If you write `>>` without a name, the overlay named `default` is used automatically. See [Multiple Overlays](#multiple-overlays) for details.

### Repeating Commands

Add `x` followed by a number at the end of a command to repeat it:

```
8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

This summons 3 Evokers. Without `x`, the command runs once.

Some commands already include an amount (like `/give @a minecraft:diamond 5`). In those cases, you do not need to use `x`.

### Chaining Multiple Commands

Use `;` to run multiple commands from a single trigger. They run from left to right:

```
like_2:/clear @a *; /kill @a
```

This first clears everyone's inventory, then kills all players.

### Disabling an Action

Put a `#` at the beginning of a line to disable it:

```
#8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3
```

This line will be ignored. You can use this to temporarily turn off an action without deleting it.

---

### The Random Action

The `$random` command allows the tool to pick and execute a random action from your defined list. You can fine-tune exactly which actions are eligible using the `random_included` and `random_exclude` lists.

#### How the Filters Work
The selection process follows a specific hierarchy based on how you fill the lists:

| Scenario | Result |
| :--- | :--- |
| **Both lists are empty** | All triggers are allowed. |
| **ONLY `random_exclude` is set** | All triggers are allowed **EXCEPT** those in this list. |
| **ONLY `random_included` is set** | **ONLY** triggers in this list are allowed. |
| **BOTH lists are set** | A trigger must be in `included` **AND NOT** in `exclude`. |

> [!IMPORTANT]
> **The Override Rule:** The `random_exclude` list always acts as a "veto." Even if an action is specifically listed in `random_included`, it will be blocked if it also appears in `random_exclude`.

---

#### Configuration

You can manage these settings directly in your `config/config.yaml` file. Here is an example setup:

```yaml
Gifts:
  # WHITELIST: Only these triggers can be selected by $random.
  # Leave empty to allow all triggers (subject to exclusion rules).
  random_included:
    - 

  # BLACKLIST: These triggers will NEVER be selected by $random.
  random_exclude:
    - likes
    - like_2
    - follow
    - join
    - comment
```

---

> [!NOTE]
> * **Recursion Safety:** Any trigger that contains the `$random` command itself is **automatically excluded** by the system. This prevents the tool from getting stuck in an infinite loop.
> * **Standard Exclusions:** By default, common interactions like `follow`, `likes`, `like_2`, `join`, and `comment` are excluded. You can manually remove them from the `exclude` list if you want them included in the pool.
> * **Precision Matters:** Ensure the trigger names in these lists match your action definitions exactly (case-sensitive).

---

#### Implementation Example
If you define a gift trigger like this:
```yaml
16071:$random
```

When the gift with ID **16071** is received, the tool will look at your configuration, filter out the forbidden actions, and roll the dice on the remaining ones.

### Like Triggers

Like triggers fire when the total number of likes reaches a certain threshold. Unlike gifts and follows, like triggers are not defined in `actions.mca` alone -- they also need a matching entry in `config/config.yaml`.

Here is the default configuration:

```yaml
Gifts:
  like_triggers:
    - id: likes_standard
      every: 100
      function: likes
      payload: Community
      enable: true

    - id: likes_100k
      every: 100_000
      function: like_2
      payload: Community
      enable: true
```

**What each field means:**

| Field      | Required | Description |
|------------|----------|-------------|
| `id`       | Yes      | A unique name for this trigger. Used for identification and logging. Can be anything, but must be different for each trigger. |
| `every`    | Yes      | How many likes between each activation. For example, `100` means the trigger fires every 100 likes. You can use underscores for readability (e.g. `100_000` for 100,000). |
| `function` | Yes      | The trigger name you use in `data/actions.mca`. This is what connects the config entry to the actual Minecraft command. |
| `payload`  | No       | A label passed along with the trigger. Defaults to `Community` if not set. For gifts and follows, the viewer's TikTok username is used automatically -- but since likes are anonymous, this value is used instead. |
| `enable`   | No       | Set to `true` or `false` to turn this trigger on or off. Defaults to `true` if not set. |

With the config above, two triggers are active:

- `likes` fires every 100 likes.
- `like_2` fires every 100,000 likes.

You then define the actual commands in `data/actions.mca` using the `function` name as the trigger:

```
likes:/execute at @a run summon minecraft:creeper ~ ~ ~ x2
like_2:/clear @a *; /kill @a
```

**Adding your own like triggers:**

You can add as many like triggers as you want. Just add a new entry under `like_triggers` in `config/config.yaml` and create a matching line in `actions.mca`.

For example, to add a trigger that fires every 500 likes, your full `like_triggers` section would look like this:

```yaml
Gifts:
  like_triggers:
    - id: likes_standard
      every: 100
      function: likes
      payload: Community
      enable: true

    - id: likes_100k
      every: 100_000
      function: like_2
      payload: Community
      enable: true

    - id: likes_500
      every: 500
      function: likes_medium
      enable: true
```

Then add a matching line to `data/actions.mca`:

```
likes_medium:/give @a minecraft:tnt 10
```

Make sure each trigger has a unique `id` and a unique `function` name.


### Test Your Triggers Without TikTok

Want to test your triggers without going live on TikTok? No problem!

There is a simple test tool included:

- **Location:** `test/test_trigger.exe` (Windows) or `test/test_trigger` (Linux)
- **How to use:**
  1. Make sure the tool is running (the tool must be started, but TikTok connection is not required).
  2. Start the executable.
  3. Enter any trigger name (e.g. `follow`, `like_2`, or a gift ID like `5655`) and optionally a username when prompted.
  4. The tool will simulate the trigger as if it came from TikTok -- all actions, overlays, and Minecraft commands will run as configured.

This is perfect for testing your setup, debugging, or just having fun with your actions without needing to go live on TikTok every time.

> [!IMPORTANT]
> The test tool only confirm that your trigger was sent to the tool. They do **not** guarantee that the action was actually executed in Minecraft or by a plugin/hook. Always check in-game or in the tool logs to make sure your action really happened. The script only reports if the trigger was delivered successfully, not if the command was run or completed without errors.

If you want to temporarily disable or re-enable the TikTok connection (for testing only Minecraft features), just enter `tiktok` as the trigger in the script. This toggles the TikTok connection on or off.

> [!NOTE] 
> This setting is only valid until you restart the tool. After restarting, the TikTok connection will be enabled again by default.

### HTTP Actions (http_actions.txt)

The file `data/http_actions.txt` is a second action file that runs alongside `actions.mca`. While `actions.mca` sends commands to Minecraft, `http_actions.txt` runs any **shell command on your computer** when a gift is received.

**Trigger type:** Gift IDs only. HTTP actions are not supported for `follow`, `join`, `comment`, or like triggers.

**Independence:** Both files are checked for every gift event. If the same gift ID appears in both `actions.mca` and `http_actions.txt`, both actions run — they do not conflict.

#### Format

Each line follows the same pattern as `actions.mca`:

```
GiftID:ShellCommand
```

- **GiftID** -- The numeric gift ID (same IDs as in `actions.mca` and `core/gifts.json`).
- **ShellCommand** -- Any shell command that can run on your computer.

Lines starting with `#` are treated as comments and ignored.

#### Example

```
18508:curl -X POST http://localhost:8080/add?amount=10
16071:curl -X POST http://localhost:8080/remove?amount=10
```

This uses `curl` to send HTTP requests to the WinCounter plugin (port 8080). The first line adds 10 points to the counter when gift `18508` is received, the second removes 10 points when gift `16071` is received.

> [!NOTE]
> The WinCounter runs on `http://localhost:8080`. You can call its endpoints directly:
> - `/add?amount=N` -- Adds N to the counter.
> - `/remove?amount=N` -- Subtracts N from the counter.
>
> The same gift ID can also have an entry in `actions.mca` at the same time -- both will run independently.

> [!WARNING]
> `http_actions.txt` runs the command directly on your computer as a shell command. Only put commands here that you trust and understand.

---

### Finding Gift IDs

Every TikTok gift has a unique number (ID). You need this ID to create actions for specific gifts.

You can find all gift IDs in the file `core/gifts.json`. Open it with a text editor -- it looks like this:

```json
[
  {"name": "Cool", "coins": 1, "id": 16212},
  {"name": "Mamma Mia", "coins": 1, "id": 16111},
  ...
]
```

Use the `id` number as the trigger in your `actions.mca` file.

You can also find images of all TikTok gifts in the `core/assets/` folder. These are copyright-free and can be used in your stream.

---

## Minecraft Server

### Joining Locally

1. Start the tool with `start.exe` (Windows) or `./start` (Linux). This also starts the Minecraft server.
2. Open Minecraft.
3. Go to **Multiplayer** and click **Add Server**.
4. Enter the address: `localhost:25565`
5. Click **Done** and join the server.

### Letting Friends Join (Port Forwarding)

If you want other people to join your server over the internet, you need to set up port forwarding on your router. This forwards incoming connections to your computer.

How to do this:

1. Open your router's settings page (usually by typing `192.168.1.1` or `192.168.0.1` in your browser -- check your router's manual for the exact address).
2. Find the port forwarding section.
3. Forward port **25565** (TCP/UDP) to the local IP address of the computer running the Minecraft server.
4. Share your public IP address with your friends so they can connect.

> [!NOTE] 
> Port forwarding varies by router model. Search for "[your router model] port forwarding" online if you need help.

### Replacing the Server Version

The included Minecraft server is version 1.21.11 (Vanilla). If you want to use a different version or a modded server (Forge, Fabric, Paper, etc.), you can replace the server file:

1. Go to the `server/mc/` folder.
2. Note the **filename** of the current `.jar` file.
3. Replace it with your new `.jar` file.
4. **Rename** the new file to match the original filename exactly, so the launch script can find it.

> [!NOTE] 
> Your replacement server must support RCON (available in almost all Minecraft versions from 1.1 onward) and Datapacks (available from 1.13 onward).

---

## Plugins and Overlays

The tool comes with several built-in overlay plugins. These are small web pages that you can add as **Browser Sources** in OBS (or your streaming software) to display live information on your stream.

### Death Counter

Displays the number of times the player has died. Updates automatically when a death occurs in the game.

- **URL for OBS:** `http://localhost:7979`
- **Config setting:** `DeathCounter: Enable: true`

### Win Counter

Tracks your wins and losses on stream. When the player dies, the counter goes down by 1. When the Stream Timer reaches zero, the counter goes up by 1.

- **URL for OBS:** `http://localhost:8080`
- **Config setting:** `WinCounter: Enable: true`

### Like Goal

Shows a progress bar tracking how many likes your stream has received toward a goal.

- **URL for OBS:** `http://localhost:9797`
- **Config setting:** `LikeGoal: Enable: true`
- **Display text:** Set `LikeGoal: DisplayText:` to change the text shown above the progress bar.
- **Initial goal:** Set `LikeGoal: InitialGoal:` to the number of likes needed for the first goal (default: `100_000`).
- **Goal mode:** The `GoalMultiplier` setting controls what happens after reaching a goal:
  - `GoalMultiplier: 0` -- **Reset.** Likes reset to 0 and the goal starts over from the beginning.
  - `GoalMultiplier: 1` -- **Step.** The goal increases by `InitialGoal` each time (e.g. 100,000 → 200,000 → 300,000).
  - `GoalMultiplier: 2` (or higher) -- **Multiply.** The goal is multiplied each time (e.g. 100,000 → 200,000 → 400,000 → 800,000).

### Stream Timer

A countdown timer for your stream. It pauses when the player dies and resumes on respawn. When the timer hits zero, it counts as a win.

- **URL for OBS:** `http://localhost:7878`
- **Config setting:** `Timer: Enable: true`
- **Start time:** Set `Timer: StartTime: 10` to start with 10 minutes (or any number you want).

### Overlay Text

Displays custom text on your stream overlay. You can trigger overlay text directly from `actions.mca` using the `>>` prefix.

- **URL for OBS:** `http://localhost:5005/?overlay=default`
- **Config setting:** `Overlaytxt: Enable: true`

#### Display Mode

You can control what happens when a new message arrives while a previous one is still on screen:

```yaml
Overlaytxt:
  DisplayMode: overwrite
```

- **overwrite** -- The new message immediately replaces the current one. Use this if you only care about the latest event.
- **queue** -- Messages are queued and shown one after another. Each message stays for its full duration before the next one appears. Use this if every notification matters (e.g. follower names).

> [!WARNING]
> In queue mode, messages can pile up during busy streams. If many events fire at once (e.g. a gift spam or a raid), the queue may take a long time to clear and viewers will see outdated notifications long after the events happened. Only use queue mode if you are sure that the number of overlay messages stays manageable.

The default is `overwrite`.

#### Fade Animation

You can configure how fast the overlay text fades in and out:

```yaml
Overlaytxt:
  FadeIn: 500
  FadeOut: 500
```

Values are in milliseconds. The default is `500` (0.5 seconds) for both.

Fade-in and fade-out are **not** included in the `Duration` value. For example, with `FadeIn: 500`, `FadeOut: 500` and a duration of 3 seconds, the total visible time is 0.5s + 3s + 0.5s = 4 seconds.

Set either value to `0` to disable that animation (instant appear or disappear).

#### Syntax

```
>>Title|Subtitle|Duration
```

- **Title** -- The main text to display (large).
- **Subtitle** -- Smaller text below the title.
- **Duration** -- How many seconds the text stays visible (optional, default: 3).
- **`|`** -- A pipe character separates the three parts from each other.

You can use the following placeholders in overlay text:

- `{user}` — replaced with the TikTok username of the viewer who triggered the action.
- `{comment}` — replaced with the comment text (only for the `comment` trigger).

Example:

```
comment:>>{user} wrote:|{comment}|3
```
This will show the username and the comment text in the overlay when someone writes a comment.

**Examples:**

Show a follower notification for 5 seconds:

```
follow:>>New Follower!|{user} is now following you!|5
```

Show a short message with the default duration (3 seconds):

```
16111:>>Diamond!|Thank you {user}!
```

Combine overlay text with other commands using `;`:

```
follow:/give @a minecraft:golden_apple 7; >>New Follower!|{user} is now following you!|5
```

This gives golden apples to all players **and** shows the overlay text at the same time.

#### Multiple Overlays

You can run several overlay windows at the same time — each one as a separate OBS Browser Source showing different information. For example, one overlay in the top-left corner for gifts and another in the bottom-right for follower notifications.

To do this, add each overlay by name to `config/config.yaml`:

```yaml
Overlaytxt:
  Port: 5005
  Overlays:
    - name: default
    - name: stats
    - name: alerts
```

Each name creates a separate URL you can use as a Browser Source in OBS:

| Overlay name | URL |
|---|---|
| `default` | `http://localhost:5005/?overlay=default` |
| `stats` | `http://localhost:5005/?overlay=stats` |
| `alerts` | `http://localhost:5005/?overlay=alerts` |

All overlays share the same `Port`, `DisplayMode`, `FadeIn`, `FadeOut`, `MaxFails`, and `Cooldown` settings.

To send text to a specific overlay from `actions.mca`, write `@Name>>` instead of `>>`:

```
follow:@alerts>>New Follower!|{user} is now following you!|5
join:@stats>>Welcome!|{user} just joined!|3
```

If you write `>>` without a name, the overlay named `default` is used automatically:

```
follow:>>New Follower!|{user} is now following you!|5
```

This is exactly the same as:

```
follow:@default>>New Follower!|{user} is now following you!|5
```

> [!IMPORTANT]
> The name must exactly match one of the names defined under `Overlays` in `config.yaml`. If no match is found, the message is silently dropped.

> [!NOTE]
> Overlay Text works best with **DCS** mode (OBS Studio, vMix, Streamlabs Desktop). In DCS mode, you can add the overlay as a Browser Source with a transparent background -- the text appears cleanly on top of your stream.
>
> If you use **ICS** mode (TikTok Live Studio, Twitch Studio), you need to place a green screen filter over the overlay to make the background invisible. This can reduce the quality of the text (edges may look rough or colors may bleed). For the best results, it is recommended to use DCS mode when using Overlay Text.

---

## Maintenance

### MCA VS Code Extension (mca.vsix)

To make editing `.mca` files easier and safer, a custom VS Code extension (`mca.vsix`) is included in this project.

**Features:**
- Syntax highlighting for `.mca` files (TikTok event → Minecraft action mapping)
- Error highlighting for common mistakes (missing colons, wrong prefixes, etc.)
- Colorful formatting for triggers, commands, and comments
- Helps prevent mistakes and makes writing actions much easier

**Installation Tutorial:**
1. Open VS Code.
2. Go to the Extensions view (Ctrl+Shift+X).
3. Click the three-dot menu ("...") in the top right and select "Install from VSIX...".
4. Select the `mca.vsix` file from this repository in `core/assets/mca.vsix`.
5. Open any `.mca` file in like `data/actions.mca`. You should now see colors and error squiggles.

This extension is highly recommended for anyone editing `.mca` files, as it helps avoid formatting errors and speeds up writing new actions.

---

### Ports Used by the Tool

The tool uses several network ports. Under normal circumstances, you do not need to change any of these. Only change a port if you get an error like "Address already in use".

| Port  | Used For                    |
|-------|-----------------------------|
| 25565 | Minecraft Server            |
| 25575 | RCON (Server Communication) |
| 5000  | Web Dashboard (GUI)         |
| 7000  | Minecraft Server API        |
| 7777  | Internal Web Server         |
| 7878  | Stream Timer Overlay        |
| 7979  | Death Counter Overlay       |
| 8080  | Win Counter Overlay         |
| 5005  | Overlay Text                |
| 9797  | Like Goal Overlay           |

### Updating the Tool

The tool can update itself automatically. This is enabled by default:

```yaml
Update:
  Enable: true
```

When you start the tool, it checks for new versions and installs updates automatically. You can turn this off by setting `Enable: false`, but it is recommended to keep it on.

> [!IMPORTANT] 
> Always back up your data before updating. See [Backing Up Your Data](#backing-up-your-data).

### Backing Up Your Data

Before updating or making major changes, save copies of these files and folders:

- `server/mc/` -- Your Minecraft world and server data.
- `data/actions.mca` -- Your custom action mappings.
- `config/config.yaml` -- Your configuration.

Copy them to a safe location outside the tool folder.

---

## Troubleshooting

**The tool cannot connect to TikTok**
- Make sure you are currently live on TikTok.
- Double-check that your TikTok username is correct in `config/config.yaml` (without the @ symbol).
- The tool will keep trying to reconnect automatically.

**"Address already in use" error**
- Another application is using one of the ports listed above. Either close that application or change the conflicting port in `config/config.yaml`.

**Minecraft commands are not working**
- Make sure RCON is enabled (`RCON: Enable: true`).
- Make sure the RCON password in `config/config.yaml` matches the one the server is using.
- Check that your action lines in `data/actions.mca` follow the correct format.

**The Minecraft server does not start**
- Check that no other Minecraft server is already running on port 25565.
- If you have limited RAM, lower the `Xms` and `Xmx` values in the config.

**Overlays are not showing in OBS**
- Make sure the plugin you want to use is enabled in the config.
- Add a Browser Source in OBS with the correct URL (see [Plugins and Overlays](#plugins-and-overlays)).
- Check that the tool is running -- overlays only work while the tool is active.