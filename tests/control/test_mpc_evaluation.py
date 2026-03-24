"""Tests for MPC evaluation: confidence transition, outdoor series, evaluate_mpc safety guards, target resolver, solar series."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
    MPCController,
)
from custom_components.roommind.control.mpc_optimizer import MPCPlan
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager

from .conftest import build_hass, make_room


@pytest.mark.asyncio
async def test_confidence_transition_threshold():
    """pred_std >= 0.5 -> bang-bang, pred_std < 0.5 -> MPC."""
    hass = build_hass()
    room = make_room()
    model_mgr = RoomModelManager()
    model_mgr.update("living_room", 18.5, 5.0, "heating", 5.0)
    model_mgr.update("living_room", 19.0, 5.0, "heating", 5.0)

    # Enough training data for MPC
    model_mgr.get_mode_counts = MagicMock(return_value=(100, 30, 0))
    # Mock a realistic trained model (2 EKF updates give alpha=_ALPHA_MIN which is
    # too low for the optimizer to distinguish heating from idle via T_eq clamping)
    model_mgr.get_model = MagicMock(return_value=RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0))

    # Just above threshold — bang-bang
    model_mgr.get_prediction_std = MagicMock(return_value=0.5)
    ctrl = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = await ctrl.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode == "heating"  # bang-bang also heats when cold
    assert pf == 1.0  # bang-bang: full power

    # Just below threshold — MPC path
    model_mgr.get_prediction_std = MagicMock(return_value=0.49)
    ctrl2 = MPCController(
        hass,
        room,
        model_manager=model_mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode2, pf2 = await ctrl2.async_evaluate(current_temp=17.0, target_temp=21.0)
    assert mode2 == "heating"  # MPC also heats when cold
    assert 0.0 < pf2 <= 1.0


# ---------------------------------------------------------------------------
# T4: _build_outdoor_series unit tests
# ---------------------------------------------------------------------------


class TestBuildOutdoorSeries:
    """Unit tests for MPCController._build_outdoor_series."""

    def test_constant_outdoor_no_forecast(self):
        """Without forecast, returns constant outdoor temp repeated n_blocks times."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(10)
        assert series == [8.0] * 10

    def test_fallback_when_outdoor_temp_none_no_forecast(self):
        """Without forecast and outdoor_temp=None, uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
        from custom_components.roommind.control.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK

        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=None,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(5)
        assert series == [DEFAULT_OUTDOOR_TEMP_FALLBACK] * 5

    def test_forecast_used_when_available(self):
        """With forecast data, series uses forecast temperatures."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"temperature": 6.0},
            {"temperature": 7.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 6.0, 7.0]

    def test_forecast_padded_when_shorter_than_n_blocks(self):
        """Forecast shorter than n_blocks should be padded with last forecast value."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"temperature": 6.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(5)
        assert series == [5.0, 6.0, 6.0, 6.0, 6.0]

    def test_forecast_truncated_when_longer_than_n_blocks(self):
        """Forecast longer than n_blocks should be truncated."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"temperature": 6.0},
            {"temperature": 7.0},
            {"temperature": 8.0},
            {"temperature": 9.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=10.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 6.0, 7.0]

    def test_forecast_missing_temperature_key_uses_outdoor_temp(self):
        """Forecast entries without 'temperature' key fall back to current outdoor_temp."""
        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"temperature": 5.0},
            {"condition": "cloudy"},  # no temperature key
            {"temperature": 7.0},
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=8.0,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series == [5.0, 8.0, 7.0]

    def test_forecast_missing_temp_key_and_outdoor_none_uses_fallback(self):
        """Forecast entry without temp + outdoor_temp=None uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
        from custom_components.roommind.control.mpc_controller import DEFAULT_OUTDOOR_TEMP_FALLBACK

        hass = build_hass()
        room = make_room()
        model_mgr = RoomModelManager()
        forecast = [
            {"condition": "cloudy"},  # no temperature key
        ]
        ctrl = MPCController(
            hass,
            room,
            model_manager=model_mgr,
            outdoor_temp=None,
            outdoor_forecast=forecast,
            settings={},
            has_external_sensor=True,
        )
        series = ctrl._build_outdoor_series(3)
        assert series[0] == DEFAULT_OUTDOOR_TEMP_FALLBACK
        # Padding should also use the fallback
        assert all(v == DEFAULT_OUTDOOR_TEMP_FALLBACK for v in series)


# ---------------------------------------------------------------------------
# _evaluate_mpc edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_mpc_none_inputs():
    """None current_temp or target_temp returns idle."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )
    mode, pf = ctrl._evaluate_mpc(None, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0

    mode, pf = ctrl._evaluate_mpc(20.0, TargetTemps(heat=None, cool=None))
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# _build_outdoor_series (additional)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _evaluate_mpc safety guard
# ---------------------------------------------------------------------------


def test_evaluate_mpc_safety_guard_heating_above_target(monkeypatch):
    """Safety guard overrides heating to idle when temp >= max(near_targets)."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=19.0,
        settings={},
        has_external_sensor=True,
    )
    # Mock optimizer to return HEATING so the safety guard is actually tested
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 >= target=21 → safety guard should override to idle
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_evaluate_mpc_safety_guard_cooling_below_target(monkeypatch):
    """Safety guard overrides cooling to idle when temp <= min(near_targets)."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], thermostats=[], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=30.0,
        settings={},
        has_external_sensor=True,
    )
    # Mock optimizer to return COOLING so the safety guard is tested
    fake_plan = MPCPlan(
        actions=[MODE_COOLING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 <= target=23 → safety guard should override to idle
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_evaluate_mpc_safety_guard_respects_min_run_heating(monkeypatch):
    """Safety guard must NOT override heating when within minimum run window."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 60,  # started 1 min ago (within 30-min window)
    )
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    # current_temp=22 >= target=21 but we're in min-run window → must keep heating
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING


def test_evaluate_mpc_safety_guard_fires_after_min_run_heating(monkeypatch):
    """Safety guard must override heating when minimum run window has elapsed."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=19.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 3660,  # started 61 min ago (past 60-min underfloor window)
    )
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_evaluate_mpc_safety_guard_fires_after_default_min_run_heating(monkeypatch):
    """Safety guard must override heating when default minimum run window has elapsed."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=19.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="",
        mode_on_since=time.time() - 660,  # started 11 min ago (past 10-min default window)
    )
    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 6,
        temperatures=[22.0] * 7,
        power_fractions=[0.8] * 6,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# _predict_idle_drift
# ---------------------------------------------------------------------------


def test_predict_idle_drift_returns_model_prediction():
    """_predict_idle_drift predicts temperature with Q_active=0."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        q_solar=0.3,
        q_residual=0.1,
        shading_factor=0.8,
        q_occupancy=0.5,
    )

    model = mgr.get_model("living_room")
    predicted = ctrl._predict_idle_drift(21.0, 30.0)
    expected = model.predict(
        21.0,
        5.0,
        Q_active=0.0,
        dt_minutes=30.0,
        q_solar=0.3 * 0.8,
        q_residual=0.1,
        q_occupancy=0.5,
    )
    assert predicted == pytest.approx(expected, abs=0.01)


