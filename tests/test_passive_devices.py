"""Tests for passive device observation in the RoomMind coordinator.

Covers:
- _observe_passive_devices: all entity types, modes, power_fraction, edge cases
- EKF integration: passive mode is used when own devices are idle; ignored when own
  devices are actively heating/cooling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import MODE_COOLING, MODE_HEATING, MODE_IDLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store_mock(rooms=None):
    store = MagicMock()
    store.get_rooms.return_value = rooms or {}
    store.get_settings.return_value = {}
    store.get_thermal_data.return_value = {}
    store.async_save_thermal_data = AsyncMock()
    return store


def _create_coordinator(hass, mock_config_entry):
    from custom_components.roommind.coordinator import RoomMindCoordinator
    with patch("homeassistant.helpers.frame.report_usage"):
        return RoomMindCoordinator(hass, mock_config_entry)


def _climate_state(hvac_action: str, hvac_mode: str = "heat_cool") -> MagicMock:
    """Return a mock climate entity state."""
    s = MagicMock()
    s.state = hvac_mode
    s.attributes = {"hvac_action": hvac_action}
    return s


def _binary_state(on: bool) -> MagicMock:
    s = MagicMock()
    s.state = "on" if on else "off"
    s.attributes = {}
    return s


def _unavailable_state() -> MagicMock:
    s = MagicMock()
    s.state = "unavailable"
    s.attributes = {}
    return s


# ---------------------------------------------------------------------------
# Unit tests for _observe_passive_devices
# ---------------------------------------------------------------------------

class TestObservePassiveDevices:
    """Direct unit tests for the _observe_passive_devices method."""

    def _coordinator(self, hass, mock_config_entry):
        return _create_coordinator(hass, mock_config_entry)

    # --- no devices ---

    def test_no_passive_devices_returns_none(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        mode, pf = coord._observe_passive_devices({})
        assert mode is None
        assert pf == 0.0

    def test_empty_passive_devices_list_returns_none(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        mode, pf = coord._observe_passive_devices({"passive_devices": []})
        assert mode is None
        assert pf == 0.0

    # --- climate entity, mode=auto ---

    def test_climate_auto_cooling_action(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("cooling"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(1.0)

    def test_climate_auto_heating_action(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("heating"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.heater", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode == MODE_HEATING
        assert pf == pytest.approx(1.0)

    def test_climate_auto_preheating_action_treated_as_heating(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("preheating"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.heater", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode == MODE_HEATING

    def test_climate_auto_idle_action_returns_none(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("idle"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode is None
        assert pf == 0.0

    def test_climate_auto_off_action_returns_none(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("off"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode is None

    # --- climate entity, explicit mode ---

    def test_climate_explicit_cooling_matches_hvac_action(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("cooling"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "cooling", "power_fraction": 1.0}]
        })
        assert mode == MODE_COOLING

    def test_climate_explicit_cooling_does_not_activate_on_heating_action(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("heating"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "cooling", "power_fraction": 1.0}]
        })
        assert mode is None

    def test_climate_explicit_heating_matches_hvac_action(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("heating"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.heater", "mode": "heating", "power_fraction": 1.0}]
        })
        assert mode == MODE_HEATING

    def test_climate_explicit_heating_does_not_activate_on_cooling_action(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("cooling"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.heater", "mode": "heating", "power_fraction": 1.0}]
        })
        assert mode is None

    # --- binary_sensor / input_boolean ---

    def test_binary_sensor_on_cooling_mode(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_binary_state(True))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "binary_sensor.ac_running", "mode": "cooling", "power_fraction": 1.0}]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(1.0)

    def test_binary_sensor_on_heating_mode(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_binary_state(True))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "binary_sensor.heater_on", "mode": "heating", "power_fraction": 1.0}]
        })
        assert mode == MODE_HEATING

    def test_binary_sensor_off_returns_none(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_binary_state(False))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "binary_sensor.ac_running", "mode": "cooling", "power_fraction": 1.0}]
        })
        assert mode is None
        assert pf == 0.0

    def test_input_boolean_on_cooling_mode(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_binary_state(True))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "input_boolean.ac_active", "mode": "cooling", "power_fraction": 0.5}]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(0.5)

    # --- custom power_fraction ---

    def test_custom_power_fraction_is_returned(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("cooling"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "auto", "power_fraction": 0.3}]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(0.3)

    # --- unavailable / missing entity ---

    def test_unavailable_entity_is_skipped(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_unavailable_state())
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode is None

    def test_missing_entity_is_skipped(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=None)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "climate.ac", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode is None

    def test_empty_entity_id_is_skipped(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)
        hass.states.get = MagicMock(return_value=_climate_state("cooling"))
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [{"entity_id": "", "mode": "auto", "power_fraction": 1.0}]
        })
        assert mode is None

    # --- multiple devices ---

    def test_two_cooling_devices_sum_power_fractions(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)

        def _states(entity_id):
            if entity_id == "climate.ac_room_a":
                return _climate_state("cooling")
            if entity_id == "climate.ac_room_b":
                return _climate_state("cooling")
            return None

        hass.states.get = MagicMock(side_effect=_states)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [
                {"entity_id": "climate.ac_room_a", "mode": "auto", "power_fraction": 1.0},
                {"entity_id": "climate.ac_room_b", "mode": "auto", "power_fraction": 0.2},
            ]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(1.2)

    def test_two_heating_devices_sum_power_fractions(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)

        def _states(entity_id):
            return _binary_state(True)

        hass.states.get = MagicMock(side_effect=_states)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [
                {"entity_id": "binary_sensor.heater_a", "mode": "heating", "power_fraction": 0.6},
                {"entity_id": "binary_sensor.heater_b", "mode": "heating", "power_fraction": 0.4},
            ]
        })
        assert mode == MODE_HEATING
        assert pf == pytest.approx(1.0)

    def test_mixed_cooling_and_heating_dominant_cooling_wins(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)

        def _states(entity_id):
            if entity_id == "climate.ac":
                return _climate_state("cooling")
            if entity_id == "binary_sensor.heater":
                return _binary_state(True)
            return None

        hass.states.get = MagicMock(side_effect=_states)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [
                {"entity_id": "climate.ac",         "mode": "auto",    "power_fraction": 1.0},
                {"entity_id": "binary_sensor.heater", "mode": "heating", "power_fraction": 0.3},
            ]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(1.0)

    def test_mixed_heating_dominant_heating_wins(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)

        def _states(entity_id):
            if entity_id == "binary_sensor.heater":
                return _binary_state(True)
            if entity_id == "climate.ac":
                return _climate_state("cooling")
            return None

        hass.states.get = MagicMock(side_effect=_states)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [
                {"entity_id": "binary_sensor.heater", "mode": "heating", "power_fraction": 0.8},
                {"entity_id": "climate.ac",           "mode": "auto",    "power_fraction": 0.2},
            ]
        })
        assert mode == MODE_HEATING
        assert pf == pytest.approx(0.8)

    def test_one_active_one_inactive_device(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)

        def _states(entity_id):
            if entity_id == "climate.ac_active":
                return _climate_state("cooling")
            if entity_id == "climate.ac_idle":
                return _climate_state("idle")
            return None

        hass.states.get = MagicMock(side_effect=_states)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [
                {"entity_id": "climate.ac_active", "mode": "auto", "power_fraction": 0.7},
                {"entity_id": "climate.ac_idle",   "mode": "auto", "power_fraction": 0.3},
            ]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(0.7)

    def test_unavailable_device_ignored_active_device_used(self, hass, mock_config_entry):
        coord = self._coordinator(hass, mock_config_entry)

        def _states(entity_id):
            if entity_id == "climate.ac_ok":
                return _climate_state("cooling")
            if entity_id == "climate.ac_unavailable":
                return _unavailable_state()
            return None

        hass.states.get = MagicMock(side_effect=_states)
        mode, pf = coord._observe_passive_devices({
            "passive_devices": [
                {"entity_id": "climate.ac_ok",          "mode": "auto", "power_fraction": 1.0},
                {"entity_id": "climate.ac_unavailable", "mode": "auto", "power_fraction": 0.5},
            ]
        })
        assert mode == MODE_COOLING
        assert pf == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# EKF integration tests
# ---------------------------------------------------------------------------

# A minimal room with a temperature sensor and one passive AC device, no own AC.
PASSIVE_ROOM = {
    "area_id": "room_a_abc12345",
    "thermostats": ["climate.room_a_heater"],
    "acs": [],
    "temperature_sensor": "sensor.room_a_temp",
    "climate_mode": "auto",
    "schedules": [],
    "schedule_selector_entity": "",
    "comfort_heat": 21.0,
    "comfort_cool": 25.0,
    "eco_heat": 17.0,
    "eco_cool": 27.0,
    "passive_devices": [
        {"entity_id": "climate.room_b_ac", "mode": "auto", "power_fraction": 1.0},
    ],
}


def _make_room_a_states(thermostat_hvac_action="idle", passive_hvac_action="idle"):
    """Return a states.get mock for PASSIVE_ROOM."""
    def _get(entity_id):
        if entity_id == "sensor.room_a_temp":
            s = MagicMock()
            s.state = "23.0"
            s.attributes = {}
            return s
        if entity_id == "climate.room_a_heater":
            s = MagicMock()
            s.state = "heat_cool"
            s.attributes = {"hvac_action": thermostat_hvac_action, "current_temperature": 23.0}
            return s
        if entity_id == "climate.room_b_ac":
            s = MagicMock()
            s.state = "cool"
            s.attributes = {"hvac_action": passive_hvac_action}
            return s
        return None
    return _get


class TestPassiveDeviceEKFIntegration:
    """Integration tests: verify passive devices feed into EKF accumulator."""

    @pytest.mark.asyncio
    async def test_passive_cooling_active_sets_ekf_mode_to_cooling(
        self, hass, mock_config_entry
    ):
        """When own thermostat is idle and passive AC is cooling, EKF should
        accumulate a 'cooling' update rather than 'idle'."""
        store = _make_store_mock({"room_a_abc12345": PASSIVE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=_make_room_a_states(
                thermostat_hvac_action="idle",
                passive_hvac_action="cooling",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # The EKF accumulator should have recorded a 'cooling' interval,
        # not 'idle' — passive device observation was used.
        acc_mode = coordinator._ekf_training._accumulated_mode.get("room_a_abc12345")
        assert acc_mode == MODE_COOLING

    @pytest.mark.asyncio
    async def test_passive_cooling_inactive_ekf_mode_is_idle(
        self, hass, mock_config_entry
    ):
        """When both own thermostat and passive AC are idle, EKF should see idle."""
        store = _make_store_mock({"room_a_abc12345": PASSIVE_ROOM})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=_make_room_a_states(
                thermostat_hvac_action="idle",
                passive_hvac_action="idle",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        acc_mode = coordinator._ekf_training._accumulated_mode.get("room_a_abc12345")
        assert acc_mode == MODE_IDLE

    @pytest.mark.asyncio
    async def test_own_device_heating_passive_cooling_ignored(
        self, hass, mock_config_entry
    ):
        """When own thermostat is actively heating (temp < target), passive
        cooling signal must NOT override the EKF mode — own device takes priority."""
        store = _make_store_mock({"room_a_abc12345": PASSIVE_ROOM})
        hass.data = {"roommind": {"store": store}}

        def _states(entity_id):
            # Room is cold → coordinator will decide to heat
            if entity_id == "sensor.room_a_temp":
                s = MagicMock(); s.state = "18.0"; s.attributes = {}; return s
            if entity_id == "climate.room_a_heater":
                s = MagicMock(); s.state = "heat_cool"
                s.attributes = {"hvac_action": "heating", "current_temperature": 18.0}
                return s
            if entity_id == "climate.room_b_ac":
                s = MagicMock(); s.state = "cool"
                s.attributes = {"hvac_action": "cooling"}; return s
            return None

        hass.states.get = MagicMock(side_effect=_states)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        # Coordinator chose heating (18°C < 21°C target) → passive cooling ignored
        acc_mode = coordinator._ekf_training._accumulated_mode.get("room_a_abc12345")
        assert acc_mode == MODE_HEATING

    @pytest.mark.asyncio
    async def test_passive_cooling_pf_stored_in_accumulator(
        self, hass, mock_config_entry
    ):
        """The power_fraction from the passive device should be stored
        in the EKF accumulator."""
        room = {
            **PASSIVE_ROOM,
            "passive_devices": [
                {"entity_id": "climate.room_b_ac", "mode": "auto", "power_fraction": 0.4},
            ],
        }
        store = _make_store_mock({"room_a_abc12345": room})
        hass.data = {"roommind": {"store": store}}
        hass.states.get = MagicMock(
            side_effect=_make_room_a_states(
                thermostat_hvac_action="idle",
                passive_hvac_action="cooling",
            )
        )
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        acc_pf = coordinator._ekf_training._accumulated_pf.get("room_a_abc12345")
        assert acc_pf == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_two_passive_cooling_devices_pf_summed(
        self, hass, mock_config_entry
    ):
        """Two simultaneous passive cooling devices should sum their
        power_fractions in the EKF accumulator."""
        room = {
            **PASSIVE_ROOM,
            "passive_devices": [
                {"entity_id": "climate.room_b_ac", "mode": "auto", "power_fraction": 1.0},
                {"entity_id": "climate.room_c_ac", "mode": "auto", "power_fraction": 0.2},
            ],
        }
        store = _make_store_mock({"room_a_abc12345": room})
        hass.data = {"roommind": {"store": store}}

        def _states(entity_id):
            if entity_id == "sensor.room_a_temp":
                s = MagicMock(); s.state = "23.0"; s.attributes = {}; return s
            if entity_id == "climate.room_a_heater":
                s = MagicMock(); s.state = "heat_cool"
                s.attributes = {"hvac_action": "idle", "current_temperature": 23.0}; return s
            if entity_id in ("climate.room_b_ac", "climate.room_c_ac"):
                s = MagicMock(); s.state = "cool"
                s.attributes = {"hvac_action": "cooling"}; return s
            return None

        hass.states.get = MagicMock(side_effect=_states)
        hass.services.async_call = AsyncMock()

        coordinator = _create_coordinator(hass, mock_config_entry)
        await coordinator._async_update_data()

        assert coordinator._ekf_training._accumulated_mode.get("room_a_abc12345") == MODE_COOLING
        assert coordinator._ekf_training._accumulated_pf.get("room_a_abc12345") == pytest.approx(1.2)
