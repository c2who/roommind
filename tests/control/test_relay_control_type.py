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
