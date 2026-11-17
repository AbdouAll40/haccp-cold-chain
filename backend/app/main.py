"""HACCP Cold Chain API."""
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import config, rules, worker
from .db import Base, SessionLocal, engine, get_db
from .models import Alert, Batch, Delivery, Equipment, Inspection, Product, Reading, Truck, utcnow
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if config.SEED_DEMO_DATA:
        with SessionLocal() as db:
            seed(db)
    if config.MQTT_ENABLED:
        app.state.mqtt = worker.start_mqtt()
        worker.start_checks()
    yield
    worker.stop()
    if getattr(app.state, "mqtt", None):
        app.state.mqtt.loop_stop()
        app.state.mqtt.disconnect()


app = FastAPI(title="HACCP Cold Chain API", version="1.0.0", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


# ---------------------------------------------------------------- serializers

def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def equipment_out(e: Equipment) -> dict:
    return {"code": e.code, "name": e.name, "location": e.location, "type": e.equipment_type,
            "min_temp": e.min_temp, "max_temp": e.max_temp, "status": e.status,
            "last_temp": e.last_temp, "last_seen": _iso(e.last_seen)}


def batch_out(b: Batch, today: date) -> dict:
    return {"lot_code": b.lot_code, "product": b.product.name, "category": b.product.category,
            "quantity": b.quantity, "production_date": b.production_date.isoformat(),
            "expiry_date": b.expiry_date.isoformat(),
            "days_left": (b.expiry_date - today).days,
            "status": rules.expiry_status(b.expiry_date, today, config.EXPIRY_SOON_DAYS),
            "cold_chain_breach": b.cold_chain_breach,
            "location": b.equipment.name if b.equipment else (f"Delivery {b.delivery.code}" if b.delivery else "-")}


def alert_out(a: Alert) -> dict:
    return {"id": a.id, "kind": a.kind, "severity": a.severity, "source": a.source,
            "message": a.message, "value": a.value, "created_at": _iso(a.created_at),
            "resolved": a.resolved, "resolved_at": _iso(a.resolved_at)}


# ---------------------------------------------------------------- health

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "mqtt_connected": worker.state["mqtt_connected"] if config.MQTT_ENABLED else None}


# ---------------------------------------------------------------- equipment, trucks, readings

@app.get("/equipment")
def list_equipment(db: Session = Depends(get_db)):
    return [equipment_out(e) for e in db.scalars(select(Equipment).order_by(Equipment.id))]


@app.get("/trucks")
def list_trucks(db: Session = Depends(get_db)):
    out = []
    for t in db.scalars(select(Truck).order_by(Truck.id)):
        delivery = db.scalar(select(Delivery).where(Delivery.truck_id == t.id, Delivery.status == "in_transit"))
        out.append({"code": t.code, "name": t.name, "status": t.status, "lat": t.lat, "lon": t.lon,
                    "speed_kmh": t.speed_kmh, "last_temp": t.last_temp, "last_seen": _iso(t.last_seen),
                    "min_temp": t.min_temp, "max_temp": t.max_temp,
                    "delivery": None if delivery is None else {
                        "code": delivery.code, "origin": delivery.origin, "destination": delivery.destination}})
    return out


@app.get("/deliveries")
def list_deliveries(db: Session = Depends(get_db)):
    today = date.today()
    out = []
    for d in db.scalars(select(Delivery).order_by(Delivery.id)):
        batches = db.scalars(select(Batch).where(Batch.delivery_id == d.id)).all()
        out.append({"code": d.code, "truck": d.truck.code, "origin": d.origin, "destination": d.destination,
                    "status": d.status, "batches": [batch_out(b, today) for b in batches]})
    return out