def test_predict_idle_drift_uses_fallback_outdoor_temp():
    """When outdoor_temp is None, uses DEFAULT_OUTDOOR_TEMP_FALLBACK."""
    from custom_components.roommind.control.mpc_controller import (
        DEFAULT_OUTDOOR_TEMP_FALLBACK,
    )

    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=None,
        settings={},
        has_external_sensor=True,
    )

    model = mgr.get_model("living_room")
    predicted = ctrl._predict_idle_drift(21.0, 30.0)
    expected = model.predict(21.0, DEFAULT_OUTDOOR_TEMP_FALLBACK, Q_active=0.0, dt_minutes=30.0)
    assert predicted == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Prediction-aware safety guard
# ---------------------------------------------------------------------------


def test_safety_guard_allows_heating_when_prediction_dips(monkeypatch):
    """Safety guard allows HEATING when idle-drift predicts temp below target."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
    )

    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 24,
        temperatures=[21.0] * 25,
        power_fractions=[0.8] * 24,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )

    # current_temp=21.0 >= target=21.0 → guard entry triggers
    # With outdoor=5, 30-min idle prediction from 21°C dips well below 21 - 0.2
    # → guard should allow heating
    mode, pf = ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=25.0))
    assert mode == MODE_HEATING
    assert pf > 0.0


def test_safety_guard_suppresses_when_prediction_stays_warm(monkeypatch):
    """Safety guard suppresses HEATING when prediction stays above target."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=20.0,
        settings={},
        has_external_sensor=True,
    )

    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 24,
        temperatures=[22.0] * 25,
        power_fractions=[0.8] * 24,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )

    # current_temp=22 >= target=21, outdoor=20 → prediction stays warm → suppress
    mode, pf = ctrl._evaluate_mpc(22.0, TargetTemps(heat=21.0, cool=25.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


def test_safety_guard_adaptive_horizon_underfloor(monkeypatch):
    """Underfloor heating uses guard horizon derived from min_run_blocks.

    On upstream (min_run_minutes=30): max(6, 6) = 6 blocks = 30 min.
    On dev (min_run_minutes=60): max(6, 12) = 12 blocks = 60 min.
    Either way, the prediction-aware guard still allows heating when
    the model predicts a dip.
    """
    hass = build_hass()
    room = make_room(heating_system_type="underfloor")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        heating_system_type="underfloor",
    )

    fake_plan = MPCPlan(
        actions=[MODE_HEATING] * 24,
        temperatures=[21.0] * 25,
        power_fractions=[0.8] * 24,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )

    # At outdoor=5, idle drift from 21°C drops below 21 - 0.2 = 20.8
    # → guard allows heating regardless of horizon length
    mode, pf = ctrl._evaluate_mpc(21.0, TargetTemps(heat=21.0, cool=25.0))
    assert mode == MODE_HEATING


def test_safety_guard_allows_cooling_when_prediction_rises(monkeypatch):
    """Safety guard allows COOLING when idle-drift predicts temp above target."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], thermostats=[], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
        q_solar=0.5,
    )

    fake_plan = MPCPlan(
        actions=[MODE_COOLING] * 24,
        temperatures=[24.0] * 25,
        power_fractions=[0.8] * 24,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )

    # current_temp=24 <= cool_target=24 → guard entry triggers
    # With outdoor=35 and solar=0.5, prediction rises above 24 + 0.2 → allow cooling
    mode, pf = ctrl._evaluate_mpc(24.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_COOLING
    assert pf > 0.0


def test_safety_guard_suppresses_cooling_when_prediction_stays_cool(monkeypatch):
    """Safety guard suppresses COOLING when prediction stays below target."""
    hass = build_hass()
    room = make_room(acs=["climate.ac1"], thermostats=[], climate_mode="cool_only")
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=23.0,
        settings={},
        has_external_sensor=True,
    )

    fake_plan = MPCPlan(
        actions=[MODE_COOLING] * 24,
        temperatures=[23.0] * 25,
        power_fractions=[0.8] * 24,
    )
    monkeypatch.setattr(
        "custom_components.roommind.control.mpc_controller.MPCOptimizer.optimize",
        lambda *a, **kw: fake_plan,
    )

    # current_temp=23 <= cool_target=23, outdoor=23 → prediction stays stable → suppress
    mode, pf = ctrl._evaluate_mpc(23.0, TargetTemps(heat=21.0, cool=23.0))
    assert mode == MODE_IDLE
    assert pf == 0.0


# ---------------------------------------------------------------------------
# _evaluate_mpc without target_resolver
# ---------------------------------------------------------------------------


def test_evaluate_mpc_no_target_resolver():
    """Without target_resolver, uses flat target_series."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        target_resolver=None,
    )
    # Call _evaluate_mpc — room is cold (17 vs target 21) → should heat
    mode, pf = ctrl._evaluate_mpc(17.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING
    # Should also store a last_plan
    assert ctrl.last_plan is not None


def test_evaluate_mpc_with_target_resolver():
    """With target_resolver, builds target_series from resolver calls."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        target_resolver=lambda ts: TargetTemps(heat=21.0, cool=24.0),  # constant resolver
    )
    # Room is cold (17 vs target 21) → should heat
    mode, pf = ctrl._evaluate_mpc(17.0, TargetTemps(heat=21.0, cool=24.0))
    assert mode == MODE_HEATING
    assert ctrl.last_plan is not None


# ---------------------------------------------------------------------------
# _build_solar_series with cloud_series
# ---------------------------------------------------------------------------


def test_build_solar_series_with_cloud():
    """Cloud series is expanded to 5-min blocks and passed to build_solar_series."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        cloud_series=[50.0, 80.0],
        latitude=48.0,
        longitude=11.0,
    )
    series = ctrl._build_solar_series(30)
    assert len(series) == 30
    # All values should be non-negative floats
    assert all(isinstance(v, (int, float)) and v >= 0 for v in series)


