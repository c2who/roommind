"""Shared fixtures for integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.coordinator import RoomMindCoordinator
from custom_components.roommind.store import RoomMindStore

ROOM_LIVING = {
    "area_id": "living_room",
    "thermostats": ["climate.living_room"],
    "acs": [],
    "temperature_sensor": "sensor.living_room_temp",
    "humidity_sensor": "sensor.living_room_humidity",
    "climate_mode": "auto",
    "schedules": [{"entity_id": "schedule.living_room"}],
    "schedule_selector_entity": "",
    "comfort_temp": 21.0,
    "eco_temp": 17.0,
    "window_sensors": [],
    "window_open_delay": 0,
    "window_close_delay": 0,
    "heating_system_type": "",
    "presence_persons": [],
}


def make_hass_states(
    temp="18.0",
    humidity="55.0",
    schedule_state="on",
    outdoor_temp="5.0",
    climate_hvac_modes=None,
    climate_state="idle",
    extra=None,
):
    if climate_hvac_modes is None:
        climate_hvac_modes = ["off", "heat"]
    if extra is None:
        extra = {}

    def _get(entity_id):
        entities = {
            "sensor.living_room_temp": ("state", temp, {}),
            "sensor.living_room_humidity": ("state", humidity, {}),
            "schedule.living_room": ("state", schedule_state, {}),
            "sensor.outdoor_temp": ("state", outdoor_temp, {}),
            "climate.living_room": (
                "state",
                climate_state,
                {"hvac_modes": climate_hvac_modes, "hvac_action": "idle"},
            ),
        }
        if entity_id in extra:
            val = extra[entity_id]
            s = MagicMock()
            if isinstance(val, tuple):
                s.state = val[0]
                s.attributes = val[1] if len(val) > 1 else {}
            else:
                s.state = val
                s.attributes = {}
            return s
        if entity_id in entities:
            _, state, attrs = entities[entity_id]
            s = MagicMock()
            s.state = state
            s.attributes = attrs
            return s
        return None

    return _get


DEFAULT_SETTINGS = {"outdoor_temp_sensor": "sensor.outdoor_temp"}


@pytest.fixture
def real_store(hass):
    s = RoomMindStore(hass)
    s._store = AsyncMock()
    s._store.async_load = AsyncMock(return_value=None)
    s._store.async_save = AsyncMock()
    return s


async def setup_room(store, room=None, settings=None):
    """Helper: load store, save room, save settings."""
    await store.async_load()
    await store.async_save_room(
        (room or ROOM_LIVING)["area_id"],
        room or ROOM_LIVING,
    )
    await store.async_save_settings(settings or DEFAULT_SETTINGS)


@pytest.fixture
def coordinator(hass, mock_config_entry, real_store):
    hass.data = {"roommind": {"store": real_store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=make_hass_states())
    hass.config.latitude = 50.0
    hass.config.longitude = 10.0
    hass.config.units = MagicMock()
    hass.config.units.temperature_unit = "°C"
    with patch("homeassistant.helpers.frame.report_usage"):
        c = RoomMindCoordinator(hass, mock_config_entry)
    return c
