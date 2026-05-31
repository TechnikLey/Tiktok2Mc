import time
import logging

from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class TimerPlugin(BasePlugin):
    PLUGIN_NAME = "timer"
    DEFAULT_PORT = 29189

    def __init__(self):
        super().__init__()
        cfg = self.config
        self._initial_seconds = cfg.get("start_time", 10) * 60
        self._auto_win = cfg.get("auto_win", False)
        self._pause_on_death = cfg.get("pause_on_death", False)

        self._time_left = self._initial_seconds
        self._is_paused = False
        self._is_waiting = False
        self._lock = self._lock  # inherited from BasePlugin

        # Register command handlers
        self.register_handler("start", lambda _: self._start())
        self.register_handler("pause", lambda _: self._pause())
        self.register_handler("reset", lambda _: self._reset())
        self.register_handler("player_death", lambda _: self._on_death())
        self.register_handler("player_respawn", lambda _: self._on_respawn())

        # Internal command from overlay resize
        self.register_handler("save_dims", self._save_dims)

    # -- state helpers ------------------------------------------------------

    def _update_state(self):
        self.state = {
            "time_left": self._time_left,
            "is_paused": self._is_paused,
            "is_waiting": self._is_waiting,
            "initial": self._initial_seconds,
        }
        self.push_state()

    # -- command handlers ---------------------------------------------------

    def _start(self):
        self._is_paused = False
        self._update_state()

    def _pause(self):
        self._is_paused = True
        self._update_state()

    def _reset(self):
        self._time_left = self._initial_seconds
        self._is_waiting = False
        self._update_state()

    def _on_death(self):
        if self._pause_on_death:
            self._is_paused = True
            self._time_left = self._initial_seconds
            self._is_waiting = False
            self._update_state()

    def _on_respawn(self):
        if self._pause_on_death:
            self._is_paused = False
            self._update_state()

    def _save_dims(self, args):
        width = args.get("width", 400)
        height = args.get("height", 200)
        self.save_window_state(width, height)

    # -- tick -------------------------------------------------------------

    def on_tick(self):
        if not self._is_paused and not self._is_waiting and self._time_left > 0:
            self._time_left -= 1
            if self._time_left == 0:
                self._is_waiting = True
                if self._auto_win:
                    self.send_command("win-counter", "add_win", {"amount": 1})
                else:
                    log.info("[TIMER] Timer reached 0 (auto_win disabled)")
                self._time_left = self._initial_seconds
                self._is_waiting = False
        self._update_state()

    # -- overlay HTML ------------------------------------------------------

    def get_overlay_html(self) -> str:
        return """<!DOCTYPE html>
<html>
<head>
    <style>
{THEME_STYLE}
        body {{
            background-color: var(--background); color: var(--text); margin: 0;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; overflow: hidden; font-family: 'Segoe UI', sans-serif;
            -webkit-app-region: drag; user-select: none;
        }}
        #display {{
            font-size: 70vh; font-weight: bold;
            font-variant-numeric: tabular-nums; white-space: nowrap;
        }}
        .warning {{ color: var(--warning); }}
        .blink {{
            color: var(--blink);
            animation: syncFlash 1s infinite steps(1);
        }}
        .critical {{
            color: var(--danger) !important;
            animation: pulse 0.5s infinite ease-in-out;
        }}
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
    <div id="display">00:00</div>
    <script>
        const display = document.getElementById('display');

        function update(data) {{
            const t = data.time_left;
            const m = Math.floor(t / 60), s = t % 60;
            display.innerText = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');

            display.classList.remove('warning', 'blink', 'critical');

            if (t === 0 || data.is_waiting) {{
                display.classList.add('critical');
            }} else if (t <= 10) {{
                display.classList.add('critical');
            }} else if (t <= 30) {{
                display.classList.add('blink');
            }} else if (t <= 60) {{
                display.classList.add('warning');
            }}
        }}

        const evtSource = new EventSource('/api/v1/plugins/timer/stream');
        evtSource.onmessage = function(e) {{
            update(JSON.parse(e.data));
        }};

        window.addEventListener('resize', () => {{
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {{
                fetch('/api/v1/plugins/timer/command', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ command: 'save_dims', args: {{ width: window.outerWidth, height: window.outerHeight }} }})
                }});
            }}, 500);
        }});
    </script>
</body>
</html>
""".format(THEME_STYLE=self.theme_style)


if __name__ == '__main__':
    TimerPlugin().run()
