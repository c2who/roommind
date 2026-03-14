"""Binary sensor platform for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator


def _create_room_binary_sensors(
    coordinator: RoomMindCoordinator,
    area_id: str,
    room: dict[str, Any],
) -> list[BinarySensorEntity]:
    """Create binary sensor entities for a room.

    Creates one paused sensor per room plus one shading sensor per cover entity.
    """
    entities: list[BinarySensorEntity] = [
        RoomMindCoverPausedSensor(coordinator, area_id),
    ]
    for cover_eid in room.get("covers", []):
        entities.append(RoomMindCoverShadingSensor(coordinator, area_id, cover_eid))
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind binary sensor entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_binary_sensor_entities = async_add_entities
    rooms = store.get_rooms()
    entities: list[BinarySensorEntity] = []
    for area_id, room in rooms.items():
        if bool(room.get("covers")):
            entities.extend(_create_room_binary_sensors(coordinator, area_id, room))
            coordinator._binary_sensor_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class RoomMindCoverPausedSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if cover auto-control is paused by user override."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_cover_paused"
        self._attr_name = f"{area_id.replace('_', ' ').title()} Cover Paused"
        self._attr_icon = "mdi:hand-back-right"
        self.entity_id = f"binary_sensor.{DOMAIN}_{area_id}_cover_paused"

    @property
    def is_on(self) -> bool:
        """Return True if user override is active (auto-control paused)."""
        if self.coordinator.data is None:
            return False
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        return bool(room.get("cover_auto_paused", False)) if room else False


class RoomMindCoverShadingSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if RoomMind recommends shading for a specific cover.

    ON = shading active (cover should be partially/fully closed).
    OFF = no shading needed (cover fully open).
    Attribute ``target_position`` shows the recommended cover position (0-100).
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RoomMindCoordinator, area_id: str, cover_entity_id: str
    ) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._cover_entity_id = cover_entity_id
        # strip "cover." prefix for the sanitized id
        sanitized_eid = cover_entity_id.removeprefix("cover.")
        self._attr_unique_id = f"{DOMAIN}_{area_id}_shading_{sanitized_eid}"
        self._attr_icon = "mdi:blinds"
        self.entity_id = f"binary_sensor.{DOMAIN}_{area_id}_shading_{sanitized_eid}"

    @property
    def name(self) -> str:
        """Return friendly name based on the cover entity."""
        if self.coordinator.hass:
            state = self.coordinator.hass.states.get(self._cover_entity_id)
            if state and state.attributes.get("friendly_name"):
                return f"{state.attributes['friendly_name']} Shading"
        return f"{self._cover_entity_id} Shading"

    @property
    def is_on(self) -> bool:
        """Return True if shading is recommended (target position < 100)."""
        if self.coordinator.data is None:
            return False
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        return bool(room.get("cover_shading_active", False)) if room else False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return target_position as attribute."""
        if self.coordinator.data is None:
            return {"target_position": None}
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if not room:
            return {"target_position": None}
        return {"target_position": room.get("cover_shading_position")}