def test_build_solar_series_short_cloud_extended():
    """Short cloud series is extended to fill n_blocks."""
    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        cloud_series=[50.0],  # only 1 hour = 12 blocks
        latitude=48.0,
        longitude=11.0,
    )
    series = ctrl._build_solar_series(30)
    assert len(series) == 30


# ---------------------------------------------------------------------------
# _should_early_exit_min_run — strengthened guardrails
# ---------------------------------------------------------------------------


def _make_mpc_ready_ctrl(
    hass,
    room,
    mode_on_since: float,
    heating_system_type: str = "underfloor",
    previous_mode: str = MODE_HEATING,
) -> MPCController:
    """Create an MPCController with a model-ready RoomModelManager."""
    from unittest.mock import MagicMock

    mgr = RoomModelManager()
    # Mock model readiness: low pred_std + enough data
    mgr.get_prediction_std = MagicMock(return_value=0.1)
    mgr.get_mode_counts = MagicMock(return_value=(100, 30, 30))
    # Mock model.predict to return a high value (simulating solar overshoot)
    model = RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0)
    model.predict = MagicMock(return_value=23.0)  # well above typical target
    mgr.get_model = MagicMock(return_value=model)

    return MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=previous_mode,
        heating_system_type=heating_system_type,
        mode_on_since=mode_on_since,
    )


