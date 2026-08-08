#!/usr/bin/env python3
"""
example_plugin.py — Reference plugin for TikTok2MC

Demonstrates every major feature of the BasePlugin framework.
This plugin is NOT included in release builds (see build.py exclusion).

TOPICS COVERED:
  1. Plugin class with PLUGIN_NAME
  2. Reading config from config.yaml / plugin.json
  3. Command handlers via register_handler() + on_command() fallback
  4. Tick loop (on_tick, once per second)
  5. API communication (api_post, api_get, push_state)
  6. send_command — sending commands to OTHER plugins
  7. Event publishing to the EventBus (POST /events)
  8. Theme system (CSS variables from config)
  9. Overlay HTML with EventSource live streaming
  10. Window state save/load (save_window_state)
  11. Health monitor integration (automatic via BasePlugin)
"""

import logging
from typing import Any
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  1. PLUGIN CLASS
# ═══════════════════════════════════════════════════════════════════
# Every plugin MUST inherit from BasePlugin and MUST set PLUGIN_NAME.
# PLUGIN_NAME is used as the unique identifier for:
#   • API endpoints:  /api/v1/plugins/{PLUGIN_NAME}/...
#   • State files:    data/window_state_{PLUGIN_NAME}.json
#   • Health monitor: plugin.{PLUGIN_NAME}
#   • Overlay registration
# ═══════════════════════════════════════════════════════════════════
class ExamplePlugin(BasePlugin):
    """
    Reference counter plugin demonstrating all BasePlugin features.
    """

    # ---- Required: unique plugin ID -------------------------------
    # BasePlugin raises RuntimeError at __init__ if this is empty.
    PLUGIN_NAME = "example-plugin"

    # ---- Constructor ----------------------------------------------
    # super().__init__() automatically:
    #   • Runs parse_args()
    #   • Loads config.yaml + plugin.json (via load_plugin_config)
    #   • Loads theme colors (via load_plugin_theme → theme_css)
    #   • Loads saved window state from data/window_state_{name}.json
    #   • Registers with the health monitor
    #   • Creates the internal command dispatch table
    # -----------------------------------------------------------------
    def __init__(self):
        # ---- 1. Initialize BasePlugin -----------------------------
        # AFTER this call the following are available:
        #   self.config       — merged dict from config.yaml + plugin.json schema defaults
        #   self.theme_style  — CSS string with --text, --background, --accent etc.
        #   self.bg_color     — background hex color from theme
        #   self._plugin_dir  — path to this plugin's directory
        #   self._data_dir    — path to the shared data/ directory
        #   self._window_state — dict with "width" / "height" from last save
        #   self.state        — thread-safe dict for pushing state to the API
        #   self._handlers    — command → callback dict (use register_handler!)
        super().__init__()

        # ---- 2. Read plugin configuration -------------------------
        # self.config is a DICT that merges:
        #   1. plugin.json → config_schema → fields[].default
        #   2. config.yaml (local overrides)
        cfg = self.config

        # Starting counter value (from config, default 0)
        self._initial_count = int(cfg.get("initial_count", 0))

        # Step size for increment / decrement commands (default 1)
        self._step_size = int(cfg.get("step_size", 1))

        # Auto-tick mode: if True, counter increases every second
        self._auto_tick = cfg.get("auto_tick", False)

        # Maximum value (0 = unlimited)
        self._max_count = int(cfg.get("max_count", 0))

        # ---- 3. Runtime state -------------------------------------
        self._counter = self._initial_count
        self._is_negative = False

        # ---- 4. Register command handlers -------------------------
        # register_handler(command_name, callback) maps a command
        # string (sent via the API command queue) to a handler method.
        #
        # The callback receives args: dict with any parameters.
        # If a handler exists, the command is consumed here and
        # NEVER reaches on_command().

        # increment: increase the counter
        # args: {"amount"?: number} — optional, otherwise step_size
        self.register_handler("increment", self._on_increment)

        # decrement: decrease the counter
        self.register_handler("decrement", self._on_decrement)

        # reset: reset counter to initial value
        self.register_handler("reset", self._on_reset)

        # set: set counter to an arbitrary value
        # args: {"value": number}
        self.register_handler("set", self._on_set)

        # set_step_size: change the step size
        self.register_handler("set_step_size", self._on_set_step_size)

        # toggle_auto_tick: enable / disable auto-tick
        self.register_handler("toggle_auto_tick", self._on_toggle_auto_tick)

        # save_dims: persist window dimensions (sent by overlay JS on resize)
        self.register_handler("save_dims", self._on_save_dims)

        # ---- 5. Push initial state to the API ---------------------
        self._update_state()

        # ---- 6. Log startup confirmation --------------------------
        log.info(
            "[%s] Initialized. start=%s, step=%s, auto_tick=%s, max=%s",
            self.PLUGIN_NAME, self._counter, self._step_size,
            self._auto_tick, self._max_count,
        )

    # ═══════════════════════════════════════════════════════════════
    #  3. COMMAND HANDLERS
    # ═══════════════════════════════════════════════════════════════
    # Each handler receives args: dict from the command sender.
    # After changing state, _update_state() is called, which:
    #   1. Sets self.state with current values
    #   2. Calls self.push_state() → POST to API → EventSource update
    # ═══════════════════════════════════════════════════════════════

    def _on_increment(self, args: dict[str, Any]) -> None:
        """Increase the counter by amount (or step_size)."""
        amount = int(args.get("amount", self._step_size))
        self._counter += amount
        if self._max_count > 0 and self._counter > self._max_count:
            self._counter = self._max_count
        log.info("[Counter] +%s → %s", amount, self._counter)
        self._update_state()

        # Example of send_command(): at every 10th increment, send a
        # pause command to the timer plugin (if it's running).
        if self._counter > 0 and self._counter % 10 == 0:
            self.send_command("timer", "pause")

    def _on_decrement(self, args: dict[str, Any]) -> None:
        """Decrease the counter by amount (or step_size)."""
        amount = int(args.get("amount", self._step_size))
        self._counter -= amount
        log.info("[Counter] -%s → %s", amount, self._counter)
        self._update_state()

    def _on_reset(self, args: dict[str, Any]) -> None:
        """Reset the counter to initial_count (or a custom value)."""
        value = int(args.get("value", self._initial_count))
        self._counter = value
        log.info("[Counter] Reset → %s", value)
        self._update_state()

    def _on_set(self, args: dict[str, Any]) -> None:
        """Set the counter to an arbitrary value."""
        value = int(args.get("value", 0))
        self._counter = value
        log.info("[Counter] Set → %s", value)
        self._update_state()

    def _on_set_step_size(self, args: dict[str, Any]) -> None:
        """Change the step size (minimum 1)."""
        step = max(1, int(args.get("step", 1)))
        self._step_size = step
        log.info("[Counter] Step size → %s", step)
        self._update_state()

    def _on_toggle_auto_tick(self, args: dict[str, Any]) -> None:
        """Toggle or set auto-tick mode."""
        if "enabled" in args:
            self._auto_tick = bool(args["enabled"])
        else:
            self._auto_tick = not self._auto_tick
        log.info("[Counter] Auto tick → %s", self._auto_tick)
        self._update_state()
        self._publish_event("auto_tick_changed", {"enabled": self._auto_tick})

    def _on_save_dims(self, args: dict[str, Any]) -> None:
        """Persist window dimensions (sent by overlay JS on resize)."""
        self.save_window_state(
            args.get("width", 600),
            args.get("height", 300),
        )

    # ═══════════════════════════════════════════════════════════════
    #  7. EVENT PUBLISHING
    # ═══════════════════════════════════════════════════════════════
    # api_post("/events", ...) broadcasts an event to the central
    # EventBus. Other plugins, hooks, or the dashboard can react
    # without any direct coupling.
    # ═══════════════════════════════════════════════════════════════
    def _publish_event(self, event_type: str, data: dict | None = None) -> None:
        """Send an event to the EventBus (e.g. "counter.auto_tick_changed")."""
        payload: dict[str, Any] = {"type": f"counter.{event_type}"}
        if data:
            payload["data"] = data
        try:
            self.api_post("/events", payload)
        except (OSError, TypeError) as e:
            log.warning("[%s] Event publish failed: %s", self.PLUGIN_NAME, e)

    # ═══════════════════════════════════════════════════════════════
    #  4. TICK LOOP (on_tick)
    # ═══════════════════════════════════════════════════════════════
    # on_tick() is called once per second by the background thread
    # (_tick_loop). Use it for periodic work like countdowns,
    # polling external APIs, or checking conditions.
    #
    # IMPORTANT: Never block in on_tick() — it runs on the tick
    # thread and a long delay will stall the entire tick cycle.
    # ═══════════════════════════════════════════════════════════════
    def on_tick(self) -> None:
        """Called every second. Increments counter if auto_tick is enabled."""
        if self._auto_tick:
            self._counter += 1
            if self._max_count > 0 and self._counter > self._max_count:
                self._counter = self._max_count
                self._auto_tick = False
            self._update_state()

    # ═══════════════════════════════════════════════════════════════
    #  3. on_command FALLBACK
    # ═══════════════════════════════════════════════════════════════
    # Commands without a registered handler end up here. Override
    # this to log unknown commands or provide generic handling.
    # ═══════════════════════════════════════════════════════════════
    def on_command(self, command: str, args: dict[str, Any]) -> None:
        """Fallback for unregistered commands — logs and publishes an event."""
        log.warning("[%s] Unknown command: %s %s", self.PLUGIN_NAME, command, args)
        self._publish_event("unknown_command", {"command": command, "args": args})

    # ═══════════════════════════════════════════════════════════════
    #  5. STATE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    # self.state is a thread-safe dict. push_state() POSTs it to
    # /api/v1/plugins/{name}/state, which the overlay receives via
    # EventSource stream.
    # ═══════════════════════════════════════════════════════════════
    def _update_state(self) -> None:
        """Build current state dict and push it to the API (→ live overlay update)."""
        self._is_negative = self._counter < 0
        self.state = {
            "counter": self._counter,
            "is_negative": self._is_negative,
            "step_size": self._step_size,
            "auto_tick": self._auto_tick,
            "initial_count": self._initial_count,
            "max_count": self._max_count,
            "label": "Negative" if self._is_negative else "Positive",
        }
        self.push_state()

    # ═══════════════════════════════════════════════════════════════
    #  9. OVERLAY HTML
    # ═══════════════════════════════════════════════════════════════
    # MUST be overridden. Returns the HTML string displayed as an
    # overlay in OBS (or in the pywebview window).
    #
    # LIVE UPDATES: The overlay connects to the API via EventSource
    # (Server-Sent Events) at /api/v1/plugins/{name}/stream.
    # Whenever push_state() is called, the API pushes the new state
    # JSON to all connected overlays — no polling needed.
    #
    # self.theme_style → CSS variables from the theme (--text, --background, ...)
    # self.bg_color    → background hex color from the theme
    # ═══════════════════════════════════════════════════════════════
    def get_overlay_html(self) -> str:
        """
        Return overlay HTML. Called once at startup by BasePlugin.run().
        Live updates come through EventSource, not HTML re-rendering.
        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="dark">
<style>
{self.theme_style}
    /* =========================================================
       GLOBAL RESET
       =========================================================
       Transparent background for OBS browser source overlay.
       The theme background is applied only if displayed outside OBS. */
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        background: transparent;
        font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        overflow: hidden;
        width: 100vw;
        height: 100vh;
        display: flex;
        justify-content: center;
        align-items: center;
        -webkit-user-select: none;
        user-select: none;
        -webkit-font-smoothing: antialiased;
    }}

    /* =========================================================
       COUNTER DISPLAY
       =========================================================
       Large font size for stream readability. Negative values
       get a distinct color via the .negative CSS class. */
    #counter {{
        font-size: 70vh;
        font-weight: bold;
        font-variant-numeric: tabular-nums;
        color: var(--text);
        transition: color 0.3s ease;
        line-height: 1;
    }}

    #counter.negative {{
        color: var(--accent) !important;
        text-shadow: 0 0 20px rgba(255, 0, 0, 0.3);
    }}

    /* =========================================================
       STATUS INDICATOR (bottom-right corner)
       =========================================================
       Shows whether auto-tick is active. */
    #status {{
        position: fixed;
        bottom: 2vh;
        right: 2vw;
        font-size: 2.5vh;
        color: var(--accent);
        opacity: 0.6;
        font-weight: 400;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }}

    /* =========================================================
       FADE-IN ANIMATION
       =========================================================
       Smooth appearance when the overlay loads. */
    @keyframes fadeIn {{
        from {{ opacity: 0; transform: scale(0.9); }}
        to   {{ opacity: 1; transform: scale(1); }}
    }}
    #counter {{
        animation: fadeIn 0.4s ease-out;
    }}
</style>
</head>
<body>
    <!-- =====================================================
         COUNTER
         =====================================================
         The STARTING value is embedded directly so the overlay
         shows something immediately, even before the first
         EventSource message arrives. -->
    <div id="counter">{self._counter}</div>

    <!-- =====================================================
         AUTO-TICK STATUS INDICATOR
         ===================================================== -->
    <div id="status">{"◉ Auto" if self._auto_tick else ""}</div>

    <!-- =====================================================
         JAVASCRIPT: EventSource Live Updates
         =====================================================
         EventSource (Server-Sent Events) opens a persistent
         HTTP connection to the API. Whenever push_state() is
         called, the API pushes the new JSON state to ALL
         connected overlay clients — no polling required.

         Stream URL: /api/v1/plugins/{self.PLUGIN_NAME}/stream
         ===================================================== -->
    <script>
        // Cache DOM references
        const counterEl = document.getElementById('counter');
        const statusEl = document.getElementById('status');

        /**
         * Called whenever new state data arrives via EventSource.
         * @param {object} data — full state dict from _update_state()
         */
        function updateDisplay(data) {{
            // Update counter value
            counterEl.innerText = data.counter !== undefined ? data.counter : '?';

            // Toggle "negative" CSS class
            if (data.is_negative) {{
                counterEl.classList.add('negative');
            }} else {{
                counterEl.classList.remove('negative');
            }}

            // Show/hide auto-tick indicator
            statusEl.innerText = data.auto_tick ? '◉ Auto' : '';
        }}

        /**
         * Connect to the EventSource stream.
         * The API endpoint /api/v1/plugins/{self.PLUGIN_NAME}/stream
         * is provided automatically by the core API server when
         * the plugin calls push_state().
         */
         const evtSource = new EventSource('/api/v1/plugins/{self.PLUGIN_NAME}/stream');

        evtSource.onmessage = function(e) {{
            try {{
                const data = JSON.parse(e.data);
                updateDisplay(data);
            }} catch(err) {{
                // Ignore malformed JSON
            }}
        }};

        // EventSource auto-reconnects on connection loss.

        /**
         * WINDOW RESIZE HANDLER
         * Save overlay dimensions when the user resizes the
         * OBS browser source. Uses debounce (300ms) to avoid
         * firing a request on every pixel change.
         */
        let resizeTimer = null;
        window.addEventListener('resize', () => {{
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {{
                fetch('/api/v1/plugins/{self.PLUGIN_NAME}/command', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        command: 'save_dims',
                        args: {{
                            width: window.outerWidth,
                            height: window.outerHeight
                        }}
                    }})
                }});
            }}, 300);
        }});
    </script>
</body>
</html>"""

    # ═══════════════════════════════════════════════════════════════
    #  10. GET_STATE (optional utility)
    # ═══════════════════════════════════════════════════════════════
    # Providing a get_state() method is a common pattern in other
    # plugins. It lets external code (dashboard, API consumers)
    # read state without consuming the EventSource stream.
    # ═══════════════════════════════════════════════════════════════
    def get_state(self) -> dict[str, Any]:
        """Return current state as a plain dict (for external queries)."""
        return {
            "counter": self._counter,
            "is_negative": self._is_negative,
            "step_size": self._step_size,
            "auto_tick": self._auto_tick,
            "initial_count": self._initial_count,
            "max_count": self._max_count,
        }


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
# When run directly (python main.py), BasePlugin.run() will:
#   1. Register the overlay HTML with the API
#   2. Start the tick thread (on_tick)
#   3. Start the command polling thread (long-poll)
#   4. Open a pywebview window (unless --gui-hidden)
#   5. Print the OBS overlay URL (if --gui-hidden)
#
# In production, the plugin launcher starts plugins via the API,
# not by running this file directly.
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ExamplePlugin().run()
