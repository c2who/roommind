"""Window delay state machine for RoomMind."""

from __future__ import annotations

import time


class WindowManager:
    """Manages window open/close delay logic per room."""

    def __init__(self) -> None:
        self._open_since: dict[str, float] = {}
        self._closed_since: dict[str, float] = {}
        self._paused: dict[str, bool] = {}
        self._seen: set[str] = set()

    def is_paused(self, area_id: str) -> bool:
        """Return True if climate control is paused due to open window."""
        return self._paused.get(area_id, False)

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