def test_early_exit_blocked_below_50pct_elapsed():
    """Early exit must be blocked when < 50% of min-run has elapsed."""
    hass = build_hass()
    room = make_room()
    # Underfloor: 60 min min-run, 5 min elapsed = 8.3% < 50%
    ctrl = _make_mpc_ready_ctrl(hass, room, mode_on_since=time.time() - 300)
    result = ctrl._should_early_exit_min_run(MODE_HEATING, 22.0, 21.0)
    assert result is False


def test_early_exit_blocked_model_not_ready():
    """Early exit must be blocked when model doesn't have enough data."""
    from unittest.mock import MagicMock

    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    # Model NOT ready: high pred_std
    mgr.get_prediction_std = MagicMock(return_value=0.8)
    mgr.get_mode_counts = MagicMock(return_value=(10, 5, 0))
    model = RCModel(C=1.0, U=0.15, Q_heat=3.0, Q_cool=4.0)
    model.predict = MagicMock(return_value=23.0)
    mgr.get_model = MagicMock(return_value=model)

    # 35 min elapsed (> 50% of 60 min) but model not ready
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 2100,
    )
    result = ctrl._should_early_exit_min_run(MODE_HEATING, 22.0, 21.0)
    assert result is False


def test_early_exit_allowed_above_50pct_model_predicts_comfort():
    """Early exit allowed when >= 50% elapsed AND model predicts overshoot."""
    hass = build_hass()
    room = make_room()
    # Underfloor: 60 min min-run, 35 min elapsed = 58% > 50%
    ctrl = _make_mpc_ready_ctrl(hass, room, mode_on_since=time.time() - 2100)
    # predicted=23.0 vs target=21.0 → margin = 0.15 + 0.01 * 25min = 0.40
    # 23.0 >= 21.0 + 0.40 → should exit
    result = ctrl._should_early_exit_min_run(MODE_HEATING, 22.0, 21.0)
    assert result is True


