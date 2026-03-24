"""Shared helpers and constants for coordinator tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

SAMPLE_ROOM = {
    "area_id": "living_room_abc12345",
    "thermostats": ["climate.living_room"],
    "acs": [],
    "devices": [{"entity_id": "climate.living_room", "type": "trv", "role": "auto", "heating_system_type": ""}],
    "temperature_sensor": "sensor.living_room_temp",
    "humidity_sensor": "sensor.living_room_humidity",
    "climate_mode": "auto",
    "schedules": [{"entity_id": "schedule.living_room_heating"}],
    "schedule_selector_entity": "",
    "comfort_temp": 21.0,
    "eco_temp": 17.0,
    "occupancy_sensors": [],
}

MANAGED_ROOM = {
    **SAMPLE_ROOM,
    "temperature_sensor": "",  # No external sensor -> Managed Mode
}


def _make_store_mock(rooms=None):
    """Create a store mock with proper get_settings and get_thermal_data returns."""
    store = MagicMock()
    store.get_rooms.return_value = rooms or {}
    store.get_settings.return_value = {}
    store.get_thermal_data.return_value = {}
    store.async_save_thermal_data = AsyncMock()
    return store


def make_mock_states_get(
    temp="18.0",
    humidity="55.0",
    schedule_state="on",
    schedule_attrs=None,
    outdoor_temp=None,
    outdoor_temp_entity="sensor.outdoor_temp",
    window_sensors=None,
    selector_state=None,
    selector_entity="input_boolean.schedule_toggle",
    person_states=None,
    extra=None,
    temp_unit=None,
):
    """Create a mock ``hass.states.get`` with configurable return values.

    Parameters
    ----------
    temp:
        Value for ``sensor.living_room_temp``.  Set to ``None`` to return
        ``None`` (entity missing).  ``"unavailable"`` is also supported.
    humidity:
        Value for ``sensor.living_room_humidity``.
    schedule_state:
        State for ``schedule.living_room_heating``.
    schedule_attrs:
        Attributes dict for the schedule entity (default ``{}``).
    outdoor_temp:
        If given, ``outdoor_temp_entity`` will return this value.
    outdoor_temp_entity:
        Entity id for the outdoor sensor (default ``sensor.outdoor_temp``).
    window_sensors:
        Dict mapping ``binary_sensor.*`` entity ids to state strings
        (e.g. ``{"binary_sensor.window1": "on"}``).
    selector_state:
        If given, ``selector_entity`` will return this state string.
    selector_entity:
        Entity id for the schedule selector (default ``input_boolean.schedule_toggle``).
    person_states:
        Dict mapping ``person.*`` entity ids to state strings
        (e.g. ``{"person.kevin": "home"}``).
    extra:
        Dict mapping arbitrary entity ids to ``(state_str, attrs_dict | None)``
        tuples for any entities not covered by the above parameters.
    temp_unit:
        If given (e.g. ``"°F"``), temperature sensor mocks will include
        ``unit_of_measurement`` in their attributes.
    """
    if schedule_attrs is None:
        schedule_attrs = {}
    if window_sensors is None:
        window_sensors = {}
    if person_states is None:
        person_states = {}
    if extra is None:
        extra = {}

    def _temp_attrs():
        return {"unit_of_measurement": temp_unit} if temp_unit else {}

    def _mock(entity_id):
        # Temperature sensor
        if entity_id == "sensor.living_room_temp":
            if temp is None:
                return None
            s = MagicMock()
            s.state = temp
            s.attributes = _temp_attrs()
            return s

        # Humidity sensor
        if entity_id == "sensor.living_room_humidity":
            if humidity is None:
                return None
            s = MagicMock()
            s.state = humidity
            s.attributes = {}
            return s

        # Schedule entity
        if entity_id == "schedule.living_room_heating":
            s = MagicMock()
            s.state = schedule_state
            s.attributes = schedule_attrs
            return s

        # Outdoor temperature
        if outdoor_temp is not None and entity_id == outdoor_temp_entity:
            s = MagicMock()
            s.state = outdoor_temp
            s.attributes = _temp_attrs()
            return s

        # Window / door sensors
        if entity_id in window_sensors:
            s = MagicMock()
            s.state = window_sensors[entity_id]
            return s

        # Schedule selector
        if selector_state is not None and entity_id == selector_entity:
            s = MagicMock()
            s.state = selector_state
            return s

        # Person entities
        if entity_id in person_states:
            s = MagicMock()
            s.state = person_states[entity_id]
            return s

        # Arbitrary extras
        if entity_id in extra:
            val = extra[entity_id]
            s = MagicMock()
            if isinstance(val, tuple):
                s.state = val[0]
                s.attributes = val[1] if val[1] is not None else {}
            else:
                s.state = val
            return s

        return None

    return _mock


def _create_coordinator(hass, mock_config_entry):
    """Create a RoomMindCoordinator with frame.report_usage patched out."""
    from custom_components.roommind.coordinator import RoomMindCoordinator

    with patch("homeassistant.helpers.frame.report_usage"):
        coordinator = RoomMindCoordinator(hass, mock_config_entry)
    return coordinator


def _presence_states_get(*persons_home):
    """Create a mock states.get function with configurable presence.

    Any ``person.*`` entity in *persons_home* will report ``"home"``;
    all other ``person.*`` entities report ``"not_home"``.

    Non-person entities use the standard defaults from
    :func:`make_mock_states_get`.
    """
    home_set = set(persons_home)

    # Build the base mock with standard defaults
    base = make_mock_states_get()

    def _mock(entity_id):
        if entity_id.startswith("person."):
            s = MagicMock()
            s.state = "home" if entity_id in home_set else "not_home"
            return s
        return base(entity_id)

    return _mock
