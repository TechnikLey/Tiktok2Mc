#!/usr/bin/env python3
"""Troubleshooting launcher for the TikTok2Mc bridge (src/python/main.py).

Runs the *real* bridge process against a real TikTok account inside a
disposable sandbox directory (tests/workspace/bridge_debug/) so the repo is
never modified: config, data, datapack and runtime signals all live in the
sandbox (main.py env overrides ``TIKTOK2MC_BASE_PARENT`` /
``TIKTOK2MC_RUNTIME_DIR``). TikTokLive's own DEBUG logging is switched on to
show whether the websocket delivers events at all.

It then watches the bridge log for the markers that tell us *where* in the
pipeline events get stuck:

  [TIKTOK][RAW]        -> websocket delivered the event to the handler
  [LIKE] / [LIKE DEBUG] -> like pipeline initialized / milestone math
  [ACTION] Trigger:    -> a trigger reached the command queue
  [TIKTOK][WATCHDOG]   -> live, but no raw event for 60s (stalled receiver)
  CRITICAL ERROR ...   -> client loop crashed
  TikTok event handler error -> a handler raised (loop kept alive)

Usage:
    python tools/bridge_debug.py --user zeegelaar36 --duration 120
    python tools/bridge_debug.py --user X --like-every 1 --duration 300 --keep-sandbox

Exit code: 0 = PASS, 1 = FAIL/uncertain, 2 = process exited unexpectedly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlreq

ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = ROOT / "src" / "python" / "main.py"
SRC = ROOT / "src"
SANDBOX_ROOT = ROOT / "tests" / "workspace" / "bridge_debug"

RE_CONNECTED = re.compile(r"Live connection established: @(\S+)")
RE_RAW = re.compile(r"\[TIKTOK\]\[RAW\] (\w+) event #(\d+) received")
RE_INITIAL_LIKE = re.compile(r"\[LIKE\] Initial count set: (\d+)")
RE_MILESTONE = re.compile(r"\[LIKE\] Trigger '([^']+)' -> \+(\d+)")
RE_ACTION = re.compile(r"\[ACTION\] Trigger: (\S+)")
RE_STALL = re.compile(r"\[TIKTOK\]\[WATCHDOG\]")
RE_CRASH = re.compile(r"CRITICAL ERROR IN TIKTOK CLIENT")
RE_HANDLER_ERR = re.compile(r"TikTok event handler error")
RE_BLOCKED = re.compile(r"DEVICE_BLOCKED")
RE_TEST_COMMENT = re.compile(r"\[TEST COMMENT\]")
RE_RECONNECT = re.compile(r"Reconnect")
RE_CONFIG_ERROR = re.compile(r"Config not found|Config (?:error|Error)")
RE_EVENTBUS_FAIL = re.compile(r"Failed to publish .* to EventBus")
RE_TIKTOKLIVE = re.compile(r"^\[TikTokLive\] ")


class Monitor:
    """Thread-safe classifier for the child process log lines."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lines: list[str] = []
        self.raw: dict[str, int] = {}
        self.total_raw = 0
        self.connected_user: str | None = None
        self.initial_likes: str | None = None
        self.milestones: list[tuple[str, str]] = []
        self.actions: list[str] = []
        self.test_comments = 0
        self.reconnects = 0
        self.handler_errors = 0
        self.eventbus_fail = 0
        self.fatal: list[str] = []
        self.config_errors: list[str] = []
        self.tiktoklive_lines = 0
        self.last_line_ts = time.monotonic()

    def feed(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)
            self.last_line_ts = time.monotonic()

            m = RE_CONNECTED.search(line)
            if m:
                self.connected_user = m.group(1)
            m = RE_RAW.search(line)
            if m:
                etype = m.group(1)
                self.raw[etype] = self.raw.get(etype, 0) + 1
                self.total_raw += 1
            m = RE_INITIAL_LIKE.search(line)
            if m:
                self.initial_likes = m.group(1)
            for match in RE_MILESTONE.finditer(line):
                self.milestones.append((match.group(1), match.group(2)))
            for match in RE_ACTION.finditer(line):
                self.actions.append(match.group(1))
            if RE_TEST_COMMENT.search(line):
                self.test_comments += 1
            if RE_RECONNECT.search(line):
                self.reconnects += 1
                self.fatal[:] = [
                    f for f in self.fatal if f not in ("CRASH", "DEVICE_BLOCKED")
                ]
            if RE_HANDLER_ERR.search(line):
                self.handler_errors += 1
            if RE_EVENTBUS_FAIL.search(line):
                self.eventbus_fail += 1
            if RE_CONFIG_ERROR.search(line):
                self.config_errors.append(line.strip())
            if RE_TIKTOKLIVE.match(line):
                self.tiktoklive_lines += 1
            for flag, pattern in (
                ("STALL", RE_STALL),
                ("CRASH", RE_CRASH),
                ("DEVICE_BLOCKED", RE_BLOCKED),
            ):
                if pattern.search(line) and flag not in self.fatal:
                    self.fatal.append(flag)

    def tail(self, n: int = 80) -> list[str]:
        with self.lock:
            return list(self.lines[-n:])

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "raw": dict(self.raw),
                "total_raw": self.total_raw,
                "connected_user": self.connected_user,
                "initial_likes": self.initial_likes,
                "milestones": list(self.milestones),
                "actions": list(self.actions),
                "test_comments": self.test_comments,
                "reconnects": self.reconnects,
                "handler_errors": self.handler_errors,
                "eventbus_fail": self.eventbus_fail,
                "fatal": list(self.fatal),
                "config_errors": list(self.config_errors),
                "tiktoklive_lines": self.tiktoklive_lines,
                "quiet_seconds": time.monotonic() - self.last_line_ts,
            }


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 4.0):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urlreq.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlreq.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urlerror.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urlerror.URLError:
        return None, ""