def test_early_exit_scaled_margin_blocks_marginal_overshoot():
    """Scaled margin must block exit when overshoot is small and remaining time is large."""
    from unittest.mock import MagicMock

    hass = build_hass()
    room = make_room()
    # 31 min elapsed (just past 50% of 60 min), remaining = 29 min
    # margin = 0.15 + 0.01 * 29 = 0.44
    ctrl = _make_mpc_ready_ctrl(hass, room, mode_on_since=time.time() - 1860)
    # Override predict to return a value just above target but below margin
    mgr = ctrl._model_manager
    model = mgr.get_model("living_room")
    model.predict = MagicMock(return_value=21.3)  # 21.3 < 21.0 + 0.44

    result = ctrl._should_early_exit_min_run(MODE_HEATING, 20.5, 21.0)
    assert result is False


def test_early_exit_cooling_mode():
    """Early exit works for cooling mode too."""
    hass = build_hass()
    room = make_room()
    # 35 min elapsed, remaining = 25 min, margin = 0.15 + 0.01 * 25 = 0.40
    ctrl = _make_mpc_ready_ctrl(
        hass,
        room,
        mode_on_since=time.time() - 2100,
        previous_mode=MODE_COOLING,
    )
    # Override predict: predicted=21.0, target=24.0 → 21.0 <= 24.0 - 0.40 → should exit
    mgr = ctrl._model_manager
    model = mgr.get_model("living_room")
    model.predict = MagicMock(return_value=21.0)

    result = ctrl._should_early_exit_min_run(MODE_COOLING, 22.0, 24.0)
    assert result is True


# ---------------------------------------------------------------------------
# Bang-bang 50% elapsed floor
# ---------------------------------------------------------------------------


def test_bangbang_holds_heating_below_50pct_even_above_hysteresis():
    """Bang-bang must keep heating during first 50% of min-run even if temp exceeds hysteresis."""
    from custom_components.roommind.const import BANGBANG_HEAT_HYSTERESIS

    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    # Underfloor: 60 min min-run, 5 min elapsed = 8.3% < 50%
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 300,
    )
    # temp = target + hysteresis + 0.5 → would normally exit, but < 50% elapsed
    heat_target = 21.0
    temp = heat_target + BANGBANG_HEAT_HYSTERESIS + 0.5
    mode = ctrl._evaluate_bangbang(temp, TargetTemps(heat=heat_target, cool=25.0))
    assert mode == MODE_HEATING


def test_bangbang_allows_exit_above_50pct_and_above_hysteresis():
    """Bang-bang allows exit after 50% of min-run when temp exceeds hysteresis."""
    from custom_components.roommind.const import BANGBANG_HEAT_HYSTERESIS

    hass = build_hass()
    room = make_room()
    mgr = RoomModelManager()
    # Underfloor: 60 min min-run, 35 min elapsed = 58% > 50%
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=5.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_HEATING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 2100,
    )
    # temp = target + hysteresis + 0.5 → above hysteresis, past 50% → should exit
    heat_target = 21.0
    temp = heat_target + BANGBANG_HEAT_HYSTERESIS + 0.5
    mode = ctrl._evaluate_bangbang(temp, TargetTemps(heat=heat_target, cool=25.0))
    assert mode == MODE_IDLE


def test_bangbang_holds_cooling_below_50pct():
    """Bang-bang must keep cooling during first 50% of min-run."""
    from custom_components.roommind.const import BANGBANG_COOL_HYSTERESIS

    hass = build_hass()
    room = make_room(acs=["climate.living_ac"], thermostats=[])
    mgr = RoomModelManager()
    ctrl = MPCController(
        hass,
        room,
        model_manager=mgr,
        outdoor_temp=35.0,
        settings={},
        has_external_sensor=True,
        previous_mode=MODE_COOLING,
        heating_system_type="underfloor",
        mode_on_since=time.time() - 300,  # 5 min < 50% of 60 min
    )
    cool_target = 24.0
    temp = cool_target - BANGBANG_COOL_HYSTERESIS - 0.5
    mode = ctrl._evaluate_bangbang(temp, TargetTemps(heat=19.0, cool=cool_target))
    assert mode == MODE_COOLING
