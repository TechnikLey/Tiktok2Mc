import logging
from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class LikeManager:
    """Like-goal counter with milestone progression."""

    def __init__(self, initial_goal, multiplier):
        self.likes = 0
        self.initial_goal = max(initial_goal, 1)
        self.multiplier = multiplier
        self.goal = self.initial_goal
        self.previous_goal = 0

    def add(self, amount=1):
        self.likes += amount
        while self.likes >= self.goal:
            if self.multiplier == 0:
                self.likes = 0
                self.goal = self.initial_goal
                self.previous_goal = 0
            elif self.multiplier == 1:
                self.likes -= self.goal
                self.previous_goal = self.goal
                self.goal += self.initial_goal
            else:
                self.likes -= self.goal
                self.previous_goal = self.goal
                self.goal = int(self.goal * self.multiplier)

    def get_data(self):
        segment_size = self.goal - self.previous_goal
        progress_in_segment = self.likes - self.previous_goal
        percent = round((progress_in_segment / segment_size) * 100, 2) if segment_size > 0 else 0
        return {
            "likes": self.likes,
            "goal": self.goal,
            "percent": percent,
        }


class LikeGoalPlugin(BasePlugin):
    PLUGIN_NAME = "like-goal"
    DEFAULT_PORT = 29193

    def __init__(self):
        super().__init__()
        cfg = self.config
        self._display_text = cfg.get("display_text", "Like Goal")
        self._initial_goal = max(int(cfg.get("initial_goal", 100_000)), 1)
        self._goal_multiplier = int(cfg.get("goal_multiplier", 2))
        self._signal_on = set(cfg.get("signal_on", ["milestone", "progress"]))
        self._manager = LikeManager(self._initial_goal, self._goal_multiplier)

        self.register_handler("add_likes", self._on_add_likes)
        self.register_handler("reset", self._on_reset)
        self.register_handler("save_dims", self._on_save_dims)

    # -- event publishing ------------------------------------------------

    def _maybe_signal(self, event_type: str, extra: dict | None = None):
        if event_type in self._signal_on:
            data = self._manager.get_data()
            if extra:
                data.update(extra)
            self.api_post("/events", {"type": f"likegoal.{event_type}", "data": data})

    # -- command handlers ---------------------------------------------------

    def _on_add_likes(self, args):
        prev_goal = self._manager.goal
        delta = int(args.get("amount", 0))
        if delta > 0:
            self._manager.add(delta)
            if self._manager.goal != prev_goal:
                self._maybe_signal("milestone", {"previous_goal": prev_goal, "new_goal": self._manager.goal})
            else:
                self._maybe_signal("progress")
        self.push_state()

    def _on_reset(self, _):
        self._manager.likes = 0
        self._manager.goal = self._initial_goal
        self._manager.previous_goal = 0
        self.push_state()

    def _on_save_dims(self, args):
        self.save_window_state(
            args.get("width", 900),
            args.get("height", 200),
        )

    # -- overlay HTML -------------------------------------------------------

    def get_overlay_html(self) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{self.theme_style}
    body {{
        margin: 0;
        padding: 0 20px;
        background: var(--background);
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        overflow: hidden;
        -webkit-font-smoothing: antialiased;
    }}
    .container {{
        width: 100%;
        max-width: 900px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}
    .milestone-command {{
        font-size: clamp(14px, 3vw, 20px);
        font-weight: 700;
        color: var(--text);
        text-shadow: 0 0 12px var(--danger);
        margin-bottom: 10px;
        letter-spacing: 1px;
        opacity: 0.9;
    }}
    .bar-bg {{
        width: 100%;
        height: 60px;
        background: rgba(255, 255, 255, 0.05);
        border: 2px solid rgba(255, 255, 255, 0.1);
        position: relative;
        overflow: hidden;
        border-radius: 6px;
        box-shadow: inset 0 0 20px rgba(0,0,0,0.3);
    }}
    .bar-fill {{
        height: 100%;
        width: 0%;
        background: linear-gradient(90deg, var(--accent), var(--accent2));
        transition: width 0.5s ease-out;
        border-radius: 6px;
        box-shadow: 0 0 16px var(--accent);
    }}
    .text-overlay {{
        position: absolute;
        width: 100%;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: var(--text);
        font-size: 22px;
        font-weight: 900;
        text-align: center;
        text-shadow: 0 2px 6px rgba(0,0,0,0.8);
        z-index: 10;
    }}
</style>
</head>
<body id="body">
<div class="container">
    <div class="milestone-command" id="command">{self._display_text}</div>
    <div class="bar-bg">
        <div class="bar-fill" id="bar"></div>
        <div class="text-overlay" id="text">0% (0 / {self._initial_goal:,})</div>
    </div>
</div>
<script>
const evtSource = new EventSource("/api/v1/plugins/like-goal/stream");
evtSource.onmessage = function(event) {{
    try {{
        const data = JSON.parse(event.data);
        document.getElementById("bar").style.width = data.percent + "%";
        document.getElementById("text").innerText = `${{data.percent}}% (${{data.likes.toLocaleString()}} / ${{data.goal.toLocaleString()}})`;
    }} catch (e) {{ console.error(e); }}
}};
evtSource.onerror = function() {{ console.log("Connection lost... Reconnecting."); }};
</script>
</body>
</html>"""

    def get_state(self):
        return self._manager.get_data()


if __name__ == "__main__":
    LikeGoalPlugin().run()
