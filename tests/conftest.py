"""Fixtures for RoomMind tests."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.control.mpc_controller import clear_command_cache
from custom_components.roommind.store import RoomMindStore


@pytest.fixture(autouse=True)
def _set_utc_timezone():
    """Set HA default timezone to UTC so schedule resolution is deterministic."""
    dt_util.set_default_time_zone(datetime.UTC)
    yield
    dt_util.set_default_time_zone(datetime.UTC)


@pytest.fixture(autouse=True)
def _clear_command_cache():
    """Clear the module-level command cache between tests."""
    clear_command_cache()
    yield
    clear_command_cache()


@pytest.fixture
def hass():
    """Return a mocked Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.config.path = MagicMock(side_effect=lambda *p: "/".join(("/config",) + p))
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    return hass


@pytest.fixture
def mock_config_entry():
    """Return a mocked config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {}
    entry.options = {}
    return entry


@pytest.fixture
def store(hass):
    """Return a RoomMindStore with mocked HA storage backend."""
    s = RoomMindStore(hass)
    s._store = AsyncMock()
    s._store.async_load = AsyncMock(return_value=None)
    s._store.async_save = AsyncMock()
    return s
