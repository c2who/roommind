"""CSV-based rolling history store for RoomMind analytics."""

from __future__ import annotations

import csv
import logging
import os
import tempfile
import time

_LOGGER = logging.getLogger(__name__)

DETAIL_FIELDS = [
    "timestamp",
    "room_temp",
    "outdoor_temp",
    "target_temp",
    "mode",
    "predicted_temp",
    "window_open",
    "heating_power",
    "solar_irradiance",
    "blind_position",
    "device_setpoint",
    "occupancy",
]
DETAIL_MAX_AGE = 48 * 3600  # 48 hours
HISTORY_MAX_AGE = 90 * 24 * 3600  # 90 days


class HistoryStore:
    """Per-room CSV rolling buffer for analytics data."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir

    def _ensure_dir(self) -> None:
        os.makedirs(self._base_dir, exist_ok=True)

    def _detail_path(self, area_id: str) -> str:
        return os.path.join(self._base_dir, f"{area_id}_detail.csv")

    def _history_path(self, area_id: str) -> str:
        return os.path.join(self._base_dir, f"{area_id}_history.csv")

    def record(self, area_id: str, data: dict, timestamp: float | None = None) -> None:
        """Append a data point to the detail CSV."""
        self._ensure_dir()
        ts = timestamp or time.time()
        path = self._detail_path(area_id)

        file_size_before = os.path.getsize(path) if os.path.isfile(path) else -1

        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
            if f.tell() == 0:
                _LOGGER.warning(
                    "History record '%s': file was empty/new (size_before=%d), writing header",
                    area_id,
                    file_size_before,
                )
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": ts,
                    "room_temp": data.get("room_temp", ""),
                    "outdoor_temp": data.get("outdoor_temp", ""),
                    "target_temp": data.get("target_temp", ""),
                    "mode": data.get("mode", ""),
                    "predicted_temp": data.get("predicted_temp", ""),
                    "window_open": data.get("window_open", ""),
                    "heating_power": data.get("heating_power", ""),
                    "solar_irradiance": data.get("solar_irradiance", ""),
                    "blind_position": data.get("blind_position", ""),
                    "device_setpoint": data.get("device_setpoint", ""),
                    "occupancy": data.get("occupancy", ""),
                }
            )

    def read_detail(
        self,
        area_id: str,
        max_age: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list[dict]:
        """Read detail CSV rows, optionally filtered by age or timestamp range."""
        return self._read_csv(self._detail_path(area_id), max_age, start_ts, end_ts)

    def read_history(
        self,
        area_id: str,
        max_age: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list[dict]:
        """Read history CSV rows."""
        return self._read_csv(self._history_path(area_id), max_age, start_ts, end_ts)

    def _read_csv(
        self,
        path: str,
        max_age: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list[dict]:
        """Read CSV rows with safe timestamp parsing."""
        if not os.path.isfile(path):
            return []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        cutoff_start: float | None = None
        if start_ts is not None:
            cutoff_start = start_ts
        elif max_age is not None:
            cutoff_start = time.time() - max_age
        if cutoff_start is not None or end_ts is not None:
            filtered = []
            for r in rows:
                try:
                    ts = float(r["timestamp"])
                    if cutoff_start is not None and ts < cutoff_start:
                        continue
                    if end_ts is not None and ts > end_ts:
                        continue
                    filtered.append(r)
                except (ValueError, TypeError, KeyError):
                    pass  # skip rows with corrupt timestamps
            rows = filtered
        return rows

    def rotate(self, area_id: str) -> None:
        """Downsample old detail rows to history, trim both files."""
        now = time.time()
        path = self._detail_path(area_id)

        # Snapshot file size before reading for diagnostics
        file_size_before = os.path.getsize(path) if os.path.isfile(path) else 0

        # Read detail, split into keep (< 48h) and archive (>= 48h)
        detail_rows = self.read_detail(area_id)
        cutoff = now - DETAIL_MAX_AGE
        keep = []
        archive = []
        skipped_rows: list[dict] = []
        for r in detail_rows:
            try:
                ts = float(r["timestamp"])
            except (ValueError, TypeError, KeyError):
                skipped_rows.append(r)
                continue
            if ts >= cutoff:
                keep.append(r)
            else:
                archive.append(r)

        # Diagnostic logging to trace data loss
        def _ts_range(rows: list[dict]) -> str:
            if not rows:
                return ""
            first = float(rows[0]["timestamp"])
            last = float(rows[-1]["timestamp"])
            return f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(first))} → {time.strftime('%Y-%m-%d %H:%M', time.gmtime(last))}"

        parts = [
            f"file_size={file_size_before}",
            f"total_rows={len(detail_rows)}",
            f"keep={len(keep)}",
            f"archive={len(archive)}",
            f"skipped={len(skipped_rows)}",
            f"cutoff={time.strftime('%Y-%m-%d %H:%M', time.gmtime(cutoff))}",
        ]
        if keep:
            parts.append(f"keep_range=[{_ts_range(keep)}]")
        if archive:
            parts.append(f"archive_range=[{_ts_range(archive)}]")
        _LOGGER.warning("History rotate '%s': %s", area_id, ", ".join(parts))
        if skipped_rows:
            samples = skipped_rows[:3]
            _LOGGER.warning(
                "History rotate '%s': skipped rows (first %d): %s",
                area_id,
                len(samples),
                samples,
            )

        # Downsample archive to 5-min buckets and append to history
        if archive:
            downsampled = self._downsample(archive, bucket_seconds=300)
            self._append_history(area_id, downsampled)

        # Rewrite detail with only recent rows
        self._rewrite_csv(path, keep)

        # Trim history older than 90 days
        history_rows = self.read_history(area_id)
        history_cutoff = now - HISTORY_MAX_AGE
        trimmed = [r for r in history_rows if self._safe_ts(r) >= history_cutoff]
        if len(trimmed) < len(history_rows):
            self._rewrite_csv(self._history_path(area_id), trimmed)

    def remove_room(self, area_id: str) -> None:
        """Delete all history files for a room."""
        for path in (self._detail_path(area_id), self._history_path(area_id)):
            if os.path.isfile(path):
                os.remove(path)

    def _downsample(self, rows: list[dict], bucket_seconds: int) -> list[dict]:
        """Average rows into time buckets."""
        if not rows:
            return []
        buckets: dict[int, list[dict]] = {}
        for row in rows:
            ts = float(row["timestamp"])
            bucket_key = int(ts // bucket_seconds)
            buckets.setdefault(bucket_key, []).append(row)

        result = []
        for bucket_key in sorted(buckets):
            bucket = buckets[bucket_key]
            avg_row = {
                "timestamp": bucket_key * bucket_seconds,
                "mode": bucket[0]["mode"],
                "window_open": bucket[0].get("window_open", ""),
                "device_setpoint": bucket[0].get("device_setpoint", ""),
            }
            for field in (
                "room_temp",
                "outdoor_temp",
                "target_temp",
                "predicted_temp",
                "heating_power",
                "solar_irradiance",
                "blind_position",
            ):
                vals = []
                for r in bucket:
                    v = r.get(field, "")
                    if v != "":
                        try:
                            vals.append(float(v))
                        except (ValueError, TypeError):
                            pass
                avg_row[field] = round(sum(vals) / len(vals), 2) if vals else ""
            result.append(avg_row)
        return result

    @staticmethod
    def _safe_ts(row: dict) -> float:
        """Return timestamp as float, or 0.0 on failure."""
        try:
            return float(row["timestamp"])
        except (ValueError, TypeError, KeyError):
            return 0.0

    def _append_history(self, area_id: str, rows: list[dict]) -> None:
        self._ensure_dir()
        path = self._history_path(area_id)
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerows(rows)

    def _rewrite_csv(self, path: str, rows: list[dict]) -> None:
        self._ensure_dir()
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
            raise
