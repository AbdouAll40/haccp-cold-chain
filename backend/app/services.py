"""Business logic: turning MQTT messages into readings and alerts."""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, metrics, rules
from .influx import influx
from .models import Alert, Batch, Delivery, Equipment, Reading, Truck, utcnow

log = logging.getLogger("coldchain")


def parse_ts(value: str | None) -> datetime:
    """ISO 8601 UTC string -> naive UTC datetime (falls back to now)."""
    if not value:
        return utcnow()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return utcnow()
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------- alerts

def open_alert(db: Session, kind: str, source: str) -> Alert | None:
    return db.scalar(
        select(Alert).where(Alert.kind == kind, Alert.source == source, Alert.resolved.is_(False))
    )


def raise_alert(db: Session, kind: str, severity: str, source: str, message: str,
                value: float | None = None) -> Alert:
    """Create an alert, unless the same one (kind + source) is already open."""
    existing = open_alert(db, kind, source)
    if existing:
        if severity == "critical" and existing.severity != "critical":
            existing.severity = "critical"
            existing.message = message
            existing.value = value
        return existing
    alert = Alert(kind=kind, severity=severity, source=source, message=message, value=value)
    db.add(alert)
    metrics.ALERTS_TOTAL.labels(kind=kind, severity=severity).inc()
    log.warning("ALERT %s/%s %s: %s", kind, severity, source, message)
    return alert


def resolve_alerts(db: Session, kind: str, source: str) -> None:
    alert = open_alert(db, kind, source)
    if alert:
        alert.resolved = True
        alert.resolved_at = utcnow()


def _limits_text(min_temp: float | None, max_temp: float) -> str:
    return f"≤ {max_temp:g} °C" if min_temp is None else f"{min_temp:g} to {max_temp:g} °C"


# ---------------------------------------------------------------- MQTT handlers

def handle_sensor_reading(db: Session, payload: dict) -> None:
    code = payload["zone_id"]
    value = float(payload["temperature_c"])
    ts = parse_ts(payload.get("ts"))

    eq = db.scalar(select(Equipment).where(Equipment.code == code))
    if eq is None:  # unknown zone: register it with the default HACCP limits
        zone_type = payload.get("zone_type", "fridge")
        lo, hi = rules.LIMITS.get(zone_type, rules.LIMITS["fridge"])
        eq = Equipment(code=code, name=code, location="unknown", equipment_type=zone_type,
                       min_temp=lo, max_temp=hi)
        db.add(eq)
        db.flush()

    db.add(Reading(source=code, temperature=value, ts=ts))
    eq.last_temp = value
    eq.last_seen = utcnow()
    resolve_alerts(db, "sensor_silent", code)

    severity = rules.temperature_severity(value, eq.min_temp, eq.max_temp)
    if severity:
        eq.status = "alert"
        raise_alert(db, "temperature", severity, code,
                    f"{eq.name}: {value:.1f} °C, outside HACCP limits ({_limits_text(eq.min_temp, eq.max_temp)})",
                    value)
        _flag_stored_batches(db, eq)
    else:
        eq.status = "ok"
        resolve_alerts(db, "temperature", code)

    metrics.TEMPERATURE.labels(source=code).set(value)
    influx.write_temperature(code, eq.equipment_type, value, ts)


