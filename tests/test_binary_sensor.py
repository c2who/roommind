"""Tests for RoomMind binary sensor platform."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.binary_sensor import (
    RoomMindCoverPausedSensor,
    RoomMindCoverShadingSensor,
    RoomMindHeatingDemandSensor,
    _create_room_binary_sensors,
    async_setup_entry,
)
from custom_components.roommind.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.data = {"rooms": {"living_room": {"cover_auto_paused": False}}}
    coordinator.hass = MagicMock()
    return coordinator


def test_cover_paused_off(mock_coordinator):
    """Binary sensor OFF when no user override active."""
    mock_coordinator.data = {"rooms": {"living_room": {"cover_auto_paused": False}}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is False


def test_cover_paused_on(mock_coordinator):
    """Binary sensor ON when user override is active."""
    mock_coordinator.data = {"rooms": {"living_room": {"cover_auto_paused": True}}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is True


def test_cover_paused_missing_room(mock_coordinator):
    """Binary sensor returns False when room doesn't exist."""
    mock_coordinator.data = {"rooms": {}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "nonexistent")
    assert sensor.is_on is False


def test_cover_paused_missing_key(mock_coordinator):
    """Binary sensor returns False when cover_auto_paused key is missing."""
    mock_coordinator.data = {"rooms": {"living_room": {}}}
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is False


def test_binary_sensor_unique_id_and_entity_id(mock_coordinator):
    """Binary sensor has correct unique_id and entity_id."""
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.unique_id == "roommind_living_room_cover_paused"
    assert sensor.entity_id == "binary_sensor.roommind_living_room_cover_paused"


def test_create_room_binary_sensors(mock_coordinator):
    """Factory creates 1 paused sensor + N shading sensors (one per cover)."""
    room = {"covers": ["cover.living_blinds", "cover.living_curtain"]}
    sensors = _create_room_binary_sensors(mock_coordinator, "living_room", room)
    assert len(sensors) == 3
    assert isinstance(sensors[0], RoomMindCoverPausedSensor)
    assert isinstance(sensors[1], RoomMindCoverShadingSensor)
    assert isinstance(sensors[2], RoomMindCoverShadingSensor)


def test_create_room_binary_sensors_single_cover(mock_coordinator):
    """Factory creates 1 paused + 1 shading for a single cover."""
    room = {"covers": ["cover.blinds"]}
    sensors = _create_room_binary_sensors(mock_coordinator, "living_room", room)
    assert len(sensors) == 2
    assert isinstance(sensors[0], RoomMindCoverPausedSensor)
    assert isinstance(sensors[1], RoomMindCoverShadingSensor)


def test_cover_paused_coordinator_data_none(mock_coordinator):
    """Binary sensor returns False when coordinator.data is None (before first update)."""
    mock_coordinator.data = None
    sensor = RoomMindCoverPausedSensor(mock_coordinator, "living_room")
    assert sensor.is_on is False


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_rooms_with_covers():
    """async_setup_entry creates binary sensors for rooms with covers configured."""
    coordinator = MagicMock()
    coordinator._binary_sensor_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"covers": ["cover.blinds_left", "cover.blinds_right"]},
        "bedroom": {},  # no covers — should be skipped
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    # Callback stored on coordinator
    assert coordinator.async_add_binary_sensor_entities is async_add_entities
    # 1 hub-level heating demand + living_room: 1 paused + 2 shading = 4 entities
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 4
    assert isinstance(entities[0], RoomMindHeatingDemandSensor)
    assert isinstance(entities[1], RoomMindCoverPausedSensor)
    assert isinstance(entities[2], RoomMindCoverShadingSensor)
    assert isinstance(entities[3], RoomMindCoverShadingSensor)
    # Area tracked
    assert "living_room" in coordinator._binary_sensor_entity_areas
    assert "bedroom" not in coordinator._binary_sensor_entity_areas


@pytest.mark.asyncio
async def test_async_setup_entry_no_covers_only_hub_sensor():
    """async_setup_entry creates only the hub heating demand sensor when no rooms have covers."""
    coordinator = MagicMock()
    coordinator._binary_sensor_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {"bedroom": {}}

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], RoomMindHeatingDemandSensor)


# ---- RoomMindHeatingDemandSensor tests ----


