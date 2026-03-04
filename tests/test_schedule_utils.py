"""Tests for schedule_utils.py."""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import MagicMock

from custom_components.roommind.schedule_utils import (
    get_active_schedule_entity,
    make_target_resolver,
    resolve_schedule_index,
    resolve_target_at_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hass(entity_id: str | None = None, state_value: str | None = None):
    """Return a mock hass with optional entity state."""
    hass = MagicMock()
    if entity_id is None:
        hass.states.get.return_value = None
    else:
        mock_state = MagicMock()
        mock_state.state = state_value
        hass.states.get.return_value = mock_state
    return hass


def _make_room(**overrides):
    room = {
        "area_id": "bedroom",
        "schedules": [
            {"entity_id": "schedule.bedroom_weekday"},
            {"entity_id": "schedule.bedroom_weekend"},
        ],
        "schedule_selector_entity": "",
        "comfort_temp": 21.0,
        "eco_temp": 18.0,
    }
    room.update(overrides)
    return room


# ---------------------------------------------------------------------------
# resolve_schedule_index
# ---------------------------------------------------------------------------


class TestResolveScheduleIndex:
    """Tests for resolve_schedule_index."""

    def test_no_schedules_returns_minus_one(self):
        """Empty schedules list returns -1."""
        hass = _make_hass()
        room = _make_room(schedules=[])
        assert resolve_schedule_index(hass, room) == -1

    def test_no_selector_entity_returns_zero(self):
        """Without selector entity, first schedule is selected."""
        hass = _make_hass()
        room = _make_room(schedule_selector_entity="")
        assert resolve_schedule_index(hass, room) == 0

    def test_input_boolean_on_returns_one(self):
        """input_boolean on → index 1."""
        hass = _make_hass("input_boolean.schedule_mode", "on")
        room = _make_room(schedule_selector_entity="input_boolean.schedule_mode")
        assert resolve_schedule_index(hass, room) == 1

    def test_input_boolean_off_returns_zero(self):
        """input_boolean off → index 0."""
        hass = _make_hass("input_boolean.schedule_mode", "off")
        room = _make_room(schedule_selector_entity="input_boolean.schedule_mode")
        assert resolve_schedule_index(hass, room) == 0

    def test_input_number_one_based_to_zero_based(self):
        """input_number value 2 → index 1 (1-based to 0-based)."""
        hass = _make_hass("input_number.schedule_select", "2")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        assert resolve_schedule_index(hass, room) == 1

    def test_input_number_value_one_returns_zero(self):
        """input_number value 1 → index 0."""
        hass = _make_hass("input_number.schedule_select", "1")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        assert resolve_schedule_index(hass, room) == 0

    def test_input_number_out_of_range_returns_minus_one(self):
        """input_number value beyond schedule count → -1."""
        hass = _make_hass("input_number.schedule_select", "10")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        assert resolve_schedule_index(hass, room) == -1

    def test_input_number_zero_returns_minus_one(self):
        """input_number value 0 (1-based) → index -1 (out of range)."""
        hass = _make_hass("input_number.schedule_select", "0")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        assert resolve_schedule_index(hass, room) == -1

    def test_input_number_invalid_value_returns_zero(self):
        """input_number with non-numeric value → fallback 0."""
        hass = _make_hass("input_number.schedule_select", "abc")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        assert resolve_schedule_index(hass, room) == 0

    def test_unavailable_entity_returns_zero(self):
        """Unavailable entity → fallback to first schedule (0)."""
        hass = _make_hass("input_boolean.schedule_mode", "unavailable")
        room = _make_room(schedule_selector_entity="input_boolean.schedule_mode")
        assert resolve_schedule_index(hass, room) == 0

    def test_unknown_entity_returns_zero(self):
        """Unknown entity state → fallback to first schedule (0)."""
        hass = _make_hass("input_boolean.schedule_mode", "unknown")
        room = _make_room(schedule_selector_entity="input_boolean.schedule_mode")
        assert resolve_schedule_index(hass, room) == 0

    def test_missing_entity_returns_zero(self):
        """Entity not found in hass.states → fallback 0."""
        hass = MagicMock()
        hass.states.get.return_value = None
        room = _make_room(schedule_selector_entity="input_boolean.nonexistent")
        assert resolve_schedule_index(hass, room) == 0

    def test_unknown_domain_returns_zero(self):
        """Unrecognized entity domain → fallback 0."""
        hass = _make_hass("sensor.something", "42")
        room = _make_room(schedule_selector_entity="sensor.something")
        assert resolve_schedule_index(hass, room) == 0

    def test_input_number_float_value(self):
        """input_number with float string like '2.0' → index 1."""
        hass = _make_hass("input_number.schedule_select", "2.0")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        assert resolve_schedule_index(hass, room) == 1


# ---------------------------------------------------------------------------
# resolve_target_at_time
# ---------------------------------------------------------------------------


class TestResolveTargetAtTime:
    """Tests for resolve_target_at_time."""

    def test_override_active(self):
        """Active override returns override_temp."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=now + 3600,
            override_temp=25.0,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 25.0

    def test_override_expired(self):
        """Expired override falls through to next priority."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=now - 100,
            override_temp=25.0,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        # No vacation, no blocks → comfort_temp
        assert result == 21.0

    def test_vacation_active(self):
        """Active vacation returns vacation_temp."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=None,
            override_temp=None,
            vacation_until=now + 86400,
            vacation_temp=16.0,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 16.0

    def test_override_beats_vacation(self):
        """Override has higher priority than vacation."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=now + 3600,
            override_temp=25.0,
            vacation_until=now + 86400,
            vacation_temp=16.0,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 25.0

    def test_presence_away_returns_eco(self):
        """presence_away=True returns eco_temp."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks={"monday": []},
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            presence_away=True,
        )
        assert result == 18.0

    def test_no_schedule_blocks_returns_comfort(self):
        """schedule_blocks=None returns comfort_temp."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 21.0

    def test_inside_block_with_temperature(self):
        """Inside a schedule block that has a temperature → returns that temperature."""
        # Create a timestamp that falls on a known day and time
        # Use a Monday at 10:00
        dt = datetime(2025, 1, 6, 10, 0, 0)  # Monday
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": 22.5},
                },
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 22.5

    def test_inside_block_without_temperature(self):
        """Inside a block without temperature data → returns comfort_temp."""
        dt = datetime(2025, 1, 6, 10, 0, 0)  # Monday
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {},
                },
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 21.0

    def test_outside_all_blocks_returns_eco(self):
        """Outside all schedule blocks → returns eco_temp."""
        dt = datetime(2025, 1, 6, 6, 0, 0)  # Monday 06:00 — before any block
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": 22.0},
                },
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 18.0

    def test_day_with_no_blocks_returns_eco(self):
        """Day without any blocks → returns eco_temp."""
        dt = datetime(2025, 1, 7, 10, 0, 0)  # Tuesday
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": 22.0},
                },
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 18.0

    def test_block_with_invalid_temperature(self):
        """Block with non-numeric temperature → falls back to comfort_temp."""
        dt = datetime(2025, 1, 6, 10, 0, 0)  # Monday
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": "not_a_number"},
                },
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 21.0

    def test_vacation_expired_falls_through(self):
        """Expired vacation falls through to schedule."""
        dt = datetime(2025, 1, 6, 10, 0, 0)  # Monday
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": 22.0},
                },
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=ts - 100,  # expired
            vacation_temp=16.0,
            comfort_temp=21.0,
            eco_temp=18.0,
        )
        assert result == 22.0

    def test_presence_away_action_off_returns_none(self):
        """When presence_away_action is 'off' and presence away, returns None."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            presence_away=True,
            presence_away_action="off",
        )
        assert result is None

    def test_presence_away_action_eco_returns_eco(self):
        """When presence_away_action is 'eco' and presence away, returns eco_temp."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            presence_away=True,
            presence_away_action="eco",
        )
        assert result == 18.0

    def test_schedule_off_action_off_returns_none(self):
        """When schedule_off_action is 'off' and outside schedule blocks, returns None."""
        dt = datetime(2025, 1, 6, 23, 0, 0)  # Monday 23:00 - outside blocks
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {"from": "08:00:00", "to": "12:00:00", "data": {"temperature": 22.0}},
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            schedule_off_action="off",
        )
        assert result is None

    def test_schedule_off_action_eco_returns_eco(self):
        """When schedule_off_action is 'eco' (default), returns eco_temp."""
        dt = datetime(2025, 1, 6, 23, 0, 0)  # Monday 23:00 - outside blocks
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {"from": "08:00:00", "to": "12:00:00", "data": {"temperature": 22.0}},
            ],
        }
        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            schedule_off_action="eco",
        )
        assert result == 18.0

    def test_override_beats_presence_away_off(self):
        """Active override takes priority even when presence_away_action is 'off'."""
        now = time.time()
        result = resolve_target_at_time(
            ts=now,
            schedule_blocks=None,
            override_until=now + 3600,
            override_temp=25.0,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            presence_away=True,
            presence_away_action="off",
        )
        assert result == 25.0


