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
    """When heating stops and no forecast, demand turns off after short holdoff."""
    room = {**SAMPLE_ROOM, "schedules": []}
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)

    # First cycle: heating active (temp below comfort)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    data = await coordinator._async_update_data()
    assert data["heating_demand"] is True
    assert coordinator._heating_demand_was_active is True

    # Force mode to idle by setting previous modes and clearing min-run
    coordinator._previous_modes["living_room_abc12345"] = MODE_IDLE
    coordinator._mode_on_since.pop("living_room_abc12345", None)

    # Second cycle: room idle (temp well above comfort), no forecast heating
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="25.0"))
    data = await coordinator._async_update_data()
    assert data["rooms"]["living_room_abc12345"]["mode"] == MODE_IDLE
    # Demand should still be True (short holdoff just started)
    assert data["heating_demand"] is True
    assert coordinator._heating_demand_off_since is not None

    # Simulate time passing beyond the holdoff delay
    coordinator._heating_demand_off_since = time.monotonic() - HEATING_DEMAND_OFF_DELAY - 1
    data = await coordinator._async_update_data()
    # Now demand should be False (holdoff expired)
    assert data["heating_demand"] is False
    assert coordinator._heating_demand_was_active is False


@pytest.mark.asyncio
async def test_heating_demand_from_forecast_alone_is_false(hass, mock_config_entry):
    """Forecast alone (no prior heating) does NOT start demand."""
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
    # Forecast alone must NOT start demand
    assert data["heating_demand"] is False
    assert "living_room_abc12345" in data["rooms_heating_forecast"]


@pytest.mark.asyncio
async def test_heating_demand_kept_by_forecast_after_heating(hass, mock_config_entry):
    """Demand stays True when heating was active, stops, but forecast has heating."""
    room = {**SAMPLE_ROOM, "schedules": []}
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)

    # First cycle: heating active
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    data = await coordinator._async_update_data()
    assert data["heating_demand"] is True
    assert coordinator._heating_demand_was_active is True

    # Force mode to idle
    coordinator._previous_modes["living_room_abc12345"] = MODE_IDLE
    coordinator._mode_on_since.pop("living_room_abc12345", None)

    # Second cycle: room idle but forecast has heating → demand stays on
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
    assert coordinator._heating_demand_off_since is None  # no holdoff needed


@pytest.mark.asyncio
async def test_heating_demand_stops_when_forecast_clear(hass, mock_config_entry):
    """Demand turns off (after holdoff) when heating stops and forecast has no heating."""
    room = {**SAMPLE_ROOM, "schedules": []}
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()

    coordinator = _create_coordinator(hass, mock_config_entry)

    # First cycle: heating active
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    data = await coordinator._async_update_data()
    assert data["heating_demand"] is True

    # Force mode to idle
    coordinator._previous_modes["living_room_abc12345"] = MODE_IDLE
    coordinator._mode_on_since.pop("living_room_abc12345", None)

    # Second cycle: idle, no forecast heating → holdoff starts
    async def fake_process_room(room_cfg, settings, outdoor_forecast):
        return {
            "area_id": "living_room_abc12345",
            "mode": MODE_IDLE,
            "forecast": [{"ts": time.time() + 300, "temp": 22.0, "action": MODE_IDLE}],
        }

    with patch.object(coordinator, "_async_process_room", side_effect=fake_process_room):
        data = await coordinator._async_update_data()
    assert data["heating_demand"] is True  # holdoff active

    # Expire the holdoff
    coordinator._heating_demand_off_since = time.monotonic() - HEATING_DEMAND_OFF_DELAY - 1
    with patch.object(coordinator, "_async_process_room", side_effect=fake_process_room):
        data = await coordinator._async_update_data()
    assert data["heating_demand"] is False
    assert coordinator._heating_demand_was_active is False
