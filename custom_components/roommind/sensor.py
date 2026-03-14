"""Sensor platform for RoomMind."""

from __future__ import annotations

import time

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoomMindCoordinator
from .device import get_area_name, roommind_device_info


def _create_room_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:
    """Create the standard set of sensor entities for a room."""
    return [
        RoomMindTargetTemperatureSensor(coordinator, area_id),
        RoomMindModeSensor(coordinator, area_id),
        RoomMindForecastSensor(coordinator, area_id),
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
    for area_id in rooms:
        entities.extend(_create_room_entities(coordinator, area_id))
        coordinator._entity_areas.add(area_id)
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
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get(self._data_key)
            return val if isinstance(val, (float, int, str)) else None
        return None


class RoomMindTargetTemperatureSensor(_RoomMindBaseSensor):
    """Sensor showing the target temperature for a RoomMind room."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
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
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get("mode", "idle")
            return str(val) if val is not None else "idle"
        return "idle"


_ACTION_ICONS: dict[str, str] = {
    "heat": "mdi:radiator",
    "cool": "mdi:snowflake",
    "idle": "mdi:thermostat",
}


class RoomMindForecastSensor(_RoomMindBaseSensor):
    """Sensor showing the MPC forecast summary for a RoomMind room."""

    _data_key = "forecast"
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "forecast", "Forecast")

    @property
    def native_value(self) -> str | None:
        """Return a human-readable forecast summary."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if not room:
            return "learning"
        forecast: list[dict] = room.get("forecast", [])
        if not forecast:
            confidence = room.get("confidence")
            if confidence is not None and confidence <= 0.5:
                return "no forecast"
            return "learning"
        return self._build_summary(forecast)

    @property
    def icon(self) -> str:
        """Return a dynamic icon based on the current forecast action."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if not room:
            return "mdi:school-outline"
        forecast: list[dict] = room.get("forecast", [])
        if not forecast:
            confidence = room.get("confidence")
            if confidence is not None and confidence <= 0.5:
                return "mdi:thermostat"
            return "mdi:school-outline"
        action = forecast[0].get("action", "idle")
        return _ACTION_ICONS.get(action, "mdi:thermostat")

    @property
    def extra_state_attributes(self) -> dict:
        """Return forecast data and derived scalar attributes."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if not room:
            return {}
        forecast: list[dict] = room.get("forecast", [])
        attrs: dict = {"forecast": forecast}

        if forecast:
            now = time.time()
            first_action = forecast[0].get("action", "idle")

            # Find next mode change
            next_action = None
            next_change_minutes = None
            for block in forecast:
                if block.get("action") != first_action:
                    next_action = block["action"]
                    next_change_minutes = round((block["ts"] - now) / 60)
                    break

            attrs["next_change_action"] = next_action
            attrs["next_change_minutes"] = next_change_minutes
            attrs["predicted_temp_30m"] = self._find_predicted_temp(forecast, 30 * 60)
            attrs["predicted_temp_1h"] = self._find_predicted_temp(forecast, 60 * 60)
        else:
            attrs["next_change_action"] = None
            attrs["next_change_minutes"] = None
            attrs["predicted_temp_30m"] = None
            attrs["predicted_temp_1h"] = None

        return attrs

    @staticmethod
    def _find_predicted_temp(forecast: list[dict], offset_seconds: int) -> float | None:
        """Find the predicted temperature closest to a future time offset."""
        if not forecast:
            return None
        target_ts = forecast[0]["ts"] - (forecast[1]["ts"] - forecast[0]["ts"]) + offset_seconds if len(forecast) >= 2 else forecast[0]["ts"] + offset_seconds
        # The first block's ts is already offset from "now" by one dt,
        # so compute now from the forecast timestamps
        if len(forecast) >= 2:
            dt = forecast[1]["ts"] - forecast[0]["ts"]
            now_approx = forecast[0]["ts"] - dt
        else:
            return forecast[0].get("temp")
        target_ts = now_approx + offset_seconds
        best = None
        best_diff = float("inf")
        for block in forecast:
            diff = abs(block["ts"] - target_ts)
            if diff < best_diff:
                best_diff = diff
                best = block.get("temp")
        return best

    @staticmethod
    def _build_summary(forecast: list[dict]) -> str:
        """Build a human-readable summary string from forecast blocks."""
        if not forecast:
            return "no forecast"

        first_action = forecast[0].get("action", "idle")
        label = {"heat": "heating", "cool": "cooling", "idle": "idle"}.get(first_action, first_action)

        # Find first block with a different action
        change_idx = None
        for i, block in enumerate(forecast):
            if block.get("action") != first_action:
                change_idx = i
                break

        if change_idx is None:
            # All blocks same action — compute total duration
            if len(forecast) >= 2:
                dt = forecast[1]["ts"] - forecast[0]["ts"]
                total_min = round(len(forecast) * dt / 60)
            else:
                total_min = 5
            return f"{label} for {total_min}+ min"

        # Compute minutes until the change
        if len(forecast) >= 2:
            dt = forecast[1]["ts"] - forecast[0]["ts"]
        else:
            dt = 300  # 5 min default
        minutes_until = round(change_idx * dt / 60)
        next_action = forecast[change_idx].get("action", "idle")
        next_label = {"heat": "heating", "cool": "cooling", "idle": "idle"}.get(next_action, next_action)
        return f"{label} for {minutes_until} min, then {next_label}"
