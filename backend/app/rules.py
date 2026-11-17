"""HACCP rules as pure functions, so they are easy to unit test."""
from datetime import date, datetime, timedelta

# Default HACCP limits per zone type (°C). None = no lower limit.
LIMITS = {
    "fridge": (0.0, 4.0),
    "cold_room": (0.0, 4.0),
    "truck": (0.0, 4.0),
    "freezer": (None, -18.0),
}

# How far outside the limit a reading must be to count as critical (°C).
CRITICAL_MARGIN = 3.0


def temperature_severity(value: float, min_temp: float | None, max_temp: float) -> str | None:
    """None if the reading is inside the limits, else 'warning' or 'critical'."""
    if min_temp is not None and value < min_temp:
        gap = min_temp - value
    elif value > max_temp:
        gap = value - max_temp
    else:
        return None
    return "critical" if gap >= CRITICAL_MARGIN else "warning"


def in_range(value: float, min_temp: float | None, max_temp: float) -> bool:
    return temperature_severity(value, min_temp, max_temp) is None


def expiry_status(expiry: date, today: date, soon_days: int = 3) -> str:
    """'expired', 'soon' (within soon_days) or 'ok'."""
    if expiry < today:
        return "expired"
    if expiry <= today + timedelta(days=soon_days):
        return "soon"
    return "ok"


def is_silent(last_seen: datetime | None, now: datetime, interval_s: float, factor: float = 3) -> bool:
    """A sensor is silent when no reading arrived for factor x interval seconds."""
    if last_seen is None:
        return False  # never seen yet: not started, not silent
    return (now - last_seen).total_seconds() > interval_s * factor


def can_ship(expiry: date, today: date) -> bool:
    """Expired batches must not be loaded into a delivery."""
    return expiry_status(expiry, today) != "expired"
