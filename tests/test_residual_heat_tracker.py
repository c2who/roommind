"""Tests for the ResidualHeatTracker manager."""

from __future__ import annotations

from custom_components.roommind.const import MODE_IDLE
from custom_components.roommind.managers.residual_heat_tracker import ResidualHeatTracker

# ---------------------------------------------------------------------------
# update – cleanup branch (lines 40-43)
# ---------------------------------------------------------------------------


def test_update_clears_state_when_residual_zero_and_idle():
    """When mode is idle, previous was idle, and q_residual==0, state is cleaned up."""
    tracker = ResidualHeatTracker()
    # Seed some state as if heating stopped earlier
    tracker._off_since["room1"] = 1000.0
    tracker._off_power["room1"] = 0.8
    tracker._on_since["room1"] = 900.0

    tracker.update("room1", MODE_IDLE, 0.0, MODE_IDLE, q_residual=0.0)

    assert "room1" not in tracker._off_since
    assert "room1" not in tracker._off_power
    assert "room1" not in tracker._on_since


def test_update_keeps_state_when_residual_nonzero():
    """When q_residual > 0, state should NOT be cleaned up."""
    tracker = ResidualHeatTracker()
    tracker._off_since["room1"] = 1000.0
    tracker._off_power["room1"] = 0.8
    tracker._on_since["room1"] = 900.0

    tracker.update("room1", MODE_IDLE, 0.0, MODE_IDLE, q_residual=0.5)

    assert "room1" in tracker._off_since
    assert "room1" in tracker._off_power
    assert "room1" in tracker._on_since


def test_update_cleanup_no_state_is_noop():
    """Cleanup branch with no existing state should not raise."""
    tracker = ResidualHeatTracker()
    tracker.update("room1", MODE_IDLE, 0.0, MODE_IDLE, q_residual=0.0)
    assert "room1" not in tracker._off_since


# ---------------------------------------------------------------------------
# clear_room (line 53)
# ---------------------------------------------------------------------------


def test_clear_room_delegates_to_remove():
    """clear_room should remove all state for the given room."""
    tracker = ResidualHeatTracker()
    tracker._off_since["room1"] = 1000.0
    tracker._off_power["room1"] = 0.8
    tracker._on_since["room1"] = 900.0

    tracker.clear_room("room1")

    assert "room1" not in tracker._off_since
    assert "room1" not in tracker._off_power
    assert "room1" not in tracker._on_since


# ---------------------------------------------------------------------------
# clear_all (lines 57-59)
# ---------------------------------------------------------------------------


def test_clear_all_removes_all_rooms():
    """clear_all should remove state for every room."""
    tracker = ResidualHeatTracker()
    for room in ("room1", "room2", "room3"):
        tracker._off_since[room] = 1000.0
        tracker._off_power[room] = 0.8
        tracker._on_since[room] = 900.0

    tracker.clear_all()

    assert len(tracker._off_since) == 0
    assert len(tracker._off_power) == 0
    assert len(tracker._on_since) == 0
