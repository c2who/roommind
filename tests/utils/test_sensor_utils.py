"""Tests for sensor_utils.read_sensor_value."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.roommind.utils.sensor_utils import read_sensor_value


def _make_hass(entity_id: str, state_value: str) -> MagicMock:
    hass = MagicMock()
    mock_state = MagicMock()
    mock_state.state = state_value
    hass.states.get.return_value = mock_state
    return hass


def _make_hass_no_state() -> MagicMock:
    hass = MagicMock()
    hass.states.get.return_value = None
    return hass


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_returns_float_for_valid_state():
    hass = _make_hass("sensor.temp", "21.5")
    assert read_sensor_value(hass, "sensor.temp", "living_room", "temperature") == 21.5


# ---------------------------------------------------------------------------
# None / empty entity_id
# ---------------------------------------------------------------------------


def test_returns_none_for_none_entity():
    hass = MagicMock()
    assert read_sensor_value(hass, None, "living_room", "temperature") is None


def test_returns_none_for_empty_entity():
    hass = MagicMock()
    assert read_sensor_value(hass, "", "living_room", "temperature") is None


# ---------------------------------------------------------------------------
# Unavailable / unknown states
# ---------------------------------------------------------------------------


def test_returns_none_for_unavailable():
    hass = _make_hass("sensor.temp", "unavailable")
    assert read_sensor_value(hass, "sensor.temp", "living_room", "temperature") is None


def test_returns_none_for_unknown():
    hass = _make_hass("sensor.temp", "unknown")
    assert read_sensor_value(hass, "sensor.temp", "living_room", "temperature") is None


# ---------------------------------------------------------------------------
# Missing state object
# ---------------------------------------------------------------------------


def test_returns_none_when_state_is_none():
    hass = _make_hass_no_state()
    assert read_sensor_value(hass, "sensor.temp", "living_room", "temperature") is None


# ---------------------------------------------------------------------------
# ValueError / TypeError (lines 44-51)
# ---------------------------------------------------------------------------


def test_returns_none_for_non_numeric_state():
    hass = _make_hass("sensor.temp", "not_a_number")
    result = read_sensor_value(hass, "sensor.temp", "living_room", "temperature")
    assert result is None


def test_logs_warning_for_non_numeric_state(caplog):
    hass = _make_hass("sensor.temp", "abc")
    with caplog.at_level("WARNING"):
        result = read_sensor_value(hass, "sensor.temp", "living_room", "temperature")
    assert result is None
    assert "living_room" in caplog.text
    assert "temperature" in caplog.text
    assert "abc" in caplog.text


def test_returns_none_for_type_error():
    hass = MagicMock()
    mock_state = MagicMock()
    mock_state.state = None  # float(None) raises TypeError
    hass.states.get.return_value = mock_state
    result = read_sensor_value(hass, "sensor.temp", "living_room", "humidity")
    assert result is None
