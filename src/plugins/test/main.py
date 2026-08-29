#!/usr/bin/env python3
"""
test plugin — Interactive developer sandbox for TikTok2MC
==========================================================

NOT included in release builds (see build.py exclusion). This plugin is a
living example: start it, click around in its dashboard tab and watch what
happens on the API. Every feature below is annotated with the endpoint that
triggers it.

FEATURES DEMONSTRATED
---------------------
  1.  BasePlugin lifecycle (__init__ / run / on_stop)
  2.  Config loading (config.yaml merged with config_schema defaults)
  3.  Command handlers (POST /api/v1/plugins/test/command)
  4.  State push + live overlay via EventSource (/plugins/test/stream)
  5.  Event publishing with namespaced types + versioned data_schema
      ("events" permission)
  6.  Persistent store (store_get/store_set, "store" permission)
  7.  Queries — request/response with correlation ids
      (POST /api/v1/plugins/test/query, declared in plugin.json "queries")
  8.  Generic RPC endpoint (POST /api/v1/plugins/test/rpc)
  9.  Dashboard UI tab (dashboard_ui: true + get_dashboard_html())
  10. Tick loop (on_tick) and graceful shutdown (on_stop)

TRY IT
------
  Dashboard : open the web dashboard -> "Test" tab -> use the buttons
  Commands  : POST /api/v1/plugins/test/command {"command": "ping"}
  Query     : POST /api/v1/plugins/test/query   {"query": "stats"}
  RPC       : POST /api/v1/plugins/test/rpc     {"method": "GET", "path": "/stats"}
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.base_plugin import BasePlugin

log = logging.getLogger(__name__)


class TestPlugin(BasePlugin):
    """Sandbox plugin — bump a counter, echo messages, fire events."""

    # Unique id: used in endpoints /api/v1/plugins/test/..., health monitor,
    # store namespace and event namespace ("test.*").
    PLUGIN_NAME = "test"

    def __init__(self):
        # super().__init__() loads config.yaml + plugin.json defaults, theme,
        # window state and registers with the health monitor.
        super().__init__()

        cfg = self.config
        self._milestone_step = max(1, int(cfg.get("milestone", 10)))

        # ---- runtime state -------------------------------------------------
        self._counter = 0
        self._bumps_total = 0
        self._last_message = ""
        self._last_message_at = ""
        self._started_monotonic = time.monotonic()
        self._uptime_shown = -1

        # ---- restore previous session from the persistent store ------------
        # store_get() hits GET /api/v1/plugins/test/data/state and requires
        # the "store" permission in plugin.json. It returns None when the
        # key does not exist (first run) or was never persisted.
        saved = self.store_get("state")
        if isinstance(saved, dict):
            self._counter = int(saved.get("counter", 0))
            self._last_message = str(saved.get("last_message", ""))
            log.info("[TEST] Restored state from store: %s", saved)

        # ---- command handlers ----------------------------------------------
        # Each entry maps a command name (POST .../command {"command": ...})
        # to a callback receiving the command's "args" dict.
        self.register_handler("ping", self._on_ping)
        self.register_handler("echo", self._on_echo)
        self.register_handler("bump", self._on_bump)
        self.register_handler("reset", self._on_reset)
        self.register_handler("save_dims", self._on_save_dims)

        self._update_state()
        log.info(
            "[TEST] Sandbox ready. milestone=%s, restored_counter=%s",
            self._milestone_step,
            self._counter,
        )

    # ======================================================================
    #  COMMAND HANDLERS
    # ======================================================================

    def _on_ping(self, _args: dict[str, Any]) -> None:
        """`ping` — publishes a test.pong event on the EventBus."""
        self.publish_event("test.pong", {})
        log.info("[TEST] ping -> published test.pong")

    def _on_echo(self, args: dict[str, Any]) -> None:
        """`echo` — stores a message, publishes test.echo, updates state."""
        message = str(args.get("message", "")).strip()
        if not message:
            log.warning("[TEST] echo called without 'message' arg")
            return
        self._last_message = message
        self._last_message_at = time.strftime("%H:%M:%S")
        # The payload is validated server-side against the data_schema
        # declared for "test.echo" in plugin.json (HTTP 422 on violation).
        self.publish_event(
            "test.echo", {"message": message, "at": self._last_message_at}
        )
        self._update_state()

    def _on_bump(self, args: dict[str, Any]) -> None:
        """`bump` — increases the counter, fires a milestone event sometimes."""
        amount = max(1, int(args.get("amount", 1)))
        self._counter += amount
        self._bumps_total += 1
        if self._counter >= self._next_milestone:
            self._next_milestone += self._milestone_step
            self.publish_event(
                "test.bump_milestone",
                {"total": self._counter, "step": self._milestone_step},
            )
        self._update_state()

    def _on_reset(self, _args: dict[str, Any]) -> None:
        """`reset` — zeroes the counter (persisted values survive restarts)."""
        self._counter = 0
        self._next_milestone = self._milestone_step
        self._update_state()

    def _on_save_dims(self, args: dict[str, Any]) -> None:
        """`save_dims` — sent by the overlay JS when the window is resized."""
        self.save_window_state(args.get("width", 500), args.get("height", 400))

    # ======================================================================
    #  QUERIES  (POST /api/v1/plugins/test/query)
    # ======================================================================
    # Request/response with correlation ids: another plugin or hook calls
    # query_plugin("test", "stats") / HookAPI.query_hook(...). Declared
    # query names in plugin.json give callers fast feedback for typos.

    def on_query(self, query: str, args: dict[str, Any]) -> Any:
        if query == "last_message":
            return {
                "message": self._last_message,
                "at": self._last_message_at,
            }
        if query == "stats":
            return self._stats()
        # Unknown queries fall through to BasePlugin's debug log + None.
        return super().on_query(query, args)

    # ======================================================================
    #  GENERIC RPC  (POST /api/v1/plugins/test/rpc)
    # ======================================================================
    # A small REST-style surface without extra server routes: any external
    # client can call {"method": "GET", "path": "/stats"} against this
    # plugin. The return value is JSON-serialized for the caller.

    def on_rpc(self, method: str, path: str, body: dict[str, Any]) -> Any:
        if method == "GET" and path == "/stats":
            return self._stats()
        if method == "POST" and path == "/echo":
            self._on_echo({"message": str(body.get("message", ""))})
            return {"ok": True, "message": self._last_message}
        raise ValueError(f"no such endpoint: {method} {path}")

    # ======================================================================
    #  TICK LOOP + GRACEFUL SHUTDOWN
    # ======================================================================

    def on_tick(self) -> None:
        """Called once per second. Pushes uptime every 5 s as a demo."""
        uptime = int(time.monotonic() - self._started_monotonic)
        if uptime // 5 != self._uptime_shown:
            self._uptime_shown = uptime // 5
            self._update_state()

    def on_stop(self) -> None:
        """Runs exactly once on shutdown (disable/restart/process exit).

        Persist the session so the next start restores it via store_get().
        Exceptions are logged by BasePlugin and never block the exit.
        """
        self.store_set(
            "state",
            {
                "counter": self._counter,
                "bumps_total": self._bumps_total,
                "last_message": self._last_message,
            },
        )
        log.info("[TEST] Stopped. Persisted counter=%s", self._counter)

    # ======================================================================
    #  STATE + OVERLAY + DASHBOARD
    # ======================================================================

    def _stats(self) -> dict[str, Any]:
        return {
            "counter": self._counter,
            "bumps_total": self._bumps_total,
            "uptime_sec": int(time.monotonic() - self._started_monotonic),
        }

    def _update_state(self) -> None:
        """Build the state dict and push it (-> live update on all clients)."""
        stats = self._stats()
        self.state = {
            **stats,
            "last_message": self._last_message,
            "last_message_at": self._last_message_at,
            "next_milestone": self._next_milestone,
        }
        self.push_state()

    def get_overlay_html(self) -> str:
        """Minimal OBS overlay: shows the live counter via EventSource."""
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{self.theme_style}
    body {{
        background: transparent; margin: 0; height: 100vh;
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; font-family: 'Inter', sans-serif;
        color: var(--text); user-select: none;
    }}
    .label {{ font-size: 3vh; letter-spacing: 0.4vw; opacity: 0.6;
              text-transform: uppercase; }}
    .count {{ font-size: 40vh; font-weight: 900; line-height: 1; }}
</style>
</head>
<body>
    <div class="label">Test Counter</div>
    <div id="count" class="count">{self._counter}</div>
    <script>
        const el = document.getElementById('count');
        const es = new EventSource("/api/v1/plugins/{self.PLUGIN_NAME}/stream");
        es.onmessage = (e) => {{ el.innerText = JSON.parse(e.data).counter; }};
        window.addEventListener('resize', () => {{
            clearTimeout(window.rt);
            window.rt = setTimeout(() => {{
                fetch('/api/v1/plugins/{self.PLUGIN_NAME}/command', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        command: 'save_dims',
                        args: {{ width: window.outerWidth, height: window.outerHeight }},
                    }}),
                }});
            }}, 300);
        }});
    </script>
</body>
</html>"""

    def get_dashboard_html(self) -> str:
        """Dashboard tab (iframe in the web dashboard, same origin as API).

        Demonstrates all three client-side interaction styles:
          commands  (cmd)      — fire-and-forget
          query     (queryLast)— request/response
          rpc       (rpcStats) — REST-style custom endpoint
        """
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{self.theme_style}
    body {{
        background: var(--background); color: var(--text); margin: 0;
        padding: 24px; font-family: 'Inter', system-ui, sans-serif;
        user-select: none;
    }}
    .count {{ font-size: 64px; font-weight: 900; margin: 4px 0 16px; }}
    .label {{ font-size: 12px; font-weight: 700; letter-spacing: 2px;
              opacity: 0.6; text-transform: uppercase; }}
    .row {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
    button {{
        background: var(--accent); color: var(--background); border: 0;
        border-radius: 6px; cursor: pointer; font: inherit;
        font-weight: 700; padding: 10px 18px;
    }}
    button:hover {{ filter: brightness(1.15); }}
    input {{
        background: transparent; border: 1px solid var(--accent);
        border-radius: 6px; color: var(--text); font: inherit;
        padding: 9px 12px; width: 220px;
    }}
    pre {{
        background: rgba(255, 255, 255, 0.05); border-radius: 6px;
        font-size: 12px; overflow-x: auto; padding: 12px;
    }}
</style>
</head>
<body>
    <div class="label">Counter</div>
    <div id="count" class="count">{self._counter}</div>

    <div class="row">
        <button onclick="cmd('bump', {{}})">Bump</button>
        <button onclick="cmd('reset', {{}})">Reset</button>
        <input id="msg" placeholder="Message for echo..."
               onkeydown="if(event.key==='Enter') echo()">
        <button onclick="echo()">Echo</button>
        <button onclick="cmd('ping', {{}})">Ping (fires event)</button>
    </div>

    <div class="label">Query response (POST /plugins/test/query)</div>
    <pre id="query_out">-</pre>

    <div class="label">RPC response (POST /plugins/test/rpc)</div>
    <pre id="rpc_out">-</pre>

    <script>
        const countEl = document.getElementById('count');

        function cmd(command, args) {{
            fetch('/api/v1/plugins/{self.PLUGIN_NAME}/command', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{ command, args }}),
            }});
        }}

        function echo() {{
            const message = document.getElementById('msg').value.trim();
            if (message) cmd('echo', {{ message }});
        }}

        function queryLast() {{
            fetch('/api/v1/plugins/{self.PLUGIN_NAME}/query', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{ query: 'last_message', args: {{}} }}),
            }})
                .then((r) => r.json())
                .then((d) => {{
                    document.getElementById('query_out').textContent =
                        JSON.stringify(d, null, 2);
                }});
        }}

        function rpcStats() {{
            fetch('/api/v1/plugins/{self.PLUGIN_NAME}/rpc', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{ method: 'GET', path: '/stats', body: {{}} }}),
            }})
                .then((r) => r.json())
                .then((d) => {{
                    document.getElementById('rpc_out').textContent =
                        JSON.stringify(d, null, 2);
                }});
        }}

        setInterval(queryLast, 3000);
        setInterval(rpcStats, 3000);

        const es = new EventSource('/api/v1/plugins/{self.PLUGIN_NAME}/stream');
        es.onmessage = (e) => {{
            countEl.innerText = JSON.parse(e.data).counter;
        }};
    </script>
</body>
</html>"""


# ======================================================================
#  ENTRY POINT
# ======================================================================
# Started by the plugin launcher (or manually: python src/plugins/test/main.py).
# run() registers overlay + dashboard HTML, starts tick/poll threads and
# opens the pywebview window unless --gui-hidden is set.
# ======================================================================
if __name__ == "__main__":
    TestPlugin().run()
