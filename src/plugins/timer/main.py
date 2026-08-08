#!/usr/bin/env python3
"""Timer Plugin — fully decoupled, configurable count-up / count-down timer.

Publishes timer lifecycle events to the central EventBus via POST /api/v1/events
so that any consumer (hooks, other plugins, dashboard) can react without
hardcoded coupling.

Supported commands (via API command queue):
    start, pause, resume, reset, add_time, set_time

Published EventBus events:
    timer.started, timer.paused, timer.resumed, timer.reset,
    timer.tick, timer.zero, timer.milestone
"""

import logging

from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class TimerPlugin(BasePlugin):
    PLUGIN_NAME = "timer"

    def __init__(self):
        super().__init__()
        cfg = self.config

        # ---- configuration -------------------------------------------------
        self._direction = cfg.get("direction", "down")          # "up" | "down"
        self._start_time = int(cfg.get("start_time", 600))      # seconds
        self._auto_start = cfg.get("auto_start", False)
        self._loop = cfg.get("loop", False)
        self._reset_on = set(cfg.get("reset_on", ["zero"]))    # list of str
        self._signal_on = set(cfg.get("signal_on", ["zero"]))  # list of str
        self._milestones = sorted({int(m) for m in cfg.get("milestones", [])})
        self._format = cfg.get("format", "mm:ss")               # "mm:ss" | "hh:mm:ss" | "seconds"
        self._time_step = int(cfg.get("time_step", 1))          # seconds per tick

        # ---- runtime state -------------------------------------------------
        self._current = 0 if self._direction == "up" else self._start_time
        self._is_paused = not self._auto_start
        self._is_waiting = False
        self._milestones_sent = set()

        # ---- command handlers ----------------------------------------------
        self.register_handler("start", lambda _: self._start())
        self.register_handler("pause", lambda _: self._pause())
        self.register_handler("resume", lambda _: self._resume())
        self.register_handler("reset", lambda _: self._reset())
        self.register_handler("add_time", self._on_add_time)
        self.register_handler("set_time", self._on_set_time)
        self.register_handler("save_dims", self._on_save_dims)

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _publish(self, event_type: str, data: dict):
        """Broadcast an event to the central EventBus (no coupling)."""
        try:
            self.api_post("/events", {"type": event_type, "data": data})
        except (OSError, TypeError) as e:
            log.warning("[TIMER] Failed to publish event %s: %s", event_type, e)

    def _update_state(self):
        self.state = {
            "current": self._current,
            "initial": self._start_time,
            "direction": self._direction,
            "is_paused": self._is_paused,
            "is_waiting": self._is_waiting,
            "format": self._format,
        }
        self.push_state()

    def _should_reset(self, trigger: str) -> bool:
        return trigger in self._reset_on

    def _should_signal(self, trigger: str) -> bool:
        return trigger in self._signal_on

    def _maybe_signal(self, trigger: str, extra: dict | None = None):
        if self._should_signal(trigger):
            data = {"current": self._current, "initial": self._start_time, "direction": self._direction}
            if extra:
                data.update(extra)
            self._publish(f"timer.{trigger}", data)

    def _format_display(self) -> str:
        t = self._current
        if self._format == "seconds":
            return str(t)
        if self._format == "hh:mm:ss":
            h, rem = divmod(t, 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        # default mm:ss
        m, s = divmod(t, 60)
        return f"{m:02d}:{s:02d}"

    # ------------------------------------------------------------------
    #  Command handlers
    # ------------------------------------------------------------------

    def _start(self):
        self._is_paused = False
        self._is_waiting = False
        self._maybe_signal("started")
        self._update_state()

    def _pause(self):
        self._is_paused = True
        self._maybe_signal("paused")
        self._update_state()

    def _resume(self):
        self._is_paused = False
        self._is_waiting = False
        self._maybe_signal("resumed")
        self._update_state()

    def _reset(self):
        self._current = 0 if self._direction == "up" else self._start_time
        self._is_waiting = False
        self._milestones_sent.clear()
        self._maybe_signal("reset")
        self._update_state()

    def _on_add_time(self, args: dict):
        secs = int(args.get("seconds", 0))
        if self._direction == "up":
            self._current = max(0, self._current + secs)
        else:
            self._current = max(0, self._current + secs)
        self._update_state()

    def _on_set_time(self, args: dict):
        secs = int(args.get("seconds", self._start_time))
        self._current = max(0, secs)
        self._update_state()

    def _on_save_dims(self, args: dict):
        width = args.get("width", 400)
        height = args.get("height", 200)
        self.save_window_state(width, height)

    # ------------------------------------------------------------------
    #  Tick loop
    # ------------------------------------------------------------------

    def on_tick(self):
        if self._is_paused or self._is_waiting:
            self._update_state()
            return

        # Tick
        if self._direction == "up":
            self._current += self._time_step
        else:
            self._current = max(0, self._current - self._time_step)

        self._maybe_signal("tick", {"display": self._format_display()})

        # Milestones (for count-down: trigger at or below; for count-up: trigger at or above)
        for ms in self._milestones:
            if ms not in self._milestones_sent:
                hit = (self._direction == "down" and self._current <= ms) or \
                      (self._direction == "up" and self._current >= ms)
                if hit:
                    self._milestones_sent.add(ms)
                    self._maybe_signal("milestone", {"milestone": ms})

        # Zero handling
        if self._current == 0 and self._direction == "down":
            self._is_waiting = True
            self._maybe_signal("zero")

            if self._should_reset("zero"):
                if self._loop:
                    self._current = self._start_time
                    self._is_waiting = False
                    self._milestones_sent.clear()
                    self._maybe_signal("reset", {"reason": "loop"})
                else:
                    self._is_paused = True
                    self._maybe_signal("paused", {"reason": "zero_reached"})

        self._update_state()

    # ------------------------------------------------------------------
    #  Overlay HTML
    # ------------------------------------------------------------------

    def get_overlay_html(self) -> str:
        display = self._format_display()
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="dark">
<style>
{self.theme_style}
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
        -webkit-app-region: drag;
        user-select: none;
        -webkit-font-smoothing: antialiased;
    }}
    #display {{
        font-size: 70vh;
        font-weight: bold;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
        color: var(--text);
        transition: color 0.3s ease;
    }}
    .warning {{ color: var(--warning) !important; }}
    .blink {{ color: var(--blink) !important; animation: syncFlash 1s infinite steps(1); }}
    .critical {{ color: var(--danger) !important; animation: pulse 0.5s infinite ease-in-out; }}
    @keyframes syncFlash {{
        0% {{ opacity: 1; }}
        50% {{ opacity: 0.2; }}
        100% {{ opacity: 1; }}
    }}
    @keyframes pulse {{
        0% {{ transform: scale(1); }}
        50% {{ transform: scale(1.08); }}
        100% {{ transform: scale(1); }}
    }}
