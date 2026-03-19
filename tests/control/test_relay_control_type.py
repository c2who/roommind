"""Tests for per-device relay control_type."""

from __future__ import annotations

import pytest

from custom_components.roommind.utils.device_utils import (
    get_control_type,
    legacy_to_devices,
    CONTROL_TYPE_PROPORTIONAL,
    CONTROL_TYPE_RELAY,
)


def test_get_control_type_returns_relay():
    devices = [{"entity_id": "climate.floor", "type": "trv", "control_type": "relay"}]
    assert get_control_type(devices, "climate.floor") == CONTROL_TYPE_RELAY


def test_get_control_type_returns_proportional_default():
    devices = [{"entity_id": "climate.trv", "type": "trv"}]
    assert get_control_type(devices, "climate.trv") == CONTROL_TYPE_PROPORTIONAL


def test_get_control_type_unknown_entity():
    devices = [{"entity_id": "climate.trv", "type": "trv"}]
    assert get_control_type(devices, "climate.unknown") == CONTROL_TYPE_PROPORTIONAL


def test_legacy_to_devices_sets_proportional_default():
    devices = legacy_to_devices(["climate.trv"], ["climate.ac"])
    assert all(d["control_type"] == "proportional" for d in devices)


from unittest.mock import AsyncMock, MagicMock

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import MPCController, _last_commands
from custom_components.roommind.control.thermal_model import RoomModelManager

from .conftest import build_hass, make_room


@pytest.fixture(autouse=True)
def clear_command_cache():
    _last_commands.clear()
    yield
    _last_commands.clear()


@pytest.mark.asyncio
async def test_relay_trv_heating_sends_boost_target():
    """Relay TRV should receive boost target, not proportional setpoint."""
    hass = build_hass()
    room = make_room(
        device_overrides={"climate.living_trv": {"control_type": "relay"}},
    )
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(),
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    targets = TargetTemps(heat=21.0, cool=25.0)
    await ctrl.async_apply(
        "heating", targets, power_fraction=0.5, current_temp=19.0,
        heating_boost_target=30.0,
    )
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [
        c for c in calls
        if c[0][0] == "climate" and c[0][1] == "set_temperature"
    ]
    assert len(set_temp_calls) == 1
    # Relay device should get boost target (30.0), not proportional (24.5)
    assert set_temp_calls[0][0][2]["temperature"] == 30.0


@pytest.mark.asyncio
async def test_proportional_trv_heating_sends_proportional_setpoint():
    """Proportional TRV should still receive proportional setpoint (regression)."""
    hass = build_hass()
    room = make_room()  # default: proportional
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(),
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    targets = TargetTemps(heat=21.0, cool=25.0)
    await ctrl.async_apply(
        "heating", targets, power_fraction=0.5, current_temp=19.0,
        heating_boost_target=30.0,
    )
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [
        c for c in calls
        if c[0][0] == "climate" and c[0][1] == "set_temperature"
    ]
    assert len(set_temp_calls) == 1
    # Proportional: 19.0 + 0.5 * (30.0 - 19.0) = 24.5, floored at target 21.0
    assert set_temp_calls[0][0][2]["temperature"] == 24.5


from custom_components.roommind.managers.heat_source_orchestrator import HeatSourcePlan, DeviceCommand


@pytest.mark.asyncio
async def test_relay_trv_orchestrator_sends_boost_target():
    """Relay TRV via heat source orchestrator should get boost target."""
    hass = build_hass()
    room = make_room(
        device_overrides={"climate.living_trv": {"control_type": "relay"}},
    )
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(),
        outdoor_temp=5.0, settings={}, has_external_sensor=True,
    )
    plan = HeatSourcePlan(
        commands=[
            DeviceCommand(
                entity_id="climate.living_trv",
                role="primary",
                device_type="thermostat",
                active=True,
                power_fraction=0.5,
                reason="test",
            ),
        ],
        active_sources="primary",
        reason="test",
    )
    targets = TargetTemps(heat=21.0, cool=25.0)
    await ctrl.async_apply(
        "heating", targets, current_temp=19.0,
        heating_boost_target=30.0, heat_source_plan=plan,
    )
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [
        c for c in calls
        if c[0][0] == "climate" and c[0][1] == "set_temperature"
    ]
    assert len(set_temp_calls) == 1
    # Relay: boost target, not proportional
    assert set_temp_calls[0][0][2]["temperature"] == 30.0


@pytest.mark.asyncio
async def test_relay_ac_cooling_sends_cool_boost():
    """Relay AC in cooling should receive cool boost target."""
    hass = build_hass()
    room = make_room(
        thermostats=[], acs=["climate.ac"],
        device_overrides={"climate.ac": {"control_type": "relay"}},
    )
    ctrl = MPCController(
        hass, room, model_manager=RoomModelManager(),
        outdoor_temp=35.0, settings={}, has_external_sensor=True,
    )
    targets = TargetTemps(heat=21.0, cool=25.0)
    await ctrl.async_apply(
        "cooling", targets, power_fraction=0.5, current_temp=27.0,
        cooling_boost_target=16.0,
    )
    calls = hass.services.async_call.call_args_list
    set_temp_calls = [
        c for c in calls
        if c[0][0] == "climate" and c[0][1] == "set_temperature"
    ]
    assert len(set_temp_calls) == 1
    # Relay: should get cool boost (16.0), not proportional
    assert set_temp_calls[0][0][2]["temperature"] == 16.0