class TestMakeTargetResolverOffActions:
    """Tests for off actions in make_target_resolver."""

    def test_resolver_returns_none_for_presence_off(self):
        """Resolver returns None when presence_away_action is 'off' and away."""
        room = {"comfort_temp": 21.0, "eco_temp": 17.0}
        settings = {"presence_away_action": "off"}
        resolver = make_target_resolver(
            None, room, settings, presence_away=True,
        )
        assert resolver(time.time()) is None

    def test_resolver_returns_none_for_schedule_off(self):
        """Resolver returns None when schedule_off_action is 'off' and outside blocks."""
        room = {"comfort_temp": 21.0, "eco_temp": 17.0}
        settings = {"schedule_off_action": "off"}
        resolver = make_target_resolver(
            None, room, settings,
        )
        # No schedule blocks → falls through to eco/off logic
        # Actually with no schedule blocks, it returns comfort_temp (no blocks = comfort)
        # So we need schedule_blocks with no matching block
        dt = datetime(2025, 1, 6, 23, 0, 0)
        ts = dt.timestamp()
        blocks = {"monday": [{"from": "08:00:00", "to": "12:00:00", "data": {"temperature": 22.0}}]}
        resolver2 = make_target_resolver(blocks, room, settings)
        assert resolver2(ts) is None

    def test_resolver_skips_mold_delta_when_none(self):
        """Mold delta is NOT added when base target is None."""
        room = {"comfort_temp": 21.0, "eco_temp": 17.0}
        settings = {"presence_away_action": "off"}
        resolver = make_target_resolver(
            None, room, settings, presence_away=True, mold_prevention_delta=2.0,
        )
        assert resolver(time.time()) is None