def make_sandbox(user: str, like_every: int | None) -> Path:
    """Build a disposable bridge home under tests/workspace; repo untouched."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    sandbox = SANDBOX_ROOT / stamp
    (sandbox / "config").mkdir(parents=True, exist_ok=True)
    (sandbox / "data").mkdir(parents=True, exist_ok=True)
    (sandbox / "core" / "runtime").mkdir(parents=True, exist_ok=True)

    cfg = sandbox / "config" / "config.yaml"
    shutil.copy2(ROOT / "defaults" / "config.yaml", cfg)
    for name in ("actions.mca", "comment_commands.yaml"):
        shutil.copy2(ROOT / "defaults" / name, sandbox / "data" / name)
    (sandbox / "data" / "followed_users.txt").write_text("", encoding="utf-8")

    from ruamel.yaml import YAML

    yml = YAML()
    data = yml.load(cfg.read_text(encoding="utf-8"))
    data.setdefault("tiktok", {})["user"] = user
    if like_every is not None:
        changed = 0
        for rule in data.get("like_triggers") or []:
            if rule.get("enabled", True):
                rule["every"] = like_every
                changed += 1
        print(f"[sandbox] like_triggers.every -> {like_every} ({changed} rules)")
    with cfg.open("w", encoding="utf-8") as fh:
        yml.dump(data, fh)
    return sandbox


def launch_bridge(env: dict) -> subprocess.Popen:
    cmd = [sys.executable, str(MAIN_PY)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env=env,
        bufsize=1,
    )
    return proc


def spawn_reader(
    proc: subprocess.Popen, mon: Monitor, verbose: bool
) -> threading.Thread:
    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if verbose:
                print(line)
            mon.feed(line)

    t = threading.Thread(target=_read, name="bridge-log-reader", daemon=True)
    t.start()
    return t


def probe_webhook(port: int, timeout: float) -> dict:
    base = f"http://127.0.0.1:{port}"
    result: dict = {"health": None, "test_comment": None, "custom_trigger": None}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _ = http_json("GET", f"{base}/health")
        if status == 200:
            result["health"] = status
            break
        time.sleep(1.0)
    if result["health"] == 200:
        status, _ = http_json(
            "POST",
            f"{base}/test_comment",
            {"user": "BridgeSmokeTest", "text": "smoke test"},
        )
        result["test_comment"] = status
        status, _ = http_json(
            "POST",
            f"{base}/custom_trigger",
            {"trigger": "likes", "user": "BridgeSmokeTest"},
        )
        result["custom_trigger"] = status
    return result


def kill_child(proc: subprocess.Popen, reader: threading.Thread) -> None:
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    reader.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the real bridge (src/python/main.py) in a throwaway sandbox for troubleshooting.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--user", default="zeegelaar36", help="TikTok username to connect to"
    )
    parser.add_argument(
        "--duration", type=float, default=180, help="total runtime in seconds"
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=90,
        help="seconds to wait for a live connection",
    )
    parser.add_argument(
        "--like-every",
        type=int,
        default=None,
        help="test override: set every='N' on all enabled like_triggers",
    )
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=29188,
        help="bridge webhook port (minecraft_server_api.web_server_port)",
    )
    parser.add_argument(
        "--no-probe", action="store_true", help="skip webhook probe requests"
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="do not switch on TikTokLive DEBUG logging",
    )
    parser.add_argument(
        "--keep", action="store_true", help="do not terminate the bridge at the end"
    )
    parser.add_argument(
        "--keep-sandbox",
        action="store_true",
        help="keep the sandbox dir for inspection",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="echo every bridge log line live"
    )
    args = parser.parse_args()

    if not MAIN_PY.exists():
        print(f"ERROR: bridge not found: {MAIN_PY}")
        return 1

    print("=" * 72)
    print(f"TikTok2Mc bridge DEBUG run  (user: @{args.user})")
    print("=" * 72)

    sandbox = make_sandbox(args.user, args.like_every)
    print(f"[sandbox] {sandbox}")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TIKTOK2MC_BASE_PARENT"] = str(sandbox)
    env["TIKTOK2MC_RUNTIME_DIR"] = str(sandbox / "core" / "runtime")
    if not args.no_debug:
        env["TIKTOK2MC_DEBUG"] = "1"

    proc = launch_bridge(env)
    print(f"[run] pid={proc.pid} cmd={sys.executable} {MAIN_PY.name}")
    print("[run] TikTokLive DEBUG log: " + ("ON" if not args.no_debug else "OFF"))
    print("[run] log reader active - Ctrl+C to abort (child will be killed)\n")

    mon = Monitor()
    reader = spawn_reader(proc, mon, args.verbose)
    start = time.monotonic()
    connected = False
    probe_done = False
    probe_result: dict = {}
    child_exit = False
    last_progress = -1

    def _interrupt(_sig, _frame) -> None:
        print("\n[ctrl+c] aborting, killing bridge ...")
        kill_child(proc, reader)
        sys.exit(130)

    signal.signal(signal.SIGINT, _interrupt)

    try:
        while True:
            if proc.poll() is not None:
                child_exit = True
                print(
                    f"\n[run] bridge process EXITED unexpectedly (rc={proc.returncode})"
                )
                break
            snap = mon.snapshot()

            if not connected and snap["connected_user"]:
                connected = True
                print(
                    f"\n[+ok] LIVE connected as @{snap['connected_user']} "
                    f"(after {time.monotonic() - start:.0f}s)"
                )

            if not probe_done and not args.no_probe and time.monotonic() - start >= 3:
                probe_result = probe_webhook(args.webhook_port, args.connect_timeout)
                probe_done = True
                print(
                    f"\n[probe] /health={probe_result['health']} "
                    f"/test_comment={probe_result['test_comment']} "
                    f"/custom_trigger(likes)={probe_result['custom_trigger']}"
                )

            if not connected and time.monotonic() - start > args.connect_timeout:
                print(f"\n[FAIL] no live connection within {args.connect_timeout:.0f}s")
                break
            if time.monotonic() - start > args.duration:
                break

            elapsed = time.monotonic() - start
            if int(elapsed) % 15 == 0 and int(elapsed) != last_progress:
                last_progress = int(elapsed)
                raw_txt = (
                    ", ".join(f"{k}@{v}" for k, v in snap["raw"].items()) or "none"
                )
                fatal_txt = ",".join(snap["fatal"]) or "-"
                print(
                    f"[..] t={elapsed:6.0f}s raw=[{raw_txt}] fatal={fatal_txt} "
                    f"quiet={snap['quiet_seconds']:.0f}s"
                )
            time.sleep(0.4)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"\n[error] test loop failed: {exc!r}")
        kill_child(proc, reader)
        return 1

    if not args.keep:
        print("\n[run] terminating bridge ...")
        kill_child(proc, reader)

    snap = mon.snapshot()
    duration = time.monotonic() - start

    print("\n" + "=" * 72)
    print("DEBUG SUMMARY")
    print("=" * 72)
    checks: list[tuple[str, bool | None, str]] = []

    ok = not snap["config_errors"]
    checks.append(
        ("CONFIG_LOAD", ok, "no config errors" if ok else snap["config_errors"][0])
    )
    ok = connected and snap["connected_user"] == args.user
    checks.append(
        (
            "CONNECTED",
            ok,
            f"@{snap['connected_user'] or 'never'} in {duration:.0f}s"
            if ok
            else f"no live connection in {args.connect_timeout:.0f}s",
        )
    )
    raw_total = sum(snap["raw"].values())
    ok = raw_total > 0
    raw_detail = ", ".join(f"{k}={v}" for k, v in snap["raw"].items())
    checks.append(
        ("RAW_EVENTS", ok, f"{raw_total} raw event lines ({raw_detail or 'none'})")
    )
    ok = snap["initial_likes"] is not None
    checks.append(
        (
            "LIKE_INIT",
            ok,
            f"initial like count set to {snap['initial_likes']}"
            if ok
            else "no [LIKE] Initial count set line",
        )
    )
    ok = len(snap["milestones"]) > 0
    mil = ", ".join(f"{r}+{d}" for r, d in snap["milestones"])
    checks.append(
        (
            "LIKE_MILESTONE",
            ok,
            f"{len(snap['milestones'])} fired ({mil or 'none - like count stayed under a threshold'})",
        )
    )
    ok = probe_result.get("health") == 200
    if probe_result:
        detail = (
            f"/health={probe_result.get('health')} "
            f"/test_comment={probe_result.get('test_comment')} "
            f"/custom_trigger={probe_result.get('custom_trigger')}"
        )
    else:
        detail = "probes skipped (--no-probe)"
    checks.append(("WEBHOOK", ok, detail))
    ok = not snap["fatal"]
    checks.append(
        (
            "STABILITY",
            ok,
            "no fatal flags" if ok else "fatal:" + ",".join(snap["fatal"]),
        )
    )
    if snap["handler_errors"]:
        checks.append(
            (
                "HANDLER_ERRS",
                False,
                f"{snap['handler_errors']} handler exceptions (loop kept alive, investigate)",
            )
        )
    if snap["tiktoklive_lines"]:
        checks.append(
            (
                "TIKTOKLIVE_DEBUG",
                None,
                f"{snap['tiktoklive_lines']} TikTokLive DEBUG line(s) captured",
            )
        )
    if snap["eventbus_fail"]:
        checks.append(
            (
                "EVENTBUS",
                None,
                f"{snap['eventbus_fail']} EventBus publish failures (expected: no API server in this run)",
            )
        )
    if snap["actions"]:
        checks.append(
            (
                "ACTIONS",
                True,
                f"{len(snap['actions'])} trigger(s) reached the queue: {', '.join(snap['actions'][:8])}",
            )
        )

    passed = 0
    for name, ok_flag, detail in checks:
        if ok_flag is True:
            mark, passed = "[PASS]", passed + 1
        elif ok_flag is False:
            mark = "[FAIL]"
        else:
            mark = "[INFO]"
        print(f"{mark} {name:<16} {detail}")

    n_fail = sum(1 for _, ok_, _ in checks if ok_ is False)
    n_info = sum(1 for _, ok_, _ in checks if ok_ is None)
    print(f"\nran for {duration:.0f}s; pass/fail/info = {passed}/{n_fail}/{n_info}")
    print(f"sandbox (kept={args.keep_sandbox}): {sandbox}")
    if snap["fatal"]:
        print("fatal flags: " + ", ".join(snap["fatal"]))

    print("\n----- last bridge log lines -----")
    for line in mon.tail(80):
        print(line)
    print("---------------------------------\n")

    if not args.keep_sandbox:
        try:
            shutil.rmtree(sandbox, ignore_errors=True)
        except OSError:
            pass

    if child_exit and proc.returncode:
        return 2
    if not (connected and not snap["config_errors"]) or snap["fatal"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
