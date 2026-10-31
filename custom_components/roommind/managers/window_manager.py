"""Window delay state machine for RoomMind."""

from __future__ import annotations

import logging
import time

from ..const import MAX_SENSOR_STALENESS

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = (None, "unavailable", "unknown")

class WindowManager:
    """Manages window open/close delay logic per room."""

    def __init__(self) -> None:
        self._open_since: dict[str, float] = {}
        self._closed_since: dict[str, float] = {}
        self._paused: dict[str, bool] = {}
        self._seen: set[str] = set()
        # Per-sensor dropout tracking: last definitive reading (True = open) and
        # when the current unavailable stretch began.
        self._last_known: dict[str, dict[str, bool]] = {}
        self._unavailable_since: dict[str, dict[str, float]] = {}
        self._pending: set[str] = set()
        self._warned: set[tuple[str, str]] = set()

    def is_paused(self, area_id: str) -> bool:
        """Return True if climate control is paused due to open window."""
        return self._paused.get(area_id, False)

    def is_pending(self, area_id: str) -> bool:
        """Return True while the window state is unresolved (sensors unavailable, no known state yet)."""
        return area_id in self._pending

    def resolve_raw(
        self,
        area_id: str,
        sensor_states: dict[str, str | None],
        missing: frozenset[str] = frozenset(),
    ) -> bool | None:
        """Aggregate sensor states into a raw open flag, tolerating transient dropouts.

        Right after an HA restart sensors are briefly ``unavailable``/``unknown``
        (or have no state object yet).  Such a sensor keeps its last known
        reading; with none known the result is ``None`` (pending) and the caller
        must neither start climate control nor call ``update()``.  After
        ``MAX_SENSOR_STALENESS`` of continuous dropout the sensor counts as
        closed again, so a dead sensor cannot block control forever.

        *missing* lists sensors the caller knows no longer exist (no state and no
        registry entry once HA has finished starting).  They count as closed
        right away instead of waiting out the staleness cap.
        """
        now = time.time()
        last = self._last_known.setdefault(area_id, {})
        since = self._unavailable_since.setdefault(area_id, {})
        for stale in set(last) | set(since):
            if stale not in sensor_states:
                last.pop(stale, None)
                since.pop(stale, None)
                self._warned.discard((area_id, stale))

        any_open = False
        any_pending = False
        for entity_id, state in sensor_states.items():
            if entity_id in missing:
                last.pop(entity_id, None)
                since.pop(entity_id, None)
                if (area_id, entity_id) not in self._warned:
                    self._warned.add((area_id, entity_id))
                    _LOGGER.warning("Window sensor %s does not exist, treating as closed", entity_id)
                continue

            if state not in _UNAVAILABLE_STATES:
                is_open = state == "on"
                last[entity_id] = is_open
                since.pop(entity_id, None)
                self._warned.discard((area_id, entity_id))
                any_open = any_open or is_open
                continue

            started = since.setdefault(entity_id, now)
            if now - started >= MAX_SENSOR_STALENESS:
                if (area_id, entity_id) not in self._warned:
                    self._warned.add((area_id, entity_id))
                    _LOGGER.warning(
                        "Window sensor %s unavailable for over %ds, treating as closed",
                        entity_id,
                        MAX_SENSOR_STALENESS,
                    )
            elif entity_id in last:
                any_open = any_open or last[entity_id]
            else:
                any_pending = True

        if any_open:
            self._pending.discard(area_id)
            return True
        if any_pending:
            self._pending.add(area_id)
            return None
        self._pending.discard(area_id)
        return False

    def update(self, area_id: str, raw_open: bool, open_delay: int, close_delay: int) -> bool:
        """Update window state machine and return effective window_open status.

        Returns True if climate should be paused (window considered open after delay).
        """
        now = time.time()
        was_paused = self._paused.get(area_id, False)
        first_observation = area_id not in self._seen
        self._seen.add(area_id)

        if raw_open:
            self._closed_since.pop(area_id, None)
            if not was_paused:
                if first_observation:
                    # Window already open on first observation (e.g. after HA
                    # restart).  Skip open_delay — the window has been open for
                    # an unknown duration that certainly exceeds any configured
                    # delay.
                    self._paused[area_id] = True
                else:
                    if area_id not in self._open_since:
                        self._open_since[area_id] = now
                    if now - self._open_since[area_id] >= open_delay:
                        self._paused[area_id] = True
        else:
            open_duration = now - self._open_since[area_id] if area_id in self._open_since else 0
            was_in_open_delay = area_id in self._open_since and not was_paused
            self._open_since.pop(area_id, None)

            already_in_close_delay = area_id in self._closed_since
            brief_threshold = open_delay * 0.1
            needs_close_delay = (
                was_paused
                or already_in_close_delay
                or (was_in_open_delay and open_duration >= brief_threshold and close_delay > 0)
            )

            if was_in_open_delay and not needs_close_delay:
                _LOGGER.debug(
                    "[%s] Window closed after brief open (%ds < %ds threshold) -> no close delay",
                    area_id,
                    int(open_duration),
                    int(brief_threshold),
                )

            if needs_close_delay:
                if area_id not in self._closed_since:
                    self._closed_since[area_id] = now
                    if not was_paused:
                        _LOGGER.info(
                            "[%s] Window closed after %ds open (>%ds threshold) -> close delay %ds started",
                            area_id,
                            int(open_duration),
                            int(brief_threshold),
                            close_delay,
                        )
                if now - self._closed_since[area_id] >= close_delay:
                    self._paused[area_id] = False
                    self._closed_since.pop(area_id, None)
                    _LOGGER.info("[%s] Window close delay %ds elapsed -> climate resumed", area_id, close_delay)

        return self._paused.get(area_id, False)

    def in_close_delay(self, area_id: str) -> bool:
        """Return True if window closed after non-brief opening and close_delay is running."""
        return area_id in self._closed_since and not self._paused.get(area_id, False)

    def in_open_delay(self, area_id: str) -> bool:
        """Return True if window is physically open but open_delay has not elapsed."""
        return area_id in self._open_since and not self._paused.get(area_id, False)

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._open_since.pop(area_id, None)
        self._closed_since.pop(area_id, None)
        self._paused.pop(area_id, None)
        self._seen.discard(area_id)
        self._last_known.pop(area_id, None)
        self._unavailable_since.pop(area_id, None)
        self._pending.discard(area_id)
        self._warned = {k for k in self._warned if k[0] != area_id}
