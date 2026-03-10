"""Tests for mold_manager.py — mold risk detection and prevention manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.roommind.managers.mold_manager import MoldManager


@pytest.fixture
def mm(hass):
    return MoldManager(hass)


def _settings_prevention_notify(**overrides):
    """Return settings with mold prevention + notification enabled."""
    s = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": True,
        "mold_prevention_notify_enabled": True,
        "mold_notifications_enabled": True,
        "mold_prevention_intensity": "medium",
        "mold_prevention_notify_targets": ["notify.mobile"],
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 0,
    }
    s.update(overrides)
    return s


# --- prevention activation notification (lines 143-156) ---


@pytest.mark.asyncio
async def test_prevention_activation_sends_notification(mm):
    """When prevention activates for first time, notification is sent."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert result.prevention_active is True
    assert result.prevention_delta == 2.0
    assert mock_notify.call_count >= 1
    # Check that prevention notification was sent (not just detection)
    prevention_call = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_call) == 1


@pytest.mark.asyncio
async def test_prevention_notification_not_sent_without_helper_fns(mm):
    """Prevention notification skipped if celsius_delta_to_ha_fn is None."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=None,
            ha_temp_unit_str_fn=None,
        )

    assert result.prevention_active is True
    # Only detection notification, no prevention notification
    prevention_calls = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_calls) == 0


@pytest.mark.asyncio
async def test_prevention_notification_not_sent_on_second_evaluation(mm):
    """Prevention notification only sent on first activation, not repeated."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )
        mock_notify.reset_mock()

        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    prevention_calls = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_calls) == 0


# --- remove_room (lines 182-185) ---


@pytest.mark.asyncio
async def test_remove_room_clears_state(mm):
    """remove_room cleans up all internal state for a room."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert "living" in mm._risk_since
    assert mm._prevention_active.get("living") is True

    mm.remove_room("living")

    assert "living" not in mm._risk_since
    assert "living" not in mm._prevention_active


def test_remove_room_no_op_for_unknown(mm):
    """remove_room on unknown area_id does not raise."""
    mm.remove_room("nonexistent")
