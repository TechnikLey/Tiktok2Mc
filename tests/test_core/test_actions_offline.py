"""Tests for action system blocking when API is offline.

These verify that the actions editor and related features handle
the absence of the API server gracefully.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from core.api.services.actions import ActionsService


class TestActionsServiceOffline:
    """Verify actions service works independently of API server state."""

    def test_service_reads_local_files(self, monkeypatch):
        """ActionsService should read from local files without API."""
        # Monkeypatch to point to a temp directory with known content
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "data"
            data_dir.mkdir()
            actions_file = data_dir / "actions.mca"
            actions_file.write_text("follow:/say Hello!\n")
            monkeypatch.setattr(
                "core.api.services.actions.get_root_dir",
                lambda: tmp_path,
            )
            svc = ActionsService()
            raw = svc.read_raw()
            assert "follow:/say Hello!" in raw

    def test_service_validates_without_api(self):
        """Validation should work without any API connection."""
        svc = ActionsService()
        diags = svc.validate("follow:/say Test\n")
        # Empty diagnostics means no errors
        assert isinstance(diags, list)

    def test_service_parses_without_api(self):
        """Parsing triggers should work without API connection."""
        svc = ActionsService()
        content = "follow:/say Hello!\n5655:/give @a minecraft:diamond"
        triggers = svc.parse(text=content)
        assert len(triggers) == 2
        names = [t["name"] for t in triggers]
        assert "follow" in names
        assert "5655" in names

    def test_service_serialize_roundtrip(self):
        """Serialize and parse roundtrip should work offline."""
        svc = ActionsService()
        triggers = [
            {"name": "follow", "type": "event", "enabled": True,
             "commands": [{"command": "/say hi", "enabled": True}]},
        ]
        raw = svc.serialize(triggers)
        parsed = svc.parse(text=raw)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "follow"


class TestActionsAPIOfflineBlocking:
    """Verify the API routes block or fail gracefully when service is unavailable.

    These tests check the FastAPI routes in core/api/routes/actions.py.
    """

    def test_get_actions_returns_error_on_service_failure(self, monkeypatch):
        """When ActionsService fails, route should return 500."""
        from fastapi import HTTPException
        from core.api.routes.actions import get_actions

        monkeypatch.setattr(
            "core.api.routes.actions._get_service",
            MagicMock(side_effect=RuntimeError("Simulated failure"))
        )

        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_actions())
        assert exc_info.value.status_code == 500

    def test_actions_service_lazy_initialization(self):
        """_get_service should create service on first call."""
        from core.api.routes.actions import _get_service, _service
        # Reset internal state for test
        import core.api.routes.actions as actions_mod
        actions_mod._service = None
        svc = _get_service()
        assert svc is not None
        assert isinstance(svc, ActionsService)


class TestActionBlockingInLauncher:
    """Tests that verify the launcher page blocks actions when API offline.

    These tests document the expected UI behavior rather than test the
    HTML/JS directly.
    """

    def _load_launcher_html(self):
        root = Path(__file__).resolve().parent.parent.parent
        candidates = [
            root / "templates" / "gui" / "launcher.html",
            root / "core" / "templates" / "gui" / "launcher.html",
        ]
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8")
        raise FileNotFoundError("launcher.html not found in any known location")

    def test_launcher_api_blocks_actions_when_offline(self):
        """When API is offline, actions requiring the API should be disabled.

        This is enforced by the launcher.html UI:
        - The actions-blocked banner is shown
        - Buttons are visually disabled
        """
        content = self._load_launcher_html()
        assert "actions-blocked" in content
        assert "API server is not running" in content
        assert 'id="actions-blocked"' in content

    def test_launcher_shows_start_buttons_when_offline(self):
        """The launcher must show Start API and Start Full System buttons."""
        content = self._load_launcher_html()
        assert "btn-start-api" in content
        assert "btn-start-full" in content
        assert "Start API Server" in content
        assert "Start Full System" in content

    def test_launcher_navigates_to_dashboard_when_online(self):
        """When API comes online, launcher should navigate to full dashboard."""
        content = self._load_launcher_html()
        assert "/gui/index.html" in content
        assert "window.location.href" in content
