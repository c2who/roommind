"""Tests for fan-only idle mode."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.control.mpc_controller import (
    MPCController,
    _last_commands,
    async_idle_device,
)
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room

# ---------------------------------------------------------------------------
# async_idle_device — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_idle_device_off():
    """Device with idle_action='off' delegates to async_turn_off_climate."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [{"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "off", "idle_fan_mode": ""}]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_only():
    """Device with idle_action='fan_only' and supported fan_only mode sets fan_only + fan_mode."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    assert calls[0][0] == ("climate", "set_hvac_mode", {"entity_id": "climate.ac1", "hvac_mode": "fan_only"})
    assert calls[1][0] == ("climate", "set_fan_mode", {"entity_id": "climate.ac1", "fan_mode": "low"})


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_unsupported():
    """Device with idle_action='fan_only' but fan_only NOT in hvac_modes falls back to off."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "off"], "fan_modes": ["low"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    # Falls back to async_turn_off_climate which calls set_hvac_mode off
    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.ac1", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_redundancy():
    """Device already in fan_only with correct fan_mode skips service calls."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "fan_only"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium"], "fan_mode": "low"}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {"entity_id": "climate.ac1", "type": "ac", "role": "auto", "idle_action": "fan_only", "idle_fan_mode": "low"}
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_async_idle_device_fan_only_custom_fan_mode():
    """Custom idle_fan_mode='medium' calls set_fan_mode('medium')."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "medium",
        }
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    fan_mode_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert len(fan_mode_calls) == 1
    assert fan_mode_calls[0][0][2]["fan_mode"] == "medium"


@pytest.mark.asyncio
async def test_async_idle_device_no_device_config():
    """Entity not found in devices[] defaults to 'off' behavior."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get = MagicMock(return_value=state)

    # Empty devices list, entity not found
    await async_idle_device(hass, "climate.unknown", [], area_id="living_room")

    hass.services.async_call.assert_called_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.unknown", "hvac_mode": "off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_async_idle_device_fan_mode_not_in_fan_modes():
    """idle_fan_mode='turbo' not in fan_modes: hvac_mode=fan_only IS set, fan_mode call is SKIPPED."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {"hvac_modes": ["cool", "fan_only", "off"], "fan_modes": ["low", "medium", "high"]}
    hass.states.get = MagicMock(return_value=state)

    devices = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "idle_action": "fan_only",
            "idle_fan_mode": "turbo",
        }
    ]
    await async_idle_device(hass, "climate.ac1", devices, area_id="living_room")

    calls = hass.services.async_call.call_args_list
    # set_hvac_mode(fan_only) should be called
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert len(hvac_calls) == 1
    assert hvac_calls[0][0][2]["hvac_mode"] == "fan_only"
    # set_fan_mode should NOT be called (turbo not supported)
    fan_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert len(fan_calls) == 0


# ---------------------------------------------------------------------------
# async_apply integration tests with fan_only idle_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mpc_apply_idle_respects_fan_only():
    """async_apply(MODE_IDLE) with AC device that has idle_action='fan_only' uses fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low", "medium", "high"],
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    # Override devices with fan_only config
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 23.0)

    calls = hass.services.async_call.call_args_list
    hvac_calls = [c for c in calls if c[0][1] == "set_hvac_mode"]
    assert any(c[0][2].get("hvac_mode") == "fan_only" for c in hvac_calls)
    fan_calls = [c for c in calls if c[0][1] == "set_fan_mode"]
    assert any(c[0][2].get("fan_mode") == "low" for c in fan_calls)
    # No "off" calls
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_idle_forced_on_overrides_fan_only():
    """Device in compressor_forced_on during IDLE runs forced_on logic, NOT fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low"],
        "temperature": 25.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("idle", 23.0, compressor_forced_on={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # forced_on sets temperature, does NOT switch to fan_only
    fan_only_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "fan_only"]
    assert len(fan_only_calls) == 0
    # Verify forced_on DID call set_temperature (positive assertion)
    temp_calls = [c for c in calls if c[0][1] == "set_temperature"]
    assert len(temp_calls) >= 1


@pytest.mark.asyncio
async def test_mpc_apply_heating_forced_off_fan_only():
    """AC with idle_action='fan_only' in compressor_forced_off during HEATING uses fan_only."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {
        "hvac_modes": ["heat", "cool", "fan_only", "off"],
        "fan_modes": ["low", "medium"],
        "temperature": 20.0,
    }
    hass.states.get = MagicMock(return_value=state)

    room = make_room(thermostats=[], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        }
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    await ctrl.async_apply("heating", 21.0, compressor_forced_off={"climate.ac1"})

    calls = hass.services.async_call.call_args_list
    # Should use fan_only instead of off
    fan_only_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "fan_only"]
    assert len(fan_only_calls) >= 1
    off_calls = [c for c in calls if c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"]
    assert len(off_calls) == 0


@pytest.mark.asyncio
async def test_mpc_apply_call_hvac_off_uses_idle_action():
    """Verify _call('set_hvac_mode', hvac_mode='off') delegates to async_idle_device."""
    _last_commands.clear()
    hass = build_hass()
    state = MagicMock()
    state.state = "cool"
    state.attributes = {
        "hvac_modes": ["cool", "fan_only", "off"],
        "fan_modes": ["low"],
        "temperature": 23.0,
    }
    hass.states.get = MagicMock(return_value=state)

    # Room with TRV + AC. During cooling, TRVs get "off" via _call.
    # If the TRV has idle_action=fan_only, it should get fan_only.
    room = make_room(thermostats=["climate.trv1"], acs=["climate.ac1"])
    room["devices"] = [
        {
            "entity_id": "climate.trv1",
            "type": "trv",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "fan_only",
            "idle_fan_mode": "low",
        },
        {
            "entity_id": "climate.ac1",
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "idle_fan_mode": "",
        },
    ]
    model_mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # During cooling, TRVs are set to "off" via _call -> async_idle_device
    await ctrl.async_apply("cooling", 23.0)

    calls = hass.services.async_call.call_args_list
    # TRV should get fan_only (not off) via the _call delegation to async_idle_device
    trv_fan_only = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "fan_only"
    ]
    assert len(trv_fan_only) >= 1
    trv_off = [
        c
        for c in calls
        if c[0][2].get("entity_id") == "climate.trv1"
        and c[0][1] == "set_hvac_mode"
        and c[0][2].get("hvac_mode") == "off"
    ]
    assert len(trv_off) == 0
