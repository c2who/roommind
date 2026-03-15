"""Integration: window/door sensor pause with delays and state transitions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from .conftest import ROOM_LIVING, make_hass_states, setup_room

ROOM_WITH_WINDOW = {
    **ROOM_LIVING,
    "window_sensors": ["binary_sensor.window_living"],
    "window_open_delay": 0,
    "window_close_delay": 0,
}


class TestWindowPause:
    @pytest.mark.asyncio
    async def test_window_open_pauses_heating(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )

        data = await coordinator._async_update_data()

        room = data["rooms"]["living_room"]
        assert room["window_open"] is True
        assert room["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_window_close_resumes_heating(self, coordinator, real_store):
        await setup_room(real_store, ROOM_WITH_WINDOW)

        # First cycle: window open
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data1 = await coordinator._async_update_data()
        assert data1["rooms"]["living_room"]["mode"] == "idle"

        # Second cycle: window closed
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "off"},
            )
        )
        data2 = await coordinator._async_update_data()
        assert data2["rooms"]["living_room"]["mode"] in ("heating", "idle")
        assert data2["rooms"]["living_room"]["window_open"] is False

    @pytest.mark.asyncio
    async def test_window_open_delay_blocks_new_heating(self, coordinator, real_store):
        """With a 60s open delay, window opens and new heating is blocked."""
        room = {**ROOM_WITH_WINDOW, "window_open_delay": 60}
        await setup_room(real_store, room)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )

        data = await coordinator._async_update_data()

        # Window physically open, delay not elapsed, no previous heating → blocked
        assert data["rooms"]["living_room"]["window_open"] is False
        assert data["rooms"]["living_room"]["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_open_delay_continues_existing_heating(self, coordinator, real_store):
        """During open delay, already-running heating continues."""
        room = {**ROOM_WITH_WINDOW, "window_open_delay": 60}
        await setup_room(real_store, room)

        # First cycle: no window open → heating starts
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "off"},
            )
        )
        data1 = await coordinator._async_update_data()
        # Ensure first cycle produces heating (temp 18 < target 21)
        assert data1["rooms"]["living_room"]["mode"] == "heating"

        # Second cycle: window opens during delay → heating continues
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data2 = await coordinator._async_update_data()
        assert data2["rooms"]["living_room"]["window_open"] is False
        assert data2["rooms"]["living_room"]["mode"] == "heating"

    @pytest.mark.asyncio
    async def test_open_delay_blocks_mode_switch(self, coordinator, real_store):
        """During open delay, mode switch (heating→cooling) is blocked."""
        room = {
            **ROOM_WITH_WINDOW,
            "window_open_delay": 60,
            "climate_mode": "auto",
        }
        await setup_room(real_store, room)

        # Seed previous mode as heating
        coordinator._previous_modes["living_room"] = "heating"

        # Window opens during delay, MPC wants cooling (temp above target)
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                temp="25.0",
                climate_hvac_modes=["off", "heat", "cool"],
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data = await coordinator._async_update_data()
        # Mode switch blocked → stays heating (or idle if MPC decided idle)
        assert data["rooms"]["living_room"]["mode"] in ("heating", "idle")

    @pytest.mark.asyncio
    async def test_force_off_overrides_open_delay(self, coordinator, real_store):
        """force_off takes priority over open delay allowing continued heating."""
        room = {**ROOM_WITH_WINDOW, "window_open_delay": 60}
        await setup_room(real_store, room)

        # Seed previous mode as heating
        coordinator._previous_modes["living_room"] = "heating"

        # Schedule off → force_off, window in open delay
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                schedule_state="off",
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data = await coordinator._async_update_data()
        # force_off sets mode=idle before window check, so stays idle
        assert data["rooms"]["living_room"]["mode"] == "idle"

    @pytest.mark.asyncio
    async def test_window_target_temp_unchanged_during_pause(self, coordinator, real_store):
        """Window pause should idle the mode but NOT change the target temp."""
        await setup_room(real_store, ROOM_WITH_WINDOW)

        # Cycle without window open
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "off"},
            )
        )
        data_normal = await coordinator._async_update_data()
        normal_target = data_normal["rooms"]["living_room"]["target_temp"]

        # Cycle with window open
        coordinator.hass.states.get = MagicMock(
            side_effect=make_hass_states(
                extra={"binary_sensor.window_living": "on"},
            )
        )
        data_paused = await coordinator._async_update_data()
        paused_target = data_paused["rooms"]["living_room"]["target_temp"]

        assert normal_target == paused_target == 21.0
