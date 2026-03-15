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


# --- in_close_delay tests ---


def test_in_close_delay_unknown_room():
    """in_close_delay returns False for an unknown room."""
    mgr = WindowManager()
    assert mgr.in_close_delay("unknown") is False


def test_close_delay_after_non_brief_open_delay_opening():
    """Window open for >= 10% of open_delay triggers close_delay on close."""
    mgr = WindowManager()
    now = 1000.0
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Open window (open_delay=900, so threshold=90s)
        mock_time.time.return_value = now
        mgr.update("room", raw_open=True, open_delay=900, close_delay=900)
        assert mgr.in_open_delay("room") is True
        assert mgr.is_paused("room") is False

        # Close window after 200s (> 90s threshold)
        mock_time.time.return_value = now + 200
        mgr.update("room", raw_open=False, open_delay=900, close_delay=900)
        assert mgr.is_paused("room") is False
        assert mgr.in_close_delay("room") is True

        # Still in close_delay after 500s
        mock_time.time.return_value = now + 700
        mgr.update("room", raw_open=False, open_delay=900, close_delay=900)
        assert mgr.in_close_delay("room") is True

        # Close delay elapsed (200 + 900 = 1100s from start)
        mock_time.time.return_value = now + 1100
        mgr.update("room", raw_open=False, open_delay=900, close_delay=900)
        assert mgr.in_close_delay("room") is False
        assert mgr.is_paused("room") is False


def test_no_close_delay_after_brief_opening():
    """Window open for < 10% of open_delay does NOT trigger close_delay."""
    mgr = WindowManager()
    now = 1000.0
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        # Open window (open_delay=900, threshold=90s)
        mock_time.time.return_value = now
        mgr.update("room", raw_open=True, open_delay=900, close_delay=900)

        # Close after 30s (< 90s threshold) — brief opening
        mock_time.time.return_value = now + 30
        mgr.update("room", raw_open=False, open_delay=900, close_delay=900)
        assert mgr.in_close_delay("room") is False
        assert mgr.is_paused("room") is False


def test_close_delay_after_full_pause():
    """Existing behavior: close_delay works after open_delay fully elapsed."""
    mgr = WindowManager()
    now = 1000.0
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = now
        mgr.update("room", raw_open=True, open_delay=60, close_delay=120)

        # open_delay elapses
        mock_time.time.return_value = now + 61
        mgr.update("room", raw_open=True, open_delay=60, close_delay=120)
        assert mgr.is_paused("room") is True

        # Window closes
        mock_time.time.return_value = now + 100
        mgr.update("room", raw_open=False, open_delay=60, close_delay=120)
        assert mgr.is_paused("room") is True  # in close_delay

        # Close delay elapses
        mock_time.time.return_value = now + 220
        mgr.update("room", raw_open=False, open_delay=60, close_delay=120)
        assert mgr.is_paused("room") is False


def test_no_close_delay_when_close_delay_is_zero():
    """No close_delay triggered even for non-brief opening when close_delay=0."""
    mgr = WindowManager()
    now = 1000.0
    with patch("custom_components.roommind.managers.window_manager.time") as mock_time:
        mock_time.time.return_value = now
        mgr.update("room", raw_open=True, open_delay=900, close_delay=0)

        # Close after 200s (non-brief), but close_delay=0
        mock_time.time.return_value = now + 200
        mgr.update("room", raw_open=False, open_delay=900, close_delay=0)
        assert mgr.in_close_delay("room") is False
        assert mgr.is_paused("room") is False
