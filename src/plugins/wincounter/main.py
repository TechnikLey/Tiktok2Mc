import json
import logging

from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class WinManager:
    """Thread-safe win counter with milestone tracking."""

    def __init__(self, stats_path, initial_needed=10, theme=None):
        self._stats_path = stats_path
        self._theme = theme or {}
        self.wins, self.needed, self.record_low = 0, initial_needed, 0
        self._load()

    def _load(self):
        if self._stats_path.exists():
            try:
                data = json.loads(self._stats_path.read_text(encoding="utf-8"))
                self.wins = data.get("wins", 0)
                self.needed = data.get("needed", 10)
                self.record_low = data.get("record_low", 0)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                pass

    def save(self):
        try:
            self._stats_path.parent.mkdir(parents=True, exist_ok=True)
            self._stats_path.write_text(
                json.dumps(
                    {
                        "wins": self.wins,
                        "needed": self.needed,
                        "record_low": self.record_low,
                    },
                    indent=4,
                ),
                encoding="utf-8",
            )
        except (OSError, TypeError):
            pass

    def add(self, amount=1):
        self.wins += amount
        while self.wins >= self.needed:
            self.wins -= self.needed
            self.needed += 10
        self.save()

    def remove(self, amount=1):
        self.wins -= amount
        self.record_low = min(self.record_low, self.wins)
        self.save()

    def get_data(self):
        return {
            "wins": self.wins,
            "needed": self.needed,
            "record_low": self.record_low,
            "win_color": self._theme.get("danger", "#ff4444")
            if self.wins < 0
            else self._theme.get("text", "#ffffff"),
        }


class WinCounterPlugin(BasePlugin):
    PLUGIN_NAME = "win-counter"

    def __init__(self):
        super().__init__()
        cfg = self.config
        self._initial_needed = cfg.get("initial_needed", 10)
        self._milestone_increment = cfg.get("milestone_increment", 10)
        self._signal_on = set(cfg.get("signal_on", ["milestone", "record_low"]))
        self._stats_file = self._data_dir / "stats.json"
        self._manager = WinManager(
            self._stats_file,
            initial_needed=self._initial_needed,
            theme=self._theme,
        )

        self.register_handler("add_win", self._on_add_win)
        self.register_handler("remove_win", self._on_remove_win)
        self.register_handler("save_dims", self._on_save_dims)

    # -- event publishing ------------------------------------------------

    def _maybe_signal(self, event_type: str, extra: dict | None = None):
        if event_type in self._signal_on:
            data = self._manager.get_data()
            if extra:
                data.update(extra)
            self.publish_event(f"win.{event_type}", data)

    # -- command handlers ---------------------------------------------------

    def _on_add_win(self, args):
        prev_needed = self._manager.needed
        self._manager.add(int(args.get("amount", 1)))
        if self._manager.needed != prev_needed:
            self._maybe_signal(
                "milestone",
                {"milestone": self._manager.needed - self._milestone_increment},
            )
        self.push_state()

    def _on_remove_win(self, args):
        prev_record = self._manager.record_low
        self._manager.remove(int(args.get("amount", 1)))
        if self._manager.record_low != prev_record:
            self._maybe_signal("record_low", {"record_low": self._manager.record_low})
        self.push_state()

    def _on_save_dims(self, args):
        self.save_window_state(
            args.get("width", 600),
            args.get("height", 300),
        )

    # -- overlay HTML -------------------------------------------------------

    def get_overlay_html(self) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
    <style>
{self.theme_style}
        body {{
            background-color: var(--background); color: var(--text);
            font-family: 'Inter', 'Consolas', monospace; margin: 0;
            display: flex; flex-direction: column;
            justify-content: center; align-items: center;
            height: 100vh; width: 100vw;
            overflow: hidden; user-select: none;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{
            display: flex; align-items: center;
            gap: 3vw;
            font-size: 25vmin;
            font-weight: bold;
            white-space: nowrap;
            line-height: 1;
        }}
        .record-section {{
            margin-top: 1vh;
            font-size: 10vmin;
            color: var(--muted);
        }}
        .separator {{
            color: var(--separator);
            opacity: 0.5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <span>Wins:</span><span id="wins">0</span><span class="separator">|</span><span id="needed">10</span>
    </div>
    <div class="record-section">Record Low: <span id="record_low">0</span></div>
    <script>
        const es = new EventSource("/api/v1/plugins/win-counter/stream");
        es.onmessage = (e) => {{
            const d = JSON.parse(e.data);
            document.getElementById('wins').innerText = d.wins;
            document.getElementById('wins').style.color = d.win_color;
            document.getElementById('needed').innerText = d.needed;
            document.getElementById('record_low').innerText = d.record_low;
        }};
        window.addEventListener('resize', () => {{
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {{
                fetch('/api/v1/plugins/win-counter/command', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ command: 'save_dims', args: {{ width: window.outerWidth, height: window.outerHeight }} }})
                }});
            }}, 500);
        }});
    </script>
</body>
</html>"""

    def get_state(self):
        return self._manager.get_data()


if __name__ == "__main__":
    WinCounterPlugin().run()
