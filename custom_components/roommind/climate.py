"""Climate platform for RoomMind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CLIMATE_MODE_AUTO,
    CLIMATE_MODE_COOL_ONLY,
    CLIMATE_MODE_HEAT_ONLY,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    DOMAIN,
    MODE_COOLING,
    MODE_HEATING,
    OVERRIDE_BOOST,
    OVERRIDE_CUSTOM,
    OVERRIDE_ECO,
    ROOM_ENABLED_DEFAULT,
)
from .coordinator import RoomMindCoordinator


def _create_room_climates(
    coordinator: RoomMindCoordinator,
    area_id: str,
) -> list[ClimateEntity]:
    """Create climate entities for a room."""
    return [RoomMindClimate(coordinator, area_id)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind climate entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]
    coordinator.async_add_climate_entities = async_add_entities
    rooms = store.get_rooms()
    entities: list[ClimateEntity] = []
    for area_id in rooms:
        entities.extend(_create_room_climates(coordinator, area_id))
        coordinator._climate_entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


# Maps RoomMind climate_mode → HA HVACMode
_CLIMATE_MODE_TO_HVAC: dict[str, HVACMode] = {
    CLIMATE_MODE_AUTO: HVACMode.HEAT_COOL,
    CLIMATE_MODE_HEAT_ONLY: HVACMode.HEAT,
    CLIMATE_MODE_COOL_ONLY: HVACMode.COOL,
}

# Reverse map: HA HVACMode → RoomMind climate_mode
_HVAC_TO_CLIMATE_MODE: dict[HVACMode, str] = {v: k for k, v in _CLIMATE_MODE_TO_HVAC.items()}


class RoomMindClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity representing full RoomMind room state."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermostat"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_preset_modes = ["none", "boost", "eco"]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_climate"
        self._attr_name = area_id.replace("_", " ").title()
        self.entity_id = f"climate.{DOMAIN}_{area_id}_climate"

    def _get_room(self) -> dict | None:
        """Return current room config from store."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        result: dict | None = store.get_room(self._area_id)
        return result

    def _get_live(self) -> dict:
        """Return live coordinator data for this room."""
        data = self.coordinator.data
        if not data:
            return {}
        result: dict = data.get("rooms", {}).get(self._area_id, {})
        return result

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode based on room_enabled and climate_mode."""
        room = self._get_room()
        if not room:
            return HVACMode.OFF
        room_enabled = room.get("room_enabled", ROOM_ENABLED_DEFAULT)
        if not room_enabled:
            return HVACMode.OFF
        climate_mode = room.get("climate_mode", CLIMATE_MODE_AUTO)
        return _CLIMATE_MODE_TO_HVAC.get(climate_mode, HVACMode.HEAT_COOL)

    @property
    def hvac_action(self) -> HVACAction:
        """Return current HVAC action from coordinator data."""
        room = self._get_room()
        if not room or not room.get("room_enabled", ROOM_ENABLED_DEFAULT):
            return HVACAction.OFF
        live = self._get_live()
        mode = live.get("mode", "idle")
        if mode == MODE_HEATING:
            return HVACAction.HEATING
        if mode == MODE_COOLING:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return the room's current temperature from coordinator data."""
        live = self._get_live()
        val = live.get("current_temp")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature(self) -> float | None:
        """Return single target temperature (used in HEAT/COOL mode)."""
        live = self._get_live()
        val = live.get("target_temp")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature_low(self) -> float | None:
        """Return heating target for HEAT_COOL mode."""
        room = self._get_room()
        if not room or room.get("climate_mode", CLIMATE_MODE_AUTO) != CLIMATE_MODE_AUTO:
            return None
        live = self._get_live()
        val = live.get("heat_target")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def target_temperature_high(self) -> float | None:
        """Return cooling target for HEAT_COOL mode."""
        room = self._get_room()
        if not room or room.get("climate_mode", CLIMATE_MODE_AUTO) != CLIMATE_MODE_AUTO:
            return None
        live = self._get_live()
        val = live.get("cool_target")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def preset_mode(self) -> str:
        """Return current preset mode based on override state."""
        live = self._get_live()
        if not live.get("override_active", False):
            return "none"
        override_type = live.get("override_type")
        if override_type == OVERRIDE_BOOST:
            return "boost"
        if override_type == OVERRIDE_ECO:
            return "eco"
        return "none"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode: OFF disables room, HEAT/COOL/HEAT_COOL sets climate_mode."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        if hvac_mode == HVACMode.OFF:
            await store.async_update_room(self._area_id, {"room_enabled": False})
        else:
            climate_mode = _HVAC_TO_CLIMATE_MODE.get(hvac_mode, CLIMATE_MODE_AUTO)
            await store.async_update_room(
                self._area_id,
                {"room_enabled": True, "climate_mode": climate_mode},
            )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature via override."""
        room = self._get_room()
        if not room or not room.get("room_enabled", ROOM_ENABLED_DEFAULT):
            return

        store = self.coordinator.hass.data[DOMAIN]["store"]
        temp_low = kwargs.get("target_temp_low")
        temp_high = kwargs.get("target_temp_high")
        temperature = kwargs.get("temperature")

        if temp_low is not None and temp_high is not None:
            # Dual-target set (HEAT_COOL mode)
            await store.async_update_room(
                self._area_id,
                {
                    "override_temp": temp_low,
                    "override_heat": temp_low,
                    "override_cool": temp_high,
                    "override_until": None,
                    "override_type": OVERRIDE_CUSTOM,
                },
            )
        elif temperature is not None:
            # Single-target set
            await store.async_update_room(
                self._area_id,
                {
                    "override_temp": temperature,
                    "override_heat": None,
                    "override_cool": None,
                    "override_until": None,
                    "override_type": OVERRIDE_CUSTOM,
                },
            )
        else:
            return

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode: boost/eco activate override, none clears it."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        room = self._get_room()
        if not room:
            return

        if preset_mode == "none":
            await store.async_update_room(
                self._area_id,
                {
                    "override_temp": None,
                    "override_heat": None,
                    "override_cool": None,
                    "override_until": None,
                    "override_type": None,
                },
            )
        elif preset_mode in ("boost", "eco"):
            climate_mode = room.get("climate_mode", CLIMATE_MODE_AUTO)

            if preset_mode == "boost":
                heat_temp = room.get("comfort_heat", room.get("comfort_temp", DEFAULT_COMFORT_HEAT))
                cool_temp = room.get("comfort_cool", DEFAULT_COMFORT_COOL)
                override_type = OVERRIDE_BOOST
            else:
                heat_temp = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
                cool_temp = room.get("eco_cool", DEFAULT_ECO_COOL)
                override_type = OVERRIDE_ECO

            if climate_mode == CLIMATE_MODE_AUTO:
                await store.async_update_room(
                    self._area_id,
                    {
                        "override_temp": heat_temp,
                        "override_heat": heat_temp,
                        "override_cool": cool_temp,
                        "override_until": None,
                        "override_type": override_type,
                    },
                )
            elif climate_mode == CLIMATE_MODE_COOL_ONLY:
                await store.async_update_room(
                    self._area_id,
                    {
                        "override_temp": cool_temp,
                        "override_heat": None,
                        "override_cool": None,
                        "override_until": None,
                        "override_type": override_type,
                    },
                )
            else:
                await store.async_update_room(
                    self._area_id,
                    {
                        "override_temp": heat_temp,
                        "override_heat": None,
                        "override_cool": None,
                        "override_until": None,
                        "override_type": override_type,
                    },
                )

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on room control (restore last climate_mode)."""
        room = self._get_room()
        if room and not room.get("room_enabled", ROOM_ENABLED_DEFAULT):
            store = self.coordinator.hass.data[DOMAIN]["store"]
            await store.async_update_room(self._area_id, {"room_enabled": True})
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off room control."""
        store = self.coordinator.hass.data[DOMAIN]["store"]
        await store.async_update_room(self._area_id, {"room_enabled": False})
        await self.coordinator.async_request_refresh()
