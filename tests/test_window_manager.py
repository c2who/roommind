"""Tests for WindowManager."""

from __future__ import annotations

import time
from unittest.mock import patch

from custom_components.roommind.managers.window_manager import WindowManager


def test_is_paused_default_false():
    """is_paused returns False for an unknown room."""
    mgr = WindowManager()
    assert mgr.is_paused("living_room") is False


def test_is_paused_after_window_opens():
    """is_paused returns True after window has been open past the delay."""
    mgr = WindowManager()
    # open_delay=0 → immediate pause
    mgr.update("living_room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.is_paused("living_room") is True


# --- in_open_delay tests ---


def test_in_open_delay_unknown_room():
    """in_open_delay returns False for an unknown room."""
    mgr = WindowManager()
    assert mgr.in_open_delay("unknown") is False


def test_in_open_delay_during_delay():
    """in_open_delay returns True when window is open but delay has not elapsed."""
    mgr = WindowManager()
    now = time.time()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = now
        mgr.update("room", raw_open=True, open_delay=60, close_delay=0)
    assert mgr.in_open_delay("room") is True


def test_in_open_delay_after_delay_elapses():
    """in_open_delay returns False once delay elapses (room is now paused)."""
    mgr = WindowManager()
    now = time.time()
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = now
        mgr.update("room", raw_open=True, open_delay=60, close_delay=0)
        assert mgr.in_open_delay("room") is True
        mock_time.time.return_value = now + 61
        mgr.update("room", raw_open=True, open_delay=60, close_delay=0)
    assert mgr.in_open_delay("room") is False
    assert mgr.is_paused("room") is True


def test_in_open_delay_window_closed():
    """in_open_delay returns False when window is closed."""
    mgr = WindowManager()
    mgr.update("room", raw_open=False, open_delay=60, close_delay=0)
    assert mgr.in_open_delay("room") is False


def test_in_open_delay_zero_delay():
    """in_open_delay returns False with delay=0 (immediate pause)."""
    mgr = WindowManager()
    mgr.update("room", raw_open=True, open_delay=0, close_delay=0)
    assert mgr.in_open_delay("room") is False
    assert mgr.is_paused("room") is True