# ---------------------------------------------------------------------------
# get_active_schedule_entity
# ---------------------------------------------------------------------------


class TestGetActiveScheduleEntity:
    """Tests for get_active_schedule_entity."""

    def test_returns_entity_for_first_schedule(self):
        """No selector → returns first schedule entity."""
        hass = _make_hass()
        room = _make_room()
        result = get_active_schedule_entity(hass, room)
        assert result == "schedule.bedroom_weekday"

    def test_returns_entity_for_second_schedule(self):
        """input_boolean on → returns second schedule entity."""
        hass = _make_hass("input_boolean.schedule_mode", "on")
        room = _make_room(schedule_selector_entity="input_boolean.schedule_mode")
        result = get_active_schedule_entity(hass, room)
        assert result == "schedule.bedroom_weekend"

    def test_no_schedules_returns_none(self):
        """No schedules → None."""
        hass = _make_hass()
        room = _make_room(schedules=[])
        result = get_active_schedule_entity(hass, room)
        assert result is None

    def test_index_out_of_range_returns_none(self):
        """Out-of-range index → None."""
        hass = _make_hass("input_number.schedule_select", "10")
        room = _make_room(schedule_selector_entity="input_number.schedule_select")
        result = get_active_schedule_entity(hass, room)
        assert result is None

    def test_empty_entity_id_returns_none(self):
        """Schedule with empty entity_id → None."""
        hass = _make_hass()
        room = _make_room(schedules=[{"entity_id": ""}])
        result = get_active_schedule_entity(hass, room)
        assert result is None

    def test_schedule_without_entity_id_returns_none(self):
        """Schedule dict missing entity_id key → None."""
        hass = _make_hass()
        room = _make_room(schedules=[{}])
        result = get_active_schedule_entity(hass, room)
        assert result is None


# ---------------------------------------------------------------------------
# make_target_resolver with mold_prevention_delta
# ---------------------------------------------------------------------------


