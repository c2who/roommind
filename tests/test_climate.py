"""Tests for RoomMind climate platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.roommind.climate import (
    RoomMindClimate,
    _create_room_climates,
    async_setup_entry,
)
from custom_components.roommind.const import (
    DOMAIN,
    OVERRIDE_BOOST,
    OVERRIDE_CUSTOM,
    OVERRIDE_ECO,
)


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.hass = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    store = MagicMock()
    coordinator.hass.data = {DOMAIN: {"store": store}}
    coordinator.data = {}
    return coordinator, store


def test_create_room_climates(mock_coordinator):
    """Factory creates exactly one climate entity per room."""
    coordinator, _ = mock_coordinator
    climates = _create_room_climates(coordinator, "living_room")
    assert len(climates) == 1
    assert isinstance(climates[0], RoomMindClimate)


def test_unique_id_and_entity_id(mock_coordinator):
    """Climate entity has correct unique_id and entity_id."""
    coordinator, _ = mock_coordinator
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.unique_id == "roommind_living_room_climate"
    assert entity.entity_id == "climate.roommind_living_room_climate"


def test_name(mock_coordinator):
    """Climate entity name is the area_id."""
    coordinator, _ = mock_coordinator
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.name == "living_room"


# --- HVAC mode ---


def test_hvac_mode_heat_cool_when_auto(mock_coordinator):
    """hvac_mode returns HEAT_COOL when climate_mode is auto."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True, "climate_mode": "auto"}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT_COOL


def test_hvac_mode_heat_when_heat_only(mock_coordinator):
    """hvac_mode returns HEAT when climate_mode is heat_only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True, "climate_mode": "heat_only"}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT


def test_hvac_mode_cool_when_cool_only(mock_coordinator):
    """hvac_mode returns COOL when climate_mode is cool_only."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True, "climate_mode": "cool_only"}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.COOL


def test_hvac_mode_off_when_disabled(mock_coordinator):
    """hvac_mode returns OFF when room_enabled is False."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": False, "climate_mode": "auto"}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_off_when_room_missing(mock_coordinator):
    """hvac_mode returns OFF when room doesn't exist in store."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = None
    entity = RoomMindClimate(coordinator, "nonexistent")
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_defaults_enabled(mock_coordinator):
    """hvac_mode defaults to HEAT_COOL when room_enabled not set."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_mode == HVACMode.HEAT_COOL


# --- HVAC action ---


def test_hvac_action_heating(mock_coordinator):
    """hvac_action returns HEATING when coordinator mode is heating."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    coordinator.data = {"rooms": {"living_room": {"mode": "heating"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_action == HVACAction.HEATING


def test_hvac_action_cooling(mock_coordinator):
    """hvac_action returns COOLING when coordinator mode is cooling."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    coordinator.data = {"rooms": {"living_room": {"mode": "cooling"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_action == HVACAction.COOLING


def test_hvac_action_idle(mock_coordinator):
    """hvac_action returns IDLE when coordinator mode is idle."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    coordinator.data = {"rooms": {"living_room": {"mode": "idle"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_action == HVACAction.IDLE


def test_hvac_action_off_when_disabled(mock_coordinator):
    """hvac_action returns OFF when room is disabled."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": False}
    coordinator.data = {"rooms": {"living_room": {"mode": "heating"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.hvac_action == HVACAction.OFF


# --- Temperature properties ---


def test_current_temperature_from_coordinator(mock_coordinator):
    """current_temperature reads from coordinator data."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"living_room": {"current_temp": 20.5}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.current_temperature == 20.5


def test_current_temperature_none_when_no_data(mock_coordinator):
    """current_temperature returns None when coordinator has no data."""
    coordinator, store = mock_coordinator
    coordinator.data = None
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.current_temperature is None


