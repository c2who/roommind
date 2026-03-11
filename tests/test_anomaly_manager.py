"""Tests for AnomalyManager."""

from unittest.mock import patch

import pytest

from custom_components.roommind.managers.anomaly_manager import AnomalyManager


@pytest.fixture
def manager() -> AnomalyManager:
    return AnomalyManager()


# --- Default kwargs for convenience ---
_BASE = dict(
    confidence=0.8,
    mpc_active=True,
    window_open=False,
    suppress_heating_enabled=True,
    suppress_cooling_enabled=True,
    suppression_minutes=10,
)


class TestNormalState:
    """Tests for Normal → Suppressed transitions."""

    def test_no_anomaly_returns_none(self, manager: AnomalyManager) -> None:
        result = manager.update("room1", innovation=-0.1, prediction_std=0.2, **_BASE)
        assert result is None

    def test_single_spike_does_not_trigger(self, manager: AnomalyManager) -> None:
        """Single large innovation should NOT trigger (needs 2 consecutive)."""
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        assert result is None
        assert not manager.is_suppressed("room1")

    def test_two_consecutive_triggers_heating_suppression(self, manager: AnomalyManager) -> None:
        """Two consecutive negative innovations should suppress heating."""
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        result = manager.update("room1", innovation=-0.8, prediction_std=0.2, **_BASE)
        assert result == "heating"
        assert manager.is_suppressed("room1")

    def test_two_consecutive_positive_triggers_cooling_suppression(self, manager: AnomalyManager) -> None:
        """Two consecutive positive innovations should suppress cooling."""
        manager.update("room1", innovation=1.0, prediction_std=0.2, **_BASE)
        result = manager.update("room1", innovation=0.8, prediction_std=0.2, **_BASE)
        assert result == "cooling"
        assert manager.is_suppressed("room1")

    def test_non_consecutive_resets(self, manager: AnomalyManager) -> None:
        """If an anomaly is followed by a normal reading, counter resets."""
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.update("room1", innovation=-0.05, prediction_std=0.2, **_BASE)  # normal
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        assert result is None  # only 1 consecutive, not 2

    def test_innovation_floor_respected(self, manager: AnomalyManager) -> None:
        """Threshold is max(0.3, 2.5 * prediction_std), so small std still uses 0.3."""
        # prediction_std=0.05 → 2.5*0.05=0.125 → threshold=0.3
        manager.update("room1", innovation=-0.25, prediction_std=0.05, **_BASE)
        result = manager.update("room1", innovation=-0.25, prediction_std=0.05, **_BASE)
        assert result is None  # 0.25 < 0.3 floor


class TestSafetyGuards:
    """Tests for safety guards that disable anomaly detection."""

    def test_low_confidence_disables(self, manager: AnomalyManager) -> None:
        kwargs = {**_BASE, "confidence": 0.2}
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        assert result is None

    def test_mpc_inactive_disables(self, manager: AnomalyManager) -> None:
        kwargs = {**_BASE, "mpc_active": False}
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        assert result is None

    def test_window_open_disables(self, manager: AnomalyManager) -> None:
        kwargs = {**_BASE, "window_open": True}
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        assert result is None

    def test_heating_suppression_disabled_ignores_negative(self, manager: AnomalyManager) -> None:
        kwargs = {**_BASE, "suppress_heating_enabled": False}
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **kwargs)
        assert result is None

    def test_cooling_suppression_disabled_ignores_positive(self, manager: AnomalyManager) -> None:
        kwargs = {**_BASE, "suppress_cooling_enabled": False}
        manager.update("room1", innovation=1.0, prediction_std=0.2, **kwargs)
        result = manager.update("room1", innovation=1.0, prediction_std=0.2, **kwargs)
        assert result is None


class TestSuppressionExpiry:
    """Tests for Suppressed → Recovering → Normal transitions."""

    def test_suppression_holds_during_timer(self, manager: AnomalyManager) -> None:
        """While suppressed, returns the suppressed action."""
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        # Should still be suppressed
        result = manager.update("room1", innovation=0.0, prediction_std=0.2, **_BASE)
        assert result == "heating"

    @patch("custom_components.roommind.managers.anomaly_manager.time")
    def test_suppression_expires_after_duration(self, mock_time, manager: AnomalyManager) -> None:
        """After suppression_minutes, should transition to recovering."""
        mock_time.time.return_value = 1000.0
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)

        # Jump forward 11 minutes
        mock_time.time.return_value = 1000.0 + 11 * 60
        result = manager.update("room1", innovation=0.0, prediction_std=0.2, **_BASE)
        assert result is None  # expired → recovering
        assert not manager.is_suppressed("room1")

    @patch("custom_components.roommind.managers.anomaly_manager.time")
    def test_recovering_transitions_to_normal(self, mock_time, manager: AnomalyManager) -> None:
        """After recovering state, next cycle returns to normal."""
        mock_time.time.return_value = 1000.0
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)

        # Expire
        mock_time.time.return_value = 1000.0 + 11 * 60
        manager.update("room1", innovation=0.0, prediction_std=0.2, **_BASE)  # → recovering

        # Next cycle: → normal
        result = manager.update("room1", innovation=0.0, prediction_std=0.2, **_BASE)
        assert result is None


class TestMultipleRooms:
    """Tests for independent per-room state."""

    def test_rooms_are_independent(self, manager: AnomalyManager) -> None:
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        assert manager.is_suppressed("room1")
        assert not manager.is_suppressed("room2")

    def test_remove_room(self, manager: AnomalyManager) -> None:
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        manager.remove_room("room1")
        assert not manager.is_suppressed("room1")


class TestDirectionAwareness:
    """Tests that the correct action is suppressed based on innovation direction."""

    def test_negative_innovation_only_suppresses_heating(self, manager: AnomalyManager) -> None:
        """Cooled faster → suppress heating, not cooling."""
        manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        result = manager.update("room1", innovation=-1.0, prediction_std=0.2, **_BASE)
        assert result == "heating"

    def test_positive_innovation_only_suppresses_cooling(self, manager: AnomalyManager) -> None:
        """Warmed faster → suppress cooling, not heating."""
        manager.update("room1", innovation=1.0, prediction_std=0.2, **_BASE)
        result = manager.update("room1", innovation=1.0, prediction_std=0.2, **_BASE)
        assert result == "cooling"
