"""Heating demand follows active rooms and releases after a short hold."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MODE_IDLE

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get


@pytest.mark.asyncio
async def test_heating_demand_tracks_a_heating_room(hass, mock_config_entry):
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)

    data = await coordinator._async_update_data()

    assert data["heating_demand"] is True
    assert data["rooms_heating_now"] == ["living_room_abc12345"]


@pytest.mark.asyncio
async def test_heating_demand_does_not_start_from_forecast_alone(hass, mock_config_entry):
    store = _make_store_mock({"living_room_abc12345": SAMPLE_ROOM})
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="25.0"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)

    async def idle_with_future(*args):
        coordinator._prediction_forecasts["living_room_abc12345"] = [
            {"action": MODE_IDLE},
            {"action": "heating"},
        ]
        return {"commanded_mode": MODE_IDLE, "target_temp": 21.0, "window_open": False}

    with patch.object(coordinator, "_async_process_room", side_effect=idle_with_future):
        data = await coordinator._async_update_data()

    assert data["heating_demand"] is False
    assert data["rooms_heating_forecast"] == ["living_room_abc12345"]


@pytest.mark.asyncio
async def test_heating_demand_releases_after_idle_delay(hass, mock_config_entry):
    room = {**SAMPLE_ROOM, "schedules": []}
    store = _make_store_mock({"living_room_abc12345": room})
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)

    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="18.0"))
    assert (await coordinator._async_update_data())["heating_demand"] is True
    coordinator._previous_modes["living_room_abc12345"] = MODE_IDLE
    coordinator._mode_on_since.pop("living_room_abc12345", None)
    hass.states.get = MagicMock(side_effect=make_mock_states_get(temp="25.0"))
    assert (await coordinator._async_update_data())["heating_demand"] is True
    coordinator._heating_demand_off_since = time.monotonic() - 61

    assert (await coordinator._async_update_data())["heating_demand"] is False
