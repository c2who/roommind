"""Tests for heating demand aggregation in the coordinator."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import HEATING_DEMAND_OFF_DELAY, MODE_HEATING, MODE_IDLE

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get


@pytest.mark.asyncio
async def test_heating_demand_true_when_room_heating(hass, mock_config_entry):
    """Heating demand is True when at least one room is in heating mode."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()

    # With default fixture (temp=18, comfort=21), room should be heating
    assert data["rooms"]["living_room_abc12345"]["mode"] == MODE_HEATING
    assert data["heating_demand"] is True
    assert "living_room_abc12345" in data["rooms_heating_now"]


@pytest.mark.asyncio
async def test_heating_demand_false_when_all_idle(hass, mock_config_entry):
    """Heating demand is False when no rooms heat and no forecast, and never was active."""
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    # temp above comfort → idle
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="22.0"))
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()

    assert data["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
    assert data["heating_demand"] is False
    assert data["rooms_heating_now"] == []


@pytest.mark.asyncio
async def test_heating_demand_holdoff_after_heating_stops(hass, mock_config_entry):
    """Demand stays True for HEATING_DEMAND_OFF_DELAY after last room stops heating."""
    room = {**SAMPLE_ROOM, "schedules": []}  # no schedule → uses comfort_temp directly
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)

    # First cycle: heating active (temp below comfort)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    data = await coordinator._async_update_data()
    assert data["heating_demand"] is True
    assert coordinator._heating_demand_off_since is None  # demand active

    # Force mode to idle by setting previous modes and clearing min-run
    coordinator._previous_modes["living_room_abc12345"] = MODE_IDLE
    coordinator._mode_on_since.pop("living_room_abc12345", None)

    # Second cycle: room idle (temp well above comfort)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="25.0"))
    data = await coordinator._async_update_data()
    assert data["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
    # Demand should still be True (hold-on timer just started)
    assert data["heating_demand"] is True
    assert coordinator._heating_demand_off_since is not None

    # Simulate time passing beyond the delay
    coordinator._heating_demand_off_since = time.monotonic() - HEATING_DEMAND_OFF_DELAY - 1
    data = await coordinator._async_update_data()
    # Now demand should be False (timer expired)
    assert data["heating_demand"] is False


@pytest.mark.asyncio
async def test_heating_demand_from_forecast(hass, mock_config_entry):
    """Demand is True when no room currently heats but forecast contains heating."""
    room = {**SAMPLE_ROOM, "schedules": []}
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    # Room is idle (temp well above comfort)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="25.0"))
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)

    # Patch _async_process_room to return idle with a heating forecast
    async def fake_process_room(room_cfg, settings, outdoor_forecast):
        return {
            "area_id": "living_room_abc12345",
            "mode": MODE_IDLE,
            "forecast": [{"ts": time.time() + 300, "temp": 20.5, "action": MODE_HEATING}],
        }

    with patch.object(coordinator, "_async_process_room", side_effect=fake_process_room):
        data = await coordinator._async_update_data()

    assert data["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
    assert data["heating_demand"] is True
    assert "living_room_abc12345" in data["rooms_heating_forecast"]
