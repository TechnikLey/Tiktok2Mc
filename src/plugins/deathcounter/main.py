import json
import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class DeathManager:
    """Thread-safe death counter."""

    def __init__(self, stats_path):
        self._stats_path = stats_path
        self._count = 0
        self._load()

    def _load(self):
        if self._stats_path.exists():
            try:
                data = json.loads(self._stats_path.read_text(encoding="utf-8"))
                self._count = data.get("deaths", 0)
            except Exception:
                pass

    def save(self):
        try:
            self._stats_path.parent.mkdir(parents=True, exist_ok=True)
            self._stats_path.write_text(
                json.dumps({"deaths": self._count}, indent=4),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add(self):
        self._count += 1
        self.save()

    def get_data(self):
        return {"deaths": self._count}


class DeathCounterPlugin(BasePlugin):
    PLUGIN_NAME = "death-counter"
    DEFAULT_PORT = 29190

    def __init__(self):
        super().__init__()
        self._stats_file = self._data_dir / "deaths.json"
        self._manager = DeathManager(self._stats_file)

        self.register_handler("player_death", self._on_death)
        self.register_handler("save_dims", self._on_save_dims)

    def _on_death(self, _):
        self._manager.add()
        self.push_state()

    def _on_save_dims(self, args):
        self.save_window_state(
            args.get("width", 500),
            args.get("height", 400),
        )

    def get_overlay_html(self) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@900&display=swap');
{self.theme_style}
        body, html {{
            background: var(--background); margin: 0; padding: 0;
            width: 100%; height: 100%; display: flex;
            flex-direction: column; justify-content: center; align-items: center;
            overflow: hidden; font-family: 'Inter', sans-serif; color: var(--text);
            user-select: none;
        }}
        .label {{ font-size: 12vh; font-weight: 700; opacity: 0.7; letter-spacing: 1.5vw; margin-bottom: -2vh; }}
        .count {{ font-size: 65vh; font-weight: 900; line-height: 1; }}
        .bump {{ transform: scale(1.05); transition: 0.1s; }}
    </style>
</head>
<body>
    <div id="card" style="display:flex; flex-direction:column; align-items:center;">
        <span class="label">DEATHS</span>
        <span id="counter" class="count">0</span>
    </div>
    <script>
        const card = document.getElementById('card');
        const counter = document.getElementById('counter');
        function connect() {{
            const es = new EventSource("/api/v1/plugins/death-counter/stream");
            es.onmessage = (e) => {{
                counter.innerText = JSON.parse(e.data).deaths;
                card.classList.add('bump');
                setTimeout(() => card.classList.remove('bump'), 200);
            }};
            es.onerror = () => {{ es.close(); setTimeout(connect, 2000); }};
        }}
        connect();
        window.addEventListener('resize', () => {{
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {{
                fetch('/api/v1/plugins/death-counter/command', {{
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
    DeathCounterPlugin().run()