def test_target_temperature_from_coordinator(mock_coordinator):
    """target_temperature reads from coordinator data."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"living_room": {"target_temp": 22.0}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.target_temperature == 22.0


def test_target_temperature_low_in_auto_mode(mock_coordinator):
    """target_temperature_low returns heat_target in auto mode."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "auto"}
    coordinator.data = {"rooms": {"living_room": {"heat_target": 21.0, "cool_target": 25.0}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.target_temperature_low == 21.0
    assert entity.target_temperature_high == 25.0


def test_target_temperature_range_none_in_heat_only(mock_coordinator):
    """target_temperature_low/high return None in heat_only mode."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"climate_mode": "heat_only"}
    coordinator.data = {"rooms": {"living_room": {"heat_target": 21.0, "cool_target": 25.0}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.target_temperature_low is None
    assert entity.target_temperature_high is None


# --- Preset mode ---


def test_preset_mode_none_when_no_override(mock_coordinator):
    """preset_mode returns 'none' when no override is active."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"living_room": {"override_active": False}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.preset_mode == "none"


def test_preset_mode_boost(mock_coordinator):
    """preset_mode returns 'boost' when boost override is active."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"living_room": {"override_active": True, "override_type": "boost"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.preset_mode == "boost"


def test_preset_mode_eco(mock_coordinator):
    """preset_mode returns 'eco' when eco override is active."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"living_room": {"override_active": True, "override_type": "eco"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.preset_mode == "eco"


def test_preset_mode_none_for_custom_override(mock_coordinator):
    """preset_mode returns 'none' for custom overrides."""
    coordinator, store = mock_coordinator
    coordinator.data = {"rooms": {"living_room": {"override_active": True, "override_type": "custom"}}}
    entity = RoomMindClimate(coordinator, "living_room")
    assert entity.preset_mode == "none"


# --- set_hvac_mode ---


@pytest.mark.asyncio
async def test_set_hvac_mode_off(mock_coordinator):
    """Setting hvac_mode to OFF disables the room."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.OFF)
    store.async_update_room.assert_awaited_once_with("living_room", {"room_enabled": False})
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_hvac_mode_heat(mock_coordinator):
    """Setting hvac_mode to HEAT enables room with heat_only."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    store.async_update_room.assert_awaited_once_with(
        "living_room", {"room_enabled": True, "climate_mode": "heat_only"}
    )


@pytest.mark.asyncio
async def test_set_hvac_mode_cool(mock_coordinator):
    """Setting hvac_mode to COOL enables room with cool_only."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.COOL)
    store.async_update_room.assert_awaited_once_with(
        "living_room", {"room_enabled": True, "climate_mode": "cool_only"}
    )


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_cool(mock_coordinator):
    """Setting hvac_mode to HEAT_COOL enables room with auto."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    store.async_update_room.assert_awaited_once_with(
        "living_room", {"room_enabled": True, "climate_mode": "auto"}
    )


# --- set_temperature ---


@pytest.mark.asyncio
async def test_set_temperature_single(mock_coordinator):
    """set_temperature with single temp sets custom override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=22.0)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": 22.0,
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_temperature_dual(mock_coordinator):
    """set_temperature with dual temps sets dual override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_temperature(target_temp_low=20.0, target_temp_high=25.0)
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": 20.0,
            "override_heat": 20.0,
            "override_cool": 25.0,
            "override_until": None,
            "override_type": OVERRIDE_CUSTOM,
        },
    )


@pytest.mark.asyncio
async def test_set_temperature_noop_when_disabled(mock_coordinator):
    """set_temperature does nothing when room is disabled."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": False}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_temperature(temperature=22.0)
    store.async_update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_temperature_noop_no_temp_kwarg(mock_coordinator):
    """set_temperature does nothing when no temperature kwarg is given."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_temperature()
    store.async_update_room.assert_not_awaited()


# --- set_preset_mode ---


