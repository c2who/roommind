"""Device helpers for RoomMind."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, VERSION


def roommind_device_info(area_id: str, area_name: str) -> DeviceInfo:
    """Return DeviceInfo for a per-room RoomMind device."""
    return DeviceInfo(
        identifiers={(DOMAIN, area_id)},
        name=f"RoomMind {area_name}",
        manufacturer="RoomMind",
        model="Room Controller",
        sw_version=VERSION,
        suggested_area=area_name,
    )


def roommind_hub_device_info() -> DeviceInfo:
    """Return DeviceInfo for the global RoomMind hub device."""
    return DeviceInfo(
        identifiers={(DOMAIN, "hub")},
        name="RoomMind",
        manufacturer="RoomMind",
        model="Hub",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
    )


def get_area_name(hass: HomeAssistant, area_id: str) -> str:
    """Get human-readable area name from area registry."""
    try:
        area_reg = ar.async_get(hass)
        area = area_reg.async_get_area(area_id)
        return area.name if area else area_id
    except Exception:  # noqa: BLE001
        return area_id
