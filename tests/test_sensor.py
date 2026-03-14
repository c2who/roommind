"""Tests for the sensor platform."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.sensor import (
    RoomMindForecastSensor,
    RoomMindModeSensor,
    RoomMindTargetTemperatureSensor,
    _create_room_entities,
    async_setup_entry,
)


def _make_coordinator(rooms_data=None):
    """Build a mock coordinator with data dict."""
    coordinator = MagicMock()
    coordinator.data = {"rooms": rooms_data or {}}
    return coordinator


@pytest.mark.asyncio
async def test_setup_entry_creates_entities(hass, mock_config_entry, store):
    """Entities are created for each existing room."""
    await store.async_load()
    await store.async_save_room("room_a", {"thermostats": ["climate.trv1"]})

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    # Callback stored on coordinator
    assert coordinator.async_add_entities is add_entities
    # 3 entities per room (target_temp + mode + forecast)
    add_entities.assert_called_once()
    entities = add_entities.call_args[0][0]
    assert len(entities) == 3


@pytest.mark.asyncio
async def test_setup_entry_no_rooms(hass, mock_config_entry, store):
    """No entities created when store has no rooms."""
    await store.async_load()

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    assert coordinator.async_add_entities is add_entities
    add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_setup_entry_multiple_rooms(hass, mock_config_entry, store):
    """Entities created for each room."""
    await store.async_load()
    await store.async_save_room("room_a", {"thermostats": ["climate.trv1"]})
    await store.async_save_room("room_b", {"thermostats": ["climate.trv2"]})

    coordinator = _make_coordinator()
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: coordinator,
        "store": store,
    }
    add_entities = MagicMock()

    await async_setup_entry(hass, mock_config_entry, add_entities)

    entities = add_entities.call_args[0][0]
    assert len(entities) == 6  # 3 per room


def test_create_room_entities():
    """_create_room_entities returns target temp, mode, and forecast sensors."""
    coordinator = _make_coordinator()
    entities = _create_room_entities(coordinator, "room_a")
    assert len(entities) == 3
    assert isinstance(entities[0], RoomMindTargetTemperatureSensor)
    assert isinstance(entities[1], RoomMindModeSensor)
    assert isinstance(entities[2], RoomMindForecastSensor)


def test_target_temp_sensor_value():
    """Target temperature sensor returns value from room data."""
    coordinator = _make_coordinator({"room_a": {"target_temp": 21.5}})
    sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    assert sensor.native_value == 21.5


def test_target_temp_sensor_missing_room():
    """Target temperature sensor returns None when room is missing."""
    coordinator = _make_coordinator({})
    sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    assert sensor.native_value is None


def test_target_temp_sensor_missing_key():
    """Target temperature sensor returns None when key is missing."""
    coordinator = _make_coordinator({"room_a": {"mode": "idle"}})
    sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    assert sensor.native_value is None


def test_mode_sensor_value():
    """Mode sensor returns value from room data."""
    coordinator = _make_coordinator({"room_a": {"mode": "heating"}})
    sensor = RoomMindModeSensor(coordinator, "room_a")
    assert sensor.native_value == "heating"


def test_mode_sensor_defaults_to_idle():
    """Mode sensor defaults to 'idle' when key is missing."""
    coordinator = _make_coordinator({"room_a": {"target_temp": 21.0}})
    sensor = RoomMindModeSensor(coordinator, "room_a")
    assert sensor.native_value == "idle"


def test_mode_sensor_missing_room():
    """Mode sensor returns 'idle' when room is missing."""
    coordinator = _make_coordinator({})
    sensor = RoomMindModeSensor(coordinator, "room_a")
    assert sensor.native_value == "idle"


def test_sensor_unique_id():
    """Sensors have correct unique_id format."""
    coordinator = _make_coordinator()
    temp_sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    mode_sensor = RoomMindModeSensor(coordinator, "room_a")
    assert temp_sensor.unique_id == f"{DOMAIN}_room_a_target_temp"
    assert mode_sensor.unique_id == f"{DOMAIN}_room_a_mode"


def test_sensor_entity_id():
    """Sensors have correct entity_id format."""
    coordinator = _make_coordinator()
    temp_sensor = RoomMindTargetTemperatureSensor(coordinator, "room_a")
    mode_sensor = RoomMindModeSensor(coordinator, "room_a")
    forecast_sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert temp_sensor.entity_id == f"sensor.{DOMAIN}_room_a_target_temp"
    assert mode_sensor.entity_id == f"sensor.{DOMAIN}_room_a_mode"
    assert forecast_sensor.entity_id == f"sensor.{DOMAIN}_room_a_forecast"


# --- Forecast sensor tests ---


def _make_forecast(actions: list[str], dt: int = 300) -> list[dict]:
    """Build a forecast list with the given actions (5-min blocks by default)."""
    now = time.time()
    return [
        {"ts": round(now + (i + 1) * dt, 1), "temp": round(20.0 + i * 0.1, 2), "action": a}
        for i, a in enumerate(actions)
    ]


def test_forecast_sensor_learning_no_room():
    """Forecast sensor returns 'learning' when room is missing."""
    coordinator = _make_coordinator({})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "learning"
    assert sensor.icon == "mdi:school-outline"


def test_forecast_sensor_learning_no_forecast_no_confidence():
    """Forecast sensor returns 'learning' when no forecast and no confidence."""
    coordinator = _make_coordinator({"room_a": {"mode": "idle"}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "learning"
    assert sensor.icon == "mdi:school-outline"


def test_forecast_sensor_no_forecast_confident():
    """Forecast sensor returns 'no forecast' when confident but no forecast data."""
    coordinator = _make_coordinator({"room_a": {"mode": "idle", "confidence": 0.3, "forecast": []}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "no forecast"
    assert sensor.icon == "mdi:thermostat"


def test_forecast_sensor_all_heating():
    """Forecast sensor shows heating duration when all blocks are heat."""
    forecast = _make_forecast(["heat"] * 6)
    coordinator = _make_coordinator({"room_a": {"forecast": forecast}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "heating for 30+ min"
    assert sensor.icon == "mdi:radiator"


def test_forecast_sensor_all_cooling():
    """Forecast sensor shows cooling duration when all blocks are cool."""
    forecast = _make_forecast(["cool"] * 4)
    coordinator = _make_coordinator({"room_a": {"forecast": forecast}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "cooling for 20+ min"
    assert sensor.icon == "mdi:snowflake"


def test_forecast_sensor_all_idle():
    """Forecast sensor shows idle duration when all blocks are idle."""
    forecast = _make_forecast(["idle"] * 12)
    coordinator = _make_coordinator({"room_a": {"forecast": forecast}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "idle for 60+ min"
    assert sensor.icon == "mdi:thermostat"


def test_forecast_sensor_mode_change():
    """Forecast sensor shows first mode and then next mode."""
    forecast = _make_forecast(["heat", "heat", "heat", "idle", "idle", "idle"])
    coordinator = _make_coordinator({"room_a": {"forecast": forecast}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.native_value == "heating for 15 min, then idle"


def test_forecast_sensor_attributes_with_change():
    """Forecast sensor attributes include next change and predicted temps."""
    forecast = _make_forecast(["heat", "heat", "idle", "idle", "idle", "idle"])
    coordinator = _make_coordinator({"room_a": {"forecast": forecast}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    attrs = sensor.extra_state_attributes
    assert attrs["next_change_action"] == "idle"
    assert attrs["next_change_minutes"] is not None
    assert attrs["forecast"] == forecast
    assert "predicted_temp_30m" in attrs
    assert "predicted_temp_1h" in attrs


def test_forecast_sensor_attributes_no_change():
    """Forecast sensor attributes show None for next change when all same action."""
    forecast = _make_forecast(["heat"] * 6)
    coordinator = _make_coordinator({"room_a": {"forecast": forecast}})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    attrs = sensor.extra_state_attributes
    assert attrs["next_change_action"] is None
    assert attrs["next_change_minutes"] is None


def test_forecast_sensor_attributes_empty():
    """Forecast sensor attributes are empty when room is missing."""
    coordinator = _make_coordinator({})
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.extra_state_attributes == {}


def test_forecast_sensor_unique_id():
    """Forecast sensor has correct unique_id."""
    coordinator = _make_coordinator()
    sensor = RoomMindForecastSensor(coordinator, "room_a")
    assert sensor.unique_id == f"{DOMAIN}_room_a_forecast"


def test_forecast_sensor_unrecorded_attributes():
    """Forecast sensor excludes bulky forecast list from recorder."""
    assert "forecast" in RoomMindForecastSensor._unrecorded_attributes