class TestMakeTargetResolverMoldDelta:
    """Tests for mold_prevention_delta parameter in make_target_resolver."""

    def test_resolver_adds_mold_delta(self):
        """Resolver should add mold_prevention_delta to every resolved target."""
        room = {"comfort_temp": 21.0, "eco_temp": 17.0}
        settings: dict = {}
        resolver = make_target_resolver(
            None, room, settings, mold_prevention_delta=2.0,
        )
        # No schedule → comfort_temp 21 + delta 2 = 23
        assert resolver(time.time()) == 23.0

    def test_resolver_zero_delta_no_change(self):
        """With zero delta, resolver returns base target unchanged."""
        room = {"comfort_temp": 21.0, "eco_temp": 17.0}
        settings: dict = {}
        resolver = make_target_resolver(
            None, room, settings, mold_prevention_delta=0.0,
        )
        assert resolver(time.time()) == 21.0

    def test_resolver_delta_applies_to_all_timestamps(self):
        """Delta should be applied consistently across different timestamps."""
        room = {"comfort_temp": 21.0, "eco_temp": 17.0}
        settings: dict = {}
        resolver = make_target_resolver(
            None, room, settings, mold_prevention_delta=3.0,
        )
        now = time.time()
        # All timestamps should have the delta applied
        assert resolver(now) == 24.0
        assert resolver(now + 300) == 24.0
        assert resolver(now + 3600) == 24.0


class TestFahrenheitBlockConversion:
    """Tests for Fahrenheit temperature handling in schedule resolution."""

    def test_block_temp_converter_converts_fahrenheit_to_celsius(self):
        """resolve_target_at_time applies block_temp_converter to schedule block temps."""
        from datetime import datetime

        dt = datetime(2025, 1, 6, 10, 0, 0)  # Monday 10:00
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    # Block temp stored in Fahrenheit: 71.6°F = 22°C
                    "data": {"temperature": 71.6},
                },
            ],
        }
        # Converter simulates Fahrenheit → Celsius
        converter = lambda v: (v - 32) * 5 / 9  # noqa: E731

        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            block_temp_converter=converter,
        )
        import pytest as _pytest

        assert result == _pytest.approx(22.0, abs=0.1)

    def test_block_temp_converter_not_applied_without_block_temp(self):
        """Converter is not called when block has no temperature data."""
        from datetime import datetime

        dt = datetime(2025, 1, 6, 10, 0, 0)  # Monday 10:00
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {},  # no temperature
                },
            ],
        }
        converter_called = False

        def converter(v):
            nonlocal converter_called
            converter_called = True
            return v

        result = resolve_target_at_time(
            ts=ts,
            schedule_blocks=schedule_blocks,
            override_until=None,
            override_temp=None,
            vacation_until=None,
            vacation_temp=None,
            comfort_temp=21.0,
            eco_temp=18.0,
            block_temp_converter=converter,
        )
        assert result == 21.0  # falls back to comfort_temp
        assert not converter_called

    def test_make_target_resolver_fahrenheit_block_conversion(self):
        """make_target_resolver with Fahrenheit hass converts block temps to Celsius."""
        from datetime import datetime
        from homeassistant.const import UnitOfTemperature

        hass = _make_hass()
        hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        room = _make_room(comfort_temp=21.0, eco_temp=18.0)
        settings: dict = {}

        # Monday 10:00 schedule block with 71.6°F
        dt = datetime(2025, 1, 6, 10, 0, 0)
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": 71.6},  # 71.6°F = 22°C
                },
            ],
        }

        resolver = make_target_resolver(
            schedule_blocks, room, settings, hass=hass,
        )
        import pytest as _pytest

        assert resolver(ts) == _pytest.approx(22.0, abs=0.1)

    def test_make_target_resolver_celsius_no_conversion(self):
        """make_target_resolver with Celsius hass does not alter block temps."""
        from datetime import datetime
        from homeassistant.const import UnitOfTemperature

        hass = _make_hass()
        hass.config.units.temperature_unit = UnitOfTemperature.CELSIUS

        room = _make_room(comfort_temp=21.0, eco_temp=18.0)
        settings: dict = {}

        dt = datetime(2025, 1, 6, 10, 0, 0)
        ts = dt.timestamp()
        schedule_blocks = {
            "monday": [
                {
                    "from": "08:00:00",
                    "to": "12:00:00",
                    "data": {"temperature": 22.5},
                },
            ],
        }

        resolver = make_target_resolver(
            schedule_blocks, room, settings, hass=hass,
        )
        assert resolver(ts) == 22.5
