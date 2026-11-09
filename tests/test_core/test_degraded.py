"""Tests for structured degraded reporting (``core.degraded``) and its use
in the config/data fallback hotspots (event command mapper, gift catalog).
"""

import asyncio

import pytest

import core.degraded
import core.event_command_mapper
import core.gift_sync
from core.api.eventbus import event_bus
from core.error_codes import CONFIG_0009
from core.health_monitor import HealthState, get_health_monitor


class _StubCrashManager:
    """Records ``report_error`` calls instead of touching global state."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def report_error(self, error_code, detail="", context_info=None):
        """Record a report call.

        Args:
            error_code: Structured code passed through.
            detail: Free-text detail.
            context_info: Context mapping.

        Returns:
            ``None`` (the real CrashManager returns an ErrorInstance).
        """
        self.calls.append((error_code.code, detail, context_info))
        return None


@pytest.fixture()
def stub_crash_manager(monkeypatch: pytest.MonkeyPatch) -> _StubCrashManager:
    """Patch ``core.degraded.get_crash_manager`` to a recording stub."""
    stub = _StubCrashManager()
    monkeypatch.setattr(core.degraded, "get_crash_manager", lambda: stub)
    return stub


# ---------------------------------------------------------------------------
# core.degraded.report_degraded
# ---------------------------------------------------------------------------


def test_report_degraded_records_code_and_degrades_health(
    stub_crash_manager: _StubCrashManager,
) -> None:
    """The helper reports the code and moves the component to DEGRADED."""
    core.degraded.report_degraded(
        CONFIG_0009,
        "test_component",
        "some fallback",
        path="x.json",
        publish=False,
    )
    assert stub_crash_manager.calls, "expected a crash manager report"
    code, detail, context = stub_crash_manager.calls[0]
    assert code == "CONFIG-0009"
    assert "some fallback" in detail
    assert context["component"] == "test_component"
    assert context["path"] == "x.json"
    monitor = get_health_monitor()
    monitor.register("test_component")
    assert monitor.get_state("test_component") is not None
    assert monitor._states.get("test_component") == HealthState.DEGRADED


def test_report_degraded_publishes_event_bus(
    stub_crash_manager: _StubCrashManager,
) -> None:
    """Inside a running loop the helper publishes a config.degraded event."""
    received: list[dict] = []
    q = event_bus.subscribe("config.degraded")

    async def _run() -> None:
        core.degraded.report_degraded(
            CONFIG_0009, "loop_component", "fallback in use", publish=True
        )
        received.append(await asyncio.wait_for(q.get(), timeout=2))

    try:
        asyncio.run(_run())
    finally:
        event_bus.unsubscribe(q)

    msg = received[0]
    assert msg["type"] == "config.degraded"
    assert msg["data"]["component"] == "loop_component"
    assert msg["data"]["code"] == "CONFIG-0009"


def test_report_degraded_without_loop_skips_publish(
    stub_crash_manager: _StubCrashManager,
) -> None:
    """Outside a loop no publish task is created and nothing raises."""
    core.degraded.report_degraded(
        CONFIG_0009, "sync_component", "fallback", publish=True
    )
    assert stub_crash_manager.calls, "report should still happen"


# ---------------------------------------------------------------------------
# Hotspot: event command mapper
# ---------------------------------------------------------------------------


def test_ecm_broken_yaml_reports_degraded(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A YAML syntax error in event_commands.yaml reports CONFIG-0002 degraded."""
    broken = tmp_path / "event_commands.yaml"
    broken.write_text("event_commands:\n  - [unclosed\n", encoding="utf-8")
    mapper = core.event_command_mapper.EventCommandMapper()

    monkeypatch.setattr(mapper, "_config_path", lambda: broken)
    recorded: list[tuple] = []
    monkeypatch.setattr(
        core.event_command_mapper,
        "report_degraded",
        lambda code, comp, detail, **k: recorded.append((code.code, comp)),
    )

    mappings = mapper._load_mappings()
    assert mappings == {}
    assert recorded and recorded[0][0] == "CONFIG-0002"
    assert recorded[0][1] == "event_command_mapper"


# ---------------------------------------------------------------------------
# Hotspot: gift catalog
# ---------------------------------------------------------------------------


def test_read_catalog_broken_json_reports_degraded(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A JSON decoder error in gifts.json reports CONFIG-0009 degraded."""
    broken = tmp_path / "gifts.json"
    broken.write_text("{not json", encoding="utf-8")
    recorded: list[tuple] = []
    monkeypatch.setattr(
        core.gift_sync,
        "report_degraded",
        lambda code, comp, detail, **k: recorded.append((code.code, comp)),
    )
    assert core.gift_sync.read_catalog(broken) == []
    assert recorded and recorded[0][0] == "CONFIG-0009"
    assert recorded[0][1] == "gift_catalog"


def test_read_catalog_missing_file_stays_silent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing gifts.json is a bootstrap state — no degraded report."""
    monkeypatch.setattr(
        core.gift_sync,
        "report_degraded",
        lambda *a, **k: pytest.fail("missing file must not report degraded"),
    )
    assert core.gift_sync.read_catalog(tmp_path / "does-not-exist.json") == []