</style>
</head>
<body>
    <div id="display">{display}</div>
    <script>
        const display = document.getElementById('display');
        const milestones = {self._milestones};

        function fmt(t) {{
            const f = "{self._format}";
            if (f === "seconds") return String(t);
            if (f === "hh:mm:ss") {{
                const h = Math.floor(t / 3600), rem = t % 3600;
                const m = Math.floor(rem / 60), s = rem % 60;
                return String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
            }}
            const m = Math.floor(t / 60), s = t % 60;
            return String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
        }}

        function update(data) {{
            const t = data.current || 0;
            const dir = data.direction || 'down';
            const init = data.initial || 0;
            display.innerText = fmt(t);

            display.classList.remove('warning', 'blink', 'critical');

            if (data.is_waiting || (dir === 'down' && t === 0)) {{
                display.classList.add('critical');
                return;
            }}

            if (dir === 'down') {{
                if (t <= 10) display.classList.add('critical');
                else if (t <= 30) display.classList.add('blink');
                else if (t <= 60) display.classList.add('warning');
            }} else {{
                // count-up styling: milestone-based
                const passed = milestones.filter(m => t >= m).length;
                if (passed >= milestones.length && milestones.length > 0) display.classList.add('critical');
                else if (passed > 0) display.classList.add('blink');
            }}
        }}

        const evtSource = new EventSource('/api/v1/plugins/timer/stream');
        evtSource.onmessage = function(e) {{
            try {{ update(JSON.parse(e.data)); }} catch(err) {{}}
        }};

        window.addEventListener('resize', () => {{
            clearTimeout(window._rt);
            window._rt = setTimeout(() => {{
                fetch('/api/v1/plugins/timer/command', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ command: 'save_dims', args: {{ width: window.outerWidth, height: window.outerHeight }} }})
                }});
            }}, 500);
        }});
    </script>
</body>
</html>"""


if __name__ == '__main__':
    TimerPlugin().run()
