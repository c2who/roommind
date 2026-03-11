"""Anomaly detection manager for RoomMind.

Detects when room temperature changes faster than the EKF predicts (e.g. passive
cooling from adjacent rooms being aired) and suppresses the inappropriate control
action to avoid wasted energy and EKF corruption.

State machine per room: Normal → Suppressed → Recovering → Normal.
"""

from __future__ import annotations

import logging
import time

from ..const import (
    ANOMALY_INNOVATION_FLOOR,
    ANOMALY_MIN_CONSECUTIVE,
)

_LOGGER = logging.getLogger(__name__)

_STATE_NORMAL = "normal"
_STATE_SUPPRESSED = "suppressed"
_STATE_RECOVERING = "recovering"


class _RoomAnomalyState:
    """Per-room anomaly tracking state."""

    __slots__ = ("state", "consecutive_count", "suppressed_since", "suppressed_action")

    def __init__(self) -> None:
        self.state: str = _STATE_NORMAL
        self.consecutive_count: int = 0
        self.suppressed_since: float = 0.0
        self.suppressed_action: str | None = None  # "heating" or "cooling"


class AnomalyManager:
    """Manages temperature anomaly detection and heating/cooling suppression."""

    def __init__(self) -> None:
        self._rooms: dict[str, _RoomAnomalyState] = {}

    def _get_state(self, area_id: str) -> _RoomAnomalyState:
        if area_id not in self._rooms:
            self._rooms[area_id] = _RoomAnomalyState()
        return self._rooms[area_id]

    def update(
        self,
        area_id: str,
        innovation: float,
        prediction_std: float,
        confidence: float,
        mpc_active: bool,
        window_open: bool,
        suppress_heating_enabled: bool,
        suppress_cooling_enabled: bool,
        suppression_minutes: int,
    ) -> str | None:
        """Evaluate anomaly state and return suppressed action.

        Returns:
            None — no suppression.
            "heating" — suppress heating (anomalous cold detected).
            "cooling" — suppress cooling (anomalous warm detected).
        """
        rs = self._get_state(area_id)
        now = time.time()

        # Safety guards: disable anomaly detection when unreliable
        if confidence < 0.3 or not mpc_active or window_open:
            self._reset(rs)
            return None

        # If neither direction is enabled, skip
        if not suppress_heating_enabled and not suppress_cooling_enabled:
            self._reset(rs)
            return None

        # Check if currently in suppression
        if rs.state == _STATE_SUPPRESSED:
            elapsed = (now - rs.suppressed_since) / 60.0
            if elapsed >= suppression_minutes:
                _LOGGER.debug(
                    "Room '%s': anomaly suppression expired after %.0f min",
                    area_id,
                    elapsed,
                )
                rs.state = _STATE_RECOVERING
                rs.consecutive_count = 0
                return None
            return rs.suppressed_action

        if rs.state == _STATE_RECOVERING:
            # Allow one cycle of normal operation before re-checking
            rs.state = _STATE_NORMAL
            rs.consecutive_count = 0
            return None

        # Normal state: check for anomaly
        threshold = max(ANOMALY_INNOVATION_FLOOR, 2.5 * prediction_std)

        if abs(innovation) > threshold:
            # Determine direction
            if innovation < 0:
                # Cooled faster than predicted → suppress heating
                if not suppress_heating_enabled:
                    rs.consecutive_count = 0
                    return None
                anomaly_direction = "heating"
            else:
                # Warmed faster than predicted → suppress cooling
                if not suppress_cooling_enabled:
                    rs.consecutive_count = 0
                    return None
                anomaly_direction = "cooling"

            rs.consecutive_count += 1

            if rs.consecutive_count >= ANOMALY_MIN_CONSECUTIVE:
                rs.state = _STATE_SUPPRESSED
                rs.suppressed_since = now
                rs.suppressed_action = anomaly_direction
                _LOGGER.info(
                    "Room '%s': anomaly detected (innovation=%.2f, threshold=%.2f), "
                    "suppressing %s for %d min",
                    area_id,
                    innovation,
                    threshold,
                    anomaly_direction,
                    suppression_minutes,
                )
                return anomaly_direction
        else:
            rs.consecutive_count = 0

        return None

    def is_suppressed(self, area_id: str) -> bool:
        """Return True if the room is currently in anomaly suppression."""
        rs = self._rooms.get(area_id)
        return rs is not None and rs.state == _STATE_SUPPRESSED

    def _reset(self, rs: _RoomAnomalyState) -> None:
        """Reset room state to normal."""
        rs.state = _STATE_NORMAL
        rs.consecutive_count = 0
        rs.suppressed_action = None

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._rooms.pop(area_id, None)
