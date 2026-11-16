"""Home Assistant device information for RoomMind entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, VERSION


def roommind_device_info(area_id: str, area_name: str) -> DeviceInfo:
    """Group a room's entities under its own Home Assistant device."""
    return DeviceInfo(
        identifiers={(DOMAIN, area_id)},
        name=f"RoomMind {area_name}",
        manufacturer="RoomMind",
        model="Room Controller",
        sw_version=VERSION,
        suggested_area=area_name,
    )


def roommind_hub_device_info() -> DeviceInfo:
    """Group global controls under a service device."""
    return DeviceInfo(
        identifiers={(DOMAIN, "hub")},
        name="RoomMind",
        manufacturer="RoomMind",
        model="Hub",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
    )
