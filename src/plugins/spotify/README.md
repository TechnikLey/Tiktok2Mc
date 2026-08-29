# Spotify Control Plugin

Lets viewers control your Spotify playback through TikTok chat.

## What it does

- Viewers type chat commands (`$play`, `$pause`, `$skip`, `$volume 50`, etc.) to control Spotify
- Shows the current track with album art on the overlay
- Publishes `spotify.track_changed`, `spotify.play`, `spotify.pause` events to the EventBus

## Overlay URL

```
http://127.0.0.1:29185/api/v1/plugins/spotify-control/overlay
```

## How to enable

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Add `http://127.0.0.1:29185/api/v1/plugins/oauth/callback?name=spotify-control` as a Redirect URI.
3. Enter your **Client ID** and **Client Secret** in the Dashboard (Plugins → Spotify Control → Config), or directly in `plugins/spotify/config.yaml`.
4. Enable the plugin in the Dashboard (Plugins → toggle **Spotify Control** on).
5. On first start, your browser will open for Spotify login.

> [!IMPORTANT]
> You also need to enable the `$` comment command group (under `comment_commands` in the Dashboard's Settings, or in `config.yaml`) for chat commands to work.

## Configuration

Configure via the Dashboard (Plugins → Spotify Control) or edit `plugins/spotify/config.yaml` directly.

| Setting | Description | Default |
|---------|-------------|---------|
| `client_id` | Spotify Developer App Client ID | `""` |
| `client_secret` | Spotify Developer App Client Secret | `""` |
| `volume_step` | Percent change per volume up/down command | `10` |
| `playtrack_mode` | `replace` (play immediately) or `queue` (add to queue) | `replace` |
| `device_id` | Spotify device to control (empty = active device) | `""` |
| `redirect_uri` | OAuth redirect URI | `http://127.0.0.1:29185/api/v1/plugins/oauth/callback?name=spotify-control` |
| `signal_on` | Events published to the EventBus | `["track_changed", "play", "pause"]` |

### Theme settings

| Setting | Description | Default |
|---------|-------------|---------|
| `theme.background` | Background color | `#000000` |
| `theme.text` | Text color | `#ffffff` |
| `theme.accent` | Accent color | `#1db954` |
| `theme.accent2` | Accent 2 color | `#1ed760` |

## Chat commands

| Command | Description |
|---------|-------------|
| `$play` | Start or resume playback |
| `$pause` | Pause the current track |
| `$skip` / `$next` | Skip to the next song |
| `$previous` | Go back to the previous song |
| `$volume <0-100>` | Set volume level |
| `$volume_up` | Increase the volume |
| `$volume_down` | Decrease the volume |
| `$shuffle` | Toggle shuffle on/off |
| `$repeat` | Toggle repeat on/off |
| `$save` | Save the currently playing song to your library |
| `$playtrack <name or URL>` | Search for and play a song |

> All commands use the `$` prefix by default. This can be changed in the `$` comment command group config.
