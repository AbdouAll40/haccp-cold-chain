from datetime import date, timedelta

from sqlalchemy import select

from app.models import Alert, Batch, Equipment, Reading, Truck, utcnow
from app.services import handle_message, run_periodic_checks


def reading(zone="fridge-1", temp=3.0, zone_type="fridge"):
    return f"coldchain/sensors/{zone}/temperature", {
        "sensor_id": f"sensor-{zone}", "zone_id": zone, "zone_type": zone_type,
        "temperature_c": temp, "ts": "2026-11-17T08:00:00Z"}


def open_alerts(db, kind=None):
    q = select(Alert).where(Alert.resolved.is_(False))
    if kind:
        q = q.where(Alert.kind == kind)
    return db.scalars(q).all()


def test_reading_in_range_updates_equipment(db):
    handle_message(db, *reading(temp=3.2))
    db.commit()
    eq = db.scalar(select(Equipment).where(Equipment.code == "fridge-1"))
    assert eq.status == "ok" and eq.last_temp == 3.2
    assert db.scalar(select(Reading).where(Reading.source == "fridge-1")).temperature == 3.2
    assert open_alerts(db) == []


def test_out_of_range_raises_one_alert_and_resolves(db):
    handle_message(db, *reading(temp=6.0))
    handle_message(db, *reading(temp=6.5))  # same problem: no duplicate alert
    db.commit()
    alerts = open_alerts(db, "temperature")
    assert len(alerts) == 1 and alerts[0].source == "fridge-1"
    # batches stored in that fridge are flagged
    assert all(b.cold_chain_breach for b in db.scalars(select(Batch).where(Batch.lot_code.in_(["MLK-001", "YOG-014"]))))
    handle_message(db, *reading(temp=3.0))
    db.commit()
    assert open_alerts(db, "temperature") == []


def test_alert_escalates_to_critical(db):
    handle_message(db, *reading(temp=5.0))
    handle_message(db, *reading(temp=9.0))
    db.commit()
    (alert,) = open_alerts(db, "temperature")
    assert alert.severity == "critical"


def test_unknown_zone_is_registered_with_default_limits(db):
    handle_message(db, *reading(zone="freezer-9", temp=-20.0, zone_type="freezer"))
    db.commit()
    eq = db.scalar(select(Equipment).where(Equipment.code == "freezer-9"))
    assert eq.max_temp == -18.0 and eq.min_temp is None and eq.status == "ok"


def test_truck_breach_flags_delivery_batches(db):
    handle_message(db, "coldchain/trucks/truck-1/telemetry", {
        "truck_id": "truck-1", "delivery_id": "DLV-0001", "lat": 35.5, "lon": 6.9,
        "speed_kmh": 70, "temperature_c": 8.0, "ts": "2026-11-17T08:00:00Z"})
    db.commit()
    truck = db.scalar(select(Truck).where(Truck.code == "truck-1"))
    assert truck.status == "alert" and truck.lat == 35.5
    (alert,) = open_alerts(db, "transit_breach")
    assert "DLV-0001" in alert.message and "2 batch" in alert.message
    flagged = db.scalars(select(Batch).where(Batch.cold_chain_breach.is_(True))).all()
    assert {b.lot_code for b in flagged} == {"YOG-015", "MLK-002"}


def test_last_will_offline_raises_alert(db):
    handle_message(db, "coldchain/sensors/freezer-1/status", {"status": "offline"})
    db.commit()
    (alert,) = open_alerts(db, "sensor_silent")
    assert alert.source == "freezer-1" and alert.severity == "critical"
    handle_message(db, "coldchain/sensors/freezer-1/status", {"status": "online"})
    db.commit()
    assert open_alerts(db, "sensor_silent") == []


def test_periodic_checks_silent_sensor_and_expiry(db):
    eq = db.scalar(select(Equipment).where(Equipment.code == "coldroom-1"))
    eq.last_seen = utcnow() - timedelta(minutes=5)
    db.commit()
    run_periodic_checks(db, today=date.today())
    db.commit()
    silent = open_alerts(db, "sensor_silent")
    assert [a.source for a in silent] == ["coldroom-1"]
    expiry = {a.source: a.severity for a in open_alerts(db, "expiry")}
    assert expiry["CHK-087"] == "critical"  # expired yesterday
    assert expiry["FSH-022"] == "warning"   # expires tomorrow
    assert "ICE-203" not in expiry          # expires in 60 days


def test_bad_topic_is_ignored(db):
    handle_message(db, "other/topic", {"x": 1})
    handle_message(db, "coldchain/sensors/fridge-1/humidity", {"x": 1})
    db.commit()
    assert db.scalar(select(Reading).limit(1)) is None
