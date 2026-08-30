"""Unit tests for the update-progress splash decision logic.

The splash window (``src/python/update_progress.py``) keeps Qt out of the
module top level, so :func:`~src.python.update_progress.classify` is directly
unit-testable without a GUI backend.
"""

from src.python.update_progress import classify


class TestClassify:
    def test_no_status_preparing(self):
        assert classify(None, new_gui=False, port=False, done_elapsed=0.0) == (
            "preparing",
            None,
            False,
            False,
        )

    def test_no_status_closes_when_control_plane_up(self):
        assert classify(None, new_gui=False, port=True, done_elapsed=0.0) == (
            "restarting",
            None,
            True,
            False,
        )

    def test_checking_phase(self):
        status = {"phase": "checking"}
        assert classify(status, new_gui=False, port=False, done_elapsed=0.0) == (
            "checking",
            None,
            False,
            False,
        )

    def test_downloading_phase_passes_progress(self):
        status = {"phase": "downloading", "progress": 42.5}
        assert classify(status, new_gui=False, port=False, done_elapsed=0.0) == (
            "downloading",
            42.5,
            False,
            False,
        )

    def test_downloading_without_progress(self):
        status = {"phase": "downloading"}
        assert classify(status, new_gui=False, port=False, done_elapsed=0.0) == (
            "downloading",
            None,
            False,
            False,
        )

    def test_installing_phase(self):
        status = {"phase": "installing"}
        assert classify(status, new_gui=False, port=False, done_elapsed=0.0) == (
            "installing",
            None,
            False,
            False,
        )

    def test_done_keeps_waiting_until_app_returns(self):
        status = {"phase": "done"}
        assert classify(status, new_gui=False, port=False, done_elapsed=10.0) == (
            "restarting",
            None,
            False,
            False,
        )

    def test_done_closes_on_new_gui(self):
        status = {"phase": "done"}
        assert classify(status, new_gui=True, port=False, done_elapsed=3.0) == (
            "restarting",
            None,
            True,
            False,
        )

    def test_done_closes_on_port_answering(self):
        status = {"phase": "done"}
        assert classify(status, new_gui=False, port=True, done_elapsed=5.0) == (
            "restarting",
            None,
            True,
            False,
        )

    def test_done_stuck_becomes_failure(self):
        status = {"phase": "done"}
        assert classify(status, new_gui=False, port=False, done_elapsed=181.0) == (
            "error",
            None,
            False,
            True,
        )

    def test_error_phase_shows_failure(self):
        status = {"phase": "error", "message": "boom"}
        assert classify(status, new_gui=False, port=False, done_elapsed=0.0) == (
            "error",
            None,
            False,
            True,
        )

    def test_unknown_phase_preparing(self):
        assert classify(
            {"phase": "totally-new-phase"}, new_gui=False, port=False, done_elapsed=0.0
        ) == ("preparing", None, False, False)

    def test_unknown_phase_closes_when_control_plane_up(self):
        assert classify(
            {"phase": "totally-new-phase"}, new_gui=False, port=True, done_elapsed=0.0
        ) == ("restarting", None, True, False)
