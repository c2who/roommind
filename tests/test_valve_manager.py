"""Tests for valve_manager.py — valve protection cycling."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.managers.valve_manager import ValveManager


@pytest.fixture
def vm(hass):
    return ValveManager(hass)


# --- property: cycling_eids ---


def test_cycling_eids_empty(vm):
    assert vm.cycling_eids == set()


def test_cycling_eids_returns_set(vm):
    vm._cycling["climate.trv1"] = time.time()
    vm._cycling["climate.trv2"] = time.time()
    assert vm.cycling_eids == {"climate.trv1", "climate.trv2"}


# --- property: actuation_dirty setter ---


def test_actuation_dirty_setter(vm):
    assert vm.actuation_dirty is False
    vm.actuation_dirty = True
    assert vm.actuation_dirty is True
    vm.actuation_dirty = False
    assert vm.actuation_dirty is False


# --- get_actuation_data ---


def test_get_actuation_data_empty(vm):
    assert vm.get_actuation_data() == {}


def test_get_actuation_data_returns_copy(vm):
    vm._last_actuation["climate.trv1"] = 1000.0
    data = vm.get_actuation_data()
    assert data == {"climate.trv1": 1000.0}
    data["climate.trv1"] = 9999.0
    assert vm._last_actuation["climate.trv1"] == 1000.0


# --- async_finish_cycles: exception handling ---


@pytest.mark.asyncio
async def test_finish_cycles_exception_on_turn_off(vm):
    """Exception in async_turn_off_climate is caught and cycle still removed."""
    now = time.time()
    vm._cycling["climate.trv1"] = now - 100  # well past cycle duration

    with patch(
        "custom_components.roommind.managers.valve_manager.async_turn_off_climate",
        new_callable=AsyncMock,
        side_effect=Exception("service unavailable"),
    ):
        await vm.async_finish_cycles()

    assert "climate.trv1" not in vm._cycling
    assert "climate.trv1" in vm._last_actuation
    assert vm.actuation_dirty is True


# --- async_check_and_cycle: exception on disable close ---


@pytest.mark.asyncio
async def test_check_and_cycle_exception_on_disable_close(vm):
    """Exception closing active cycle on disable is caught."""
    vm._cycling["climate.trv1"] = time.time()

    with patch(
        "custom_components.roommind.managers.valve_manager.async_turn_off_climate",
        new_callable=AsyncMock,
        side_effect=Exception("turn off failed"),
    ):
        await vm.async_check_and_cycle(
            rooms={},
            settings={"valve_protection_enabled": False},
        )

    assert vm._cycling == {}


# --- async_check_and_cycle: exception starting cycle ---


@pytest.mark.asyncio
async def test_check_and_cycle_exception_starting_cycle(vm):
    """Exception during cycle start is caught; valve not added to cycling."""
    rooms = {"living": {"thermostats": ["climate.trv1"]}}
    settings = {
        "valve_protection_enabled": True,
        "valve_protection_interval_days": 0,  # always stale
    }

    state = MagicMock()
    state.attributes = {"hvac_modes": ["heat", "off"]}
    vm.hass.states.get = MagicMock(return_value=state)
    vm.hass.services.async_call = AsyncMock(side_effect=Exception("call failed"))

    with patch(
        "custom_components.roommind.managers.valve_manager.celsius_to_ha_temp",
        return_value=30.0,
    ):
        await vm.async_check_and_cycle(rooms, settings)

    assert "climate.trv1" not in vm._cycling


# --- dual-setpoint support (#78) ---


@pytest.mark.asyncio
async def test_cycle_dual_setpoint_trv(vm):
    """TRV with target_temp_low uses dual-setpoint set_temperature call."""
    rooms = {"living": {"thermostats": ["climate.trv1"]}}
    settings = {
        "valve_protection_enabled": True,
        "valve_protection_interval_days": 0,
    }

    state = MagicMock()
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "target_temp_low": 18.0,
        "target_temp_high": 22.0,
        "max_temp": 30.0,
    }
    vm.hass.states.get = MagicMock(return_value=state)
    vm.hass.services.async_call = AsyncMock()

    with patch(
        "custom_components.roommind.managers.valve_manager.celsius_to_ha_temp",
        return_value=30.0,
    ):
        await vm.async_check_and_cycle(rooms, settings)

    calls = vm.hass.services.async_call.call_args_list
    set_temp_call = next(c for c in calls if c[0][1] == "set_temperature")
    data = set_temp_call[0][2]
    assert "target_temp_low" in data
    assert "target_temp_high" in data
    assert "temperature" not in data
    assert data["target_temp_low"] == 30.0
    assert data["target_temp_high"] == 30.0


@pytest.mark.asyncio
async def test_cycle_single_setpoint_trv_unchanged(vm):
    """Standard TRV without target_temp_low uses single-setpoint call."""
    rooms = {"living": {"thermostats": ["climate.trv1"]}}
    settings = {
        "valve_protection_enabled": True,
        "valve_protection_interval_days": 0,
    }

    state = MagicMock()
    state.attributes = {
        "hvac_modes": ["heat", "off"],
        "temperature": 20.0,
        "max_temp": 30.0,
    }
    vm.hass.states.get = MagicMock(return_value=state)
    vm.hass.services.async_call = AsyncMock()

    with patch(
        "custom_components.roommind.managers.valve_manager.celsius_to_ha_temp",
        return_value=30.0,
    ):
        await vm.async_check_and_cycle(rooms, settings)

    calls = vm.hass.services.async_call.call_args_list
    set_temp_call = next(c for c in calls if c[0][1] == "set_temperature")
    data = set_temp_call[0][2]
    assert "temperature" in data
    assert "target_temp_low" not in data
    assert "target_temp_high" not in data
