"""Sensor platform for RoomMind."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator
from .device import get_area_name, roommind_device_info

_LOGGER = logging.getLogger(__name__)


def _create_room_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:
    """Create the standard set of sensor entities for a room."""
    return [
        RoomMindTargetTemperatureSensor(coordinator, area_id),
        RoomMindModeSensor(coordinator, area_id),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind sensor entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]

    # Store the callback on the coordinator so dynamic entity creation works
    coordinator.async_add_entities = async_add_entities

    # Create entities for rooms that already exist in the store
    rooms = store.get_rooms()
    entities: list[SensorEntity] = []
    for area_id, room in rooms.items():
        entities.extend(_create_room_entities(coordinator, area_id))
        coordinator._entity_areas.add(area_id)
        if room.get("covers"):
            entities.extend(_create_cover_sensors(coordinator, area_id, room["covers"]))
            coordinator._cover_sensor_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class _RoomMindBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for all RoomMind room sensors."""

    _attr_has_entity_name = True
    _data_key: str  # Key in the room state dict (e.g. "current_temp")

    def __init__(
        self,
        coordinator: RoomMindCoordinator,
        area_id: str,
        suffix: str,
        name_label: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_{suffix}"
        self._attr_name = name_label
        self.entity_id = f"sensor.{DOMAIN}_{area_id}_{suffix}"
        area_name = get_area_name(coordinator.hass, area_id)
        self._attr_device_info = roommind_device_info(area_id, area_name)

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value from the coordinator data."""
        if self.coordinator.data is None:
            return None
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get(self._data_key)
            return val if isinstance(val, (float, int, str)) else None
        return None


class RoomMindTargetTemperatureSensor(_RoomMindBaseSensor):
    """Sensor showing the target temperature for a RoomMind room."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _data_key = "target_temp"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "target_temp", "Target Temperature")


class RoomMindModeSensor(_RoomMindBaseSensor):
    """Sensor showing the current mode for a RoomMind room."""

    _data_key = "mode"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "mode", "Mode")

    @property
    def native_value(self) -> str | None:
        """Return the current mode, defaulting to 'idle'."""
        if self.coordinator.data is None:
            return "idle"
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get("mode", "idle")
            return str(val) if val is not None else "idle"
        return "idle"


class RoomMindCoverShadingPositionSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the target cover shading position (0-100%) for debugging.

    One sensor per cover entity. Currently reads room-level position;
    will read per-cover position once orientation-based control is added.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:blinds"

    def __init__(
        self,
        coordinator: RoomMindCoordinator,
        area_id: str,
        cover_entity_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._cover_entity_id = cover_entity_id
        sanitized_eid = cover_entity_id.removeprefix("cover.")
        self._attr_unique_id = f"{DOMAIN}_{area_id}_shading_position_{sanitized_eid}"
        self.entity_id = f"sensor.{DOMAIN}_{area_id}_shading_position_{sanitized_eid}"
        area_name = get_area_name(coordinator.hass, area_id)
        self._attr_device_info = roommind_device_info(area_id, area_name)

    @property
    def name(self) -> str:
        """Return friendly name based on the cover entity."""
        if self.coordinator.hass:
            state = self.coordinator.hass.states.get(self._cover_entity_id)
            if state and state.attributes.get("friendly_name"):
                return f"{state.attributes['friendly_name']} Shading Position"
        return f"{self._cover_entity_id} Shading Position"

    @property
    def native_value(self) -> int | None:
        """Return the target shading position."""
        if self.coordinator.data is None:
            return None
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            per_cover = room.get("cover_debug", {}).get(self._cover_entity_id, {})
            val = per_cover.get("target_position", room.get("cover_shading_position"))
            _LOGGER.debug(
                "Shading position sensor read [%s/%s]: per_cover=%s fallback_room_target=%s",
                self._area_id,
                self._cover_entity_id,
                per_cover,
                val,
                room.get("cover_shading_position"),
            )
            return val if isinstance(val, (int, float)) else None
        return None


def _create_cover_sensors(
    coordinator: RoomMindCoordinator,
    area_id: str,
    cover_entity_ids: list[str],
) -> list[SensorEntity]:
    """Create shading position sensors for each cover entity in a room."""
    return [RoomMindCoverShadingPositionSensor(coordinator, area_id, eid) for eid in cover_entity_ids]
