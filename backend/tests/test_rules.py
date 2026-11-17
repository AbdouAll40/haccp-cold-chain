from datetime import date, datetime, timedelta

from app import rules


def test_fridge_in_range():
    assert rules.temperature_severity(3.0, 0.0, 4.0) is None
    assert rules.temperature_severity(0.0, 0.0, 4.0) is None
    assert rules.temperature_severity(4.0, 0.0, 4.0) is None


def test_fridge_too_warm_warning_then_critical():
    assert rules.temperature_severity(5.0, 0.0, 4.0) == "warning"
    assert rules.temperature_severity(7.5, 0.0, 4.0) == "critical"


def test_fridge_too_cold():
    assert rules.temperature_severity(-1.0, 0.0, 4.0) == "warning"


def test_freezer_has_no_lower_limit():
    assert rules.temperature_severity(-30.0, None, -18.0) is None
    assert rules.temperature_severity(-17.0, None, -18.0) == "warning"
    assert rules.temperature_severity(-12.0, None, -18.0) == "critical"


def test_expiry_status():
    today = date(2026, 11, 17)
    assert rules.expiry_status(date(2026, 11, 16), today) == "expired"
    assert rules.expiry_status(today, today) == "soon"
    assert rules.expiry_status(date(2026, 11, 20), today) == "soon"
    assert rules.expiry_status(date(2026, 11, 21), today) == "ok"


def test_expired_batch_cannot_ship():
    today = date(2026, 11, 17)
    assert rules.can_ship(today, today)
    assert not rules.can_ship(today - timedelta(days=1), today)


def test_silent_sensor():
    now = datetime(2026, 11, 17, 8, 0, 0)
    assert not rules.is_silent(None, now, 5)
    assert not rules.is_silent(now - timedelta(seconds=14), now, 5)
    assert rules.is_silent(now - timedelta(seconds=16), now, 5)