def handle_truck_telemetry(db: Session, payload: dict) -> None:
    code = payload["truck_id"]
    value = float(payload["temperature_c"])
    ts = parse_ts(payload.get("ts"))

    truck = db.scalar(select(Truck).where(Truck.code == code))
    if truck is None:
        truck = Truck(code=code, name=code)
        db.add(truck)
        db.flush()

    truck.lat = float(payload["lat"])
    truck.lon = float(payload["lon"])
    truck.speed_kmh = float(payload.get("speed_kmh") or 0)
    truck.last_temp = value
    truck.last_seen = utcnow()
    db.add(Reading(source=code, temperature=value, ts=ts))
    resolve_alerts(db, "sensor_silent", code)

    severity = rules.temperature_severity(value, truck.min_temp, truck.max_temp)
    delivery = None
    if payload.get("delivery_id"):
        delivery = db.scalar(select(Delivery).where(Delivery.code == payload["delivery_id"]))
    if severity:
        truck.status = "alert"
        flagged = 0
        if delivery:
            for batch in db.scalars(select(Batch).where(Batch.delivery_id == delivery.id)):
                if not batch.cold_chain_breach:
                    batch.cold_chain_breach = True
                    flagged += 1
        where = f" on delivery {delivery.code}" if delivery else ""
        raise_alert(db, "transit_breach", severity, code,
                    f"{truck.name}{where}: cargo at {value:.1f} °C, outside 0 to 4 °C"
                    + (f"; {flagged} batch(es) flagged" if flagged else ""),
                    value)
    else:
        truck.status = "ok"
        resolve_alerts(db, "transit_breach", code)

    metrics.TEMPERATURE.labels(source=code).set(value)
    influx.write_truck(code, value, truck.speed_kmh, truck.lat, truck.lon, ts)


def handle_status(db: Session, kind: str, code: str, payload: dict) -> None:
    """kind is 'sensors' or 'trucks'. 'offline' comes from the MQTT last will."""
    model = Equipment if kind == "sensors" else Truck
    obj = db.scalar(select(model).where(model.code == code))
    if obj is None:
        return
    if payload.get("status") == "offline":
        obj.status = "offline"
        raise_alert(db, "sensor_silent", "critical", code,
                    f"{obj.name} disconnected (MQTT last will received)")
    elif payload.get("status") == "online":
        resolve_alerts(db, "sensor_silent", code)


def handle_message(db: Session, topic: str, payload: dict) -> None:
    """Route one MQTT message (topics from docs/mqtt.md)."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "coldchain":
        return
    _, kind, code, leaf = parts
    if kind == "sensors" and leaf == "temperature":
        handle_sensor_reading(db, payload)
    elif kind == "trucks" and leaf == "telemetry":
        handle_truck_telemetry(db, payload)
    elif leaf == "status" and kind in ("sensors", "trucks"):
        handle_status(db, kind, code, payload)
    metrics.MQTT_MESSAGES.labels(kind=kind).inc()


def _flag_stored_batches(db: Session, eq: Equipment) -> None:
    for batch in db.scalars(select(Batch).where(Batch.equipment_id == eq.id)):
        batch.cold_chain_breach = True


# ---------------------------------------------------------------- periodic checks

def run_periodic_checks(db: Session, now: datetime | None = None, today: date | None = None) -> None:
    now = now or utcnow()
    today = today or date.today()

    # 1. silent sensors and trucks
    for model in (Equipment, Truck):
        for obj in db.scalars(select(model)):
            if rules.is_silent(obj.last_seen, now, config.SENSOR_INTERVAL, config.SILENT_FACTOR):
                obj.status = "offline"
                seconds = int((now - obj.last_seen).total_seconds())
                raise_alert(db, "sensor_silent", "critical", obj.code,
                            f"{obj.name}: no reading for {seconds} s")

    # 2. expiry of batches still in stock
    for batch in db.scalars(select(Batch)):
        status = rules.expiry_status(batch.expiry_date, today, config.EXPIRY_SOON_DAYS)
        if status == "expired":
            raise_alert(db, "expiry", "critical", batch.lot_code,
                        f"{batch.product.name} lot {batch.lot_code} expired on {batch.expiry_date}")
        elif status == "soon":
            raise_alert(db, "expiry", "warning", batch.lot_code,
                        f"{batch.product.name} lot {batch.lot_code} expires on {batch.expiry_date}")
        else:
            resolve_alerts(db, "expiry", batch.lot_code)

    # 3. keep the readings table small
    cutoff = now - timedelta(hours=config.READINGS_RETENTION_HOURS)
    db.query(Reading).filter(Reading.ts < cutoff).delete()