def test_heating_demand_on(mock_coordinator):
    """Heating demand sensor ON when coordinator reports demand."""
    mock_coordinator.data = {
        "heating_demand": True,
        "rooms_heating_now": ["living_room"],
        "rooms_heating_forecast": [],
        "rooms": {},
    }
    sensor = RoomMindHeatingDemandSensor(mock_coordinator)
    assert sensor.is_on is True
    assert sensor.icon == "mdi:radiator"
    assert sensor.extra_state_attributes == {
        "rooms_heating_now": ["living_room"],
        "rooms_heating_forecast": [],
    }


def test_heating_demand_off(mock_coordinator):
    """Heating demand sensor OFF when no demand."""
    mock_coordinator.data = {
        "heating_demand": False,
        "rooms_heating_now": [],
        "rooms_heating_forecast": [],
        "rooms": {},
    }
    sensor = RoomMindHeatingDemandSensor(mock_coordinator)
    assert sensor.is_on is False
    assert sensor.icon == "mdi:radiator-off"


def test_heating_demand_none_data(mock_coordinator):
    """Heating demand sensor OFF when coordinator data is None."""
    mock_coordinator.data = None
    sensor = RoomMindHeatingDemandSensor(mock_coordinator)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {
        "rooms_heating_now": [],
        "rooms_heating_forecast": [],
    }


# ---- RoomMindCoverShadingSensor tests ----


def test_shading_sensor_on(mock_coordinator):
    """Shading sensor ON when cover_shading_active is True."""
    mock_coordinator.data = {"rooms": {"living_room": {"cover_shading_active": True, "cover_shading_position": 30}}}
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {"recommended_position": 30}


def test_shading_sensor_off(mock_coordinator):
    """Shading sensor OFF when cover_shading_active is False."""
    mock_coordinator.data = {"rooms": {"living_room": {"cover_shading_active": False, "cover_shading_position": 100}}}
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"recommended_position": 100}


def test_shading_sensor_uses_per_cover_debug(mock_coordinator):
    """Per-cover debug data overrides room-level shading state."""
    mock_coordinator.data = {
        "rooms": {
            "living_room": {
                "cover_shading_active": False,
                "cover_shading_position": 100,
                "cover_debug": {
                    "cover.living_blinds": {
                        "shading_active": True,
                        "recommended_position": 45,
                    }
                },
            }
        }
    }
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {"recommended_position": 45}


def test_shading_sensor_does_not_log_on_state_reads(mock_coordinator, caplog):
    """Shading sensor reads stay quiet to avoid HA state-access log spam."""
    mock_coordinator.data = {
        "rooms": {
            "living_room": {
                "cover_shading_active": False,
                "cover_shading_position": 100,
                "cover_debug": {
                    "cover.living_blinds": {
                        "shading_active": True,
                        "recommended_position": 45,
                    }
                },
            }
        }
    }
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")

    with caplog.at_level(logging.DEBUG):
        assert sensor.is_on is True
        assert sensor.extra_state_attributes == {"recommended_position": 45}

    assert caplog.text == ""


def test_shading_sensor_missing_room(mock_coordinator):
    """Shading sensor returns False when room doesn't exist."""
    mock_coordinator.data = {"rooms": {}}
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "nonexistent", "cover.blinds")
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"recommended_position": None}


def test_shading_sensor_coordinator_none(mock_coordinator):
    """Shading sensor returns False when coordinator data is None."""
    mock_coordinator.data = None
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.blinds")
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"recommended_position": None}


def test_shading_sensor_unique_id_and_entity_id(mock_coordinator):
    """Per-cover shading sensor has correct unique_id and entity_id."""
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")
    assert sensor.unique_id == "roommind_living_room_shading_living_blinds"
    assert sensor.entity_id == "binary_sensor.roommind_living_room_shading_living_blinds"


def test_shading_sensor_name_from_friendly_name(mock_coordinator):
    """Shading sensor name uses cover entity's friendly_name."""
    state = MagicMock()
    state.attributes = {"friendly_name": "Living Room Blinds"}
    mock_coordinator.hass.states.get.return_value = state
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")
    assert sensor.name == "Living Room Blinds Shading"


def test_shading_sensor_name_fallback(mock_coordinator):
    """Shading sensor name falls back to entity_id when no friendly_name."""
    mock_coordinator.hass.states.get.return_value = None
    sensor = RoomMindCoverShadingSensor(mock_coordinator, "living_room", "cover.living_blinds")
    assert sensor.name == "cover.living_blinds Shading"
