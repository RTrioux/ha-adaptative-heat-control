"""Room temperature and presence history, plus sensor discovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

import numpy as np

from .client import Hass, parse_ha_datetime

DEFAULT_HOURS = 24.0
_BAD_STATES = ("", "none", "null", "unavailable", "unknown")


class Sample(NamedTuple):
    """One history sample: point in time (aware datetime) and its value."""

    time: datetime
    value: object


def _raw_history(
    hass: Hass,
    entity_id: str,
    start: Optional[datetime],
    end: Optional[datetime],
    hours: float,
) -> list[tuple[datetime, str]]:
    if start is None and end is None:
        start = datetime.now(timezone.utc) - timedelta(hours=hours or DEFAULT_HOURS)
    history = hass.get_history(entity_id, start=start, end=end)
    states = next((entries for entries in history if entries), [])
    samples: list[tuple[datetime, str]] = []
    for state in states:
        when = parse_ha_datetime(state.get("last_updated") or state.get("last_changed"))
        value = str(state.get("state", "")).strip().lower()
        if when is not None and value not in _BAD_STATES:
            samples.append((when, value))
    samples.sort(key=lambda sample: sample[0])
    return samples


def temperature_history(
    hass: Hass,
    sensor_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    hours: float = DEFAULT_HOURS,
) -> list[Sample]:
    """Temperature history of a sensor: ``(datetime, °C)`` samples, oldest first.

    Args:
        hass: connected :class:`heat_control.Hass` client.
        sensor_id: temperature sensor entity id.
        start / end: window bounds (aware datetimes). When both are None the
            last ``hours`` hours are used.
        hours: window length when ``start`` is not given.
    """
    samples: list[Sample] = []
    for when, value in _raw_history(hass, sensor_id, start, end, hours):
        try:
            samples.append(Sample(when, float(value)))
        except ValueError:
            continue
    return samples


def presence_history(
    hass: Hass,
    sensor_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    hours: float = DEFAULT_HOURS,
) -> list[Sample]:
    """Presence history of a binary sensor: ``(datetime, bool)`` samples.

    True means occupied/on. ``unavailable`` / ``unknown`` states are skipped.
    """
    return [
        Sample(when, value == "on")
        for when, value in _raw_history(hass, sensor_id, start, end, hours)
        if value in ("on", "off")
    ]


def temperature_stats(samples: list[Sample]) -> Optional[dict]:
    """Mean / min / max / last over temperature samples (numpy)."""
    if not samples:
        return None
    values = np.asarray([sample.value for sample in samples], dtype=float)
    return {
        "count": int(values.size),
        "mean": float(values.mean()),
        "min": float(values.min()),
        "max": float(values.max()),
        "last": float(samples[-1].value),
        "first_time": samples[0].time,
        "last_time": samples[-1].time,
        "window_start": samples[0].time,
        "window_end": samples[-1].time,
    }


def presence_stats(samples: list[Sample]) -> Optional[dict]:
    """Occupied time over covered window, estimated from consecutive samples.

    Each sample is assumed to hold until the next one; the last sample holds
    until the end of the covered window.
    """
    if not samples:
        return None
    covered = (samples[-1].time - samples[0].time).total_seconds()
    occupied = 0.0
    for current, following in zip(samples, samples[1:]):
        if current.value:
            occupied += (following.time - current.time).total_seconds()
    if occupied == 0.0 and covered == 0.0 and samples[-1].value:
        occupied = 1.0  # single sample, already occupied
    return {
        "count": len(samples),
        "current": bool(samples[-1].value),
        "current_since": samples[-1].time,
        "window_start": samples[0].time,
        "window_end": samples[-1].time,
        "covered_seconds": covered,
        "occupied_seconds": occupied,
        "occupancy_ratio": (occupied / covered) if covered > 0 else (1.0 if samples[-1].value else 0.0),
    }


def _states(hass: Hass) -> list:
    return list(hass.get_states())


def temperature_sensors(hass: Hass) -> list:
    """All temperature sensors known to Home Assistant."""
    return sorted(
        (
            state
            for state in _states(hass)
            if state.entity_id.startswith("sensor.")
            and (state.attributes or {}).get("device_class") == "temperature"
        ),
        key=lambda state: state.entity_id,
    )


def presence_sensors(hass: Hass) -> list:
    """All occupancy / presence / motion binary sensors."""
    return sorted(
        (
            state
            for state in _states(hass)
            if state.entity_id.startswith("binary_sensor.")
            and (state.attributes or {}).get("device_class") in ("occupancy", "presence", "motion")
        ),
        key=lambda state: state.entity_id,
    )