@pytest.mark.asyncio
async def test_set_preset_none_clears_override(mock_coordinator):
    """Setting preset to 'none' clears all override fields."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True, "climate_mode": "auto"}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_preset_mode("none")
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": None,
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": None,
        },
    )


@pytest.mark.asyncio
async def test_set_preset_boost_auto_mode(mock_coordinator):
    """Boost preset in auto mode sets dual-target override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "room_enabled": True,
        "climate_mode": "auto",
        "comfort_heat": 22.0,
        "comfort_cool": 25.0,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_preset_mode("boost")
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": 22.0,
            "override_heat": 22.0,
            "override_cool": 25.0,
            "override_until": None,
            "override_type": OVERRIDE_BOOST,
        },
    )


@pytest.mark.asyncio
async def test_set_preset_eco_auto_mode(mock_coordinator):
    """Eco preset in auto mode sets dual-target override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "room_enabled": True,
        "climate_mode": "auto",
        "eco_heat": 18.0,
        "eco_cool": 27.0,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_preset_mode("eco")
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": 18.0,
            "override_heat": 18.0,
            "override_cool": 27.0,
            "override_until": None,
            "override_type": OVERRIDE_ECO,
        },
    )


@pytest.mark.asyncio
async def test_set_preset_boost_heat_only(mock_coordinator):
    """Boost preset in heat_only mode sets single-target override."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "room_enabled": True,
        "climate_mode": "heat_only",
        "comfort_heat": 22.0,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_preset_mode("boost")
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": 22.0,
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": OVERRIDE_BOOST,
        },
    )


@pytest.mark.asyncio
async def test_set_preset_eco_cool_only(mock_coordinator):
    """Eco preset in cool_only mode sets single-target override with cool temp."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {
        "room_enabled": True,
        "climate_mode": "cool_only",
        "eco_cool": 28.0,
    }
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_set_preset_mode("eco")
    store.async_update_room.assert_awaited_once_with(
        "living_room",
        {
            "override_temp": 28.0,
            "override_heat": None,
            "override_cool": None,
            "override_until": None,
            "override_type": OVERRIDE_ECO,
        },
    )


# --- turn_on / turn_off ---


@pytest.mark.asyncio
async def test_turn_off(mock_coordinator):
    """turn_off disables the room."""
    coordinator, store = mock_coordinator
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_turn_off()
    store.async_update_room.assert_awaited_once_with("living_room", {"room_enabled": False})


@pytest.mark.asyncio
async def test_turn_on_when_disabled(mock_coordinator):
    """turn_on enables the room when it was disabled."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": False}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_turn_on()
    store.async_update_room.assert_awaited_once_with("living_room", {"room_enabled": True})


@pytest.mark.asyncio
async def test_turn_on_when_already_enabled(mock_coordinator):
    """turn_on is a no-op when room is already enabled."""
    coordinator, store = mock_coordinator
    store.get_room.return_value = {"room_enabled": True}
    store.async_update_room = AsyncMock()
    entity = RoomMindClimate(coordinator, "living_room")
    await entity.async_turn_on()
    store.async_update_room.assert_not_awaited()


# --- async_setup_entry ---


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_all_rooms():
    """async_setup_entry creates climate entities for all rooms."""
    coordinator = MagicMock()
    coordinator._climate_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {
        "living_room": {"thermostats": ["climate.living"]},
        "bedroom": {},
    }

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert coordinator.async_add_climate_entities is async_add_entities
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert all(isinstance(e, RoomMindClimate) for e in entities)
    assert "living_room" in coordinator._climate_entity_areas
    assert "bedroom" in coordinator._climate_entity_areas


@pytest.mark.asyncio
async def test_async_setup_entry_no_rooms():
    """async_setup_entry does not call async_add_entities when no rooms exist."""
    coordinator = MagicMock()
    coordinator._climate_entity_areas = set()

    store = MagicMock()
    store.get_rooms.return_value = {}

    entry = MagicMock()
    entry.entry_id = "test_entry"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator, "store": store}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_not_called()