@app.get("/readings")
def readings(source: str, minutes: int = Query(30, ge=1, le=24 * 60), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(minutes=minutes)
    rows = db.execute(select(Reading.ts, Reading.temperature)
                      .where(Reading.source == source, Reading.ts >= since).order_by(Reading.ts)).all()
    return [{"ts": _iso(ts), "temperature": t} for ts, t in rows]


# ---------------------------------------------------------------- products and batches

@app.get("/products")
def list_products(db: Session = Depends(get_db)):
    return [{"id": p.id, "name": p.name, "category": p.category, "storage_type": p.storage_type}
            for p in db.scalars(select(Product).order_by(Product.name))]


@app.get("/batches")
def list_batches(status: str | None = Query(None, pattern="^(ok|soon|expired)$"), db: Session = Depends(get_db)):
    today = date.today()
    items = [batch_out(b, today) for b in db.scalars(select(Batch).order_by(Batch.expiry_date))]
    return [b for b in items if status is None or b["status"] == status]


class BatchIn(BaseModel):
    lot_code: str = Field(min_length=1, max_length=50)
    product: str
    quantity: int = Field(gt=0)
    production_date: date
    expiry_date: date
    equipment: str | None = None  # equipment code


@app.post("/batches", status_code=201)
def create_batch(body: BatchIn, db: Session = Depends(get_db)):
    if body.expiry_date < body.production_date:
        raise HTTPException(422, "expiry_date is before production_date")
    product = db.scalar(select(Product).where(Product.name == body.product))
    if product is None:
        raise HTTPException(404, f"unknown product {body.product}")
    if db.scalar(select(Batch).where(Batch.lot_code == body.lot_code)):
        raise HTTPException(409, f"lot {body.lot_code} already exists")
    eq = None
    if body.equipment:
        eq = db.scalar(select(Equipment).where(Equipment.code == body.equipment))
        if eq is None:
            raise HTTPException(404, f"unknown equipment {body.equipment}")
    b = Batch(lot_code=body.lot_code, product_id=product.id, quantity=body.quantity,
              production_date=body.production_date, expiry_date=body.expiry_date,
              equipment_id=eq.id if eq else None)
    db.add(b)
    db.commit()
    return batch_out(b, date.today())


@app.post("/deliveries/{code}/batches/{lot_code}")
def load_batch(code: str, lot_code: str, db: Session = Depends(get_db)):
    """Load a batch into a delivery. HACCP rule: expired batches cannot be shipped."""
    delivery = db.scalar(select(Delivery).where(Delivery.code == code))
    batch = db.scalar(select(Batch).where(Batch.lot_code == lot_code))
    if delivery is None or batch is None:
        raise HTTPException(404, "unknown delivery or batch")
    today = date.today()
    if not rules.can_ship(batch.expiry_date, today):
        raise HTTPException(409, f"lot {lot_code} expired on {batch.expiry_date}: shipping is blocked")
    batch.delivery_id = delivery.id
    batch.equipment_id = None
    db.commit()
    return batch_out(batch, today)


# ---------------------------------------------------------------- alerts

@app.get("/alerts")
def list_alerts(status: str = Query("open", pattern="^(open|resolved|all)$"),
                limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status == "open":
        q = q.where(Alert.resolved.is_(False))
    elif status == "resolved":
        q = q.where(Alert.resolved.is_(True))
    return [alert_out(a) for a in db.scalars(q)]


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "alert not found")
    if not a.resolved:
        a.resolved = True
        a.resolved_at = utcnow()
        db.commit()
    return alert_out(a)


# ---------------------------------------------------------------- inspections

class InspectionIn(BaseModel):
    equipment: str
    observed_temperature: float
    inspector: str = Field(min_length=1, max_length=100)
    notes: str = Field("", max_length=500)
    inspection_date: date | None = None


def inspection_out(i: Inspection) -> dict:
    return {"id": i.id, "equipment": i.equipment.code, "inspection_date": i.inspection_date.isoformat(),
            "observed_temperature": i.observed_temperature, "compliant": i.compliant,
            "inspector": i.inspector, "notes": i.notes}


@app.get("/inspections")
def list_inspections(db: Session = Depends(get_db)):
    return [inspection_out(i) for i in db.scalars(select(Inspection).order_by(Inspection.id.desc()))]


@app.post("/inspections", status_code=201)
def create_inspection(body: InspectionIn, db: Session = Depends(get_db)):
    eq = db.scalar(select(Equipment).where(Equipment.code == body.equipment))
    if eq is None:
        raise HTTPException(404, f"unknown equipment {body.equipment}")
    i = Inspection(equipment_id=eq.id, inspection_date=body.inspection_date or date.today(),
                   observed_temperature=body.observed_temperature,
                   compliant=rules.in_range(body.observed_temperature, eq.min_temp, eq.max_temp),
                   inspector=body.inspector, notes=body.notes)
    db.add(i)
    db.commit()
    return inspection_out(i)


# ---------------------------------------------------------------- statistics

@app.get("/stats")
def stats(hours: float = Query(1, gt=0, le=48), db: Session = Depends(get_db)):
    now = utcnow()
    since = now - timedelta(hours=hours)
    today = date.today()

    sources = [(e.code, e.name, e.min_temp, e.max_temp) for e in db.scalars(select(Equipment))]
    sources += [(t.code, t.name, t.min_temp, t.max_temp) for t in db.scalars(select(Truck))]
    per_source = []
    for code, name, lo, hi in sources:
        base = select(func.count(), func.min(Reading.temperature), func.max(Reading.temperature),
                      func.avg(Reading.temperature)).where(Reading.source == code, Reading.ts >= since)
        count, tmin, tmax, tavg = db.execute(base).one()
        in_range_q = select(func.count()).where(Reading.source == code, Reading.ts >= since,
                                                Reading.temperature <= hi)
        if lo is not None:
            in_range_q = in_range_q.where(Reading.temperature >= lo)
        ok = db.scalar(in_range_q) or 0
        per_source.append({
            "source": code, "name": name, "min_limit": lo, "max_limit": hi, "readings": count,
            "min": None if tmin is None else round(tmin, 2), "max": None if tmax is None else round(tmax, 2),
            "avg": None if tavg is None else round(float(tavg), 2),
            "in_range_pct": None if not count else round(100 * ok / count, 1),
        })

    alerts_24h = db.scalars(select(Alert).where(Alert.created_at >= now - timedelta(hours=24))).all()
    by_kind = {k: 0 for k in ("temperature", "transit_breach", "sensor_silent", "expiry")}
    # 12 clock-hour buckets ending with the current hour; the browser shows them in local time
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    hour_starts = [current_hour - timedelta(hours=11 - i) for i in range(12)]
    per_hour = [0] * 12
    for a in alerts_24h:
        by_kind[a.kind] = by_kind.get(a.kind, 0) + 1
        idx = 11 - int((current_hour - a.created_at.replace(minute=0, second=0, microsecond=0))
                       .total_seconds() // 3600)
        if 0 <= idx < 12:
            per_hour[idx] += 1
    hour_labels = [_iso(h) for h in hour_starts]

    batches = db.scalars(select(Batch)).all()
    by_status = {"ok": 0, "soon": 0, "expired": 0}
    for b in batches:
        by_status[rules.expiry_status(b.expiry_date, today, config.EXPIRY_SOON_DAYS)] += 1

    equipment = db.scalars(select(Equipment)).all()
    trucks = db.scalars(select(Truck)).all()
    open_alerts = db.scalar(select(func.count()).select_from(Alert).where(Alert.resolved.is_(False))) or 0
    critical_open = db.scalar(select(func.count()).select_from(Alert)
                              .where(Alert.resolved.is_(False), Alert.severity == "critical")) or 0
    return {
        "window_hours": hours,
        "kpis": {
            "zones_total": len(equipment),
            "zones_ok": sum(1 for e in equipment if e.status == "ok"),
            "trucks_on_route": sum(1 for t in trucks if t.status in ("ok", "alert")),
            "open_alerts": open_alerts,
            "critical_alerts": critical_open,
            "batches_total": len(batches),
            "batches_expiring_soon": by_status["soon"],
            "batches_expired": by_status["expired"],
            "batches_breach": sum(1 for b in batches if b.cold_chain_breach),
        },
        "per_source": per_source,
        "alerts_by_kind_24h": by_kind,
        "alerts_per_hour": {"labels": hour_labels, "values": per_hour},
        "batches_by_status": by_status,
    }
