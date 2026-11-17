from datetime import date, timedelta

from app.services import handle_message


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_seeded_equipment_and_trucks(client):
    codes = [e["code"] for e in client.get("/equipment").json()]
    assert codes == ["fridge-1", "freezer-1", "coldroom-1"]
    (truck,) = client.get("/trucks").json()
    assert truck["delivery"]["code"] == "DLV-0001"


def test_batches_have_expiry_status(client):
    batches = {b["lot_code"]: b for b in client.get("/batches").json()}
    assert batches["CHK-087"]["status"] == "expired"
    assert batches["FSH-022"]["status"] == "soon"
    assert batches["ICE-203"]["status"] == "ok"
    expired = client.get("/batches", params={"status": "expired"}).json()
    assert [b["lot_code"] for b in expired] == ["CHK-087"]


def test_expired_batch_cannot_be_loaded(client):
    r = client.post("/deliveries/DLV-0001/batches/CHK-087")
    assert r.status_code == 409 and "blocked" in r.json()["detail"]
    r = client.post("/deliveries/DLV-0001/batches/ICE-203")
    assert r.status_code == 200 and r.json()["location"] == "Delivery DLV-0001"


def test_create_batch_validation(client):
    today = date.today()
    body = {"lot_code": "MLK-900", "product": "Milk", "quantity": 10,
            "production_date": today.isoformat(), "expiry_date": (today + timedelta(days=7)).isoformat(),
            "equipment": "fridge-1"}
    assert client.post("/batches", json=body).status_code == 201
    assert client.post("/batches", json=body).status_code == 409  # duplicate lot
    bad = dict(body, lot_code="MLK-901", expiry_date=(today - timedelta(days=1)).isoformat())
    assert client.post("/batches", json=bad).status_code == 422


def test_inspection_compliance(client):
    r = client.post("/inspections", json={"equipment": "fridge-1", "observed_temperature": 6.1,
                                          "inspector": "Abdou"})
    assert r.status_code == 201 and r.json()["compliant"] is False
    r = client.post("/inspections", json={"equipment": "freezer-1", "observed_temperature": -21,
                                          "inspector": "Abdou"})
    assert r.json()["compliant"] is True
    assert len(client.get("/inspections").json()) == 2


def test_alerts_and_resolution(client, db):
    handle_message(db, "coldchain/sensors/fridge-1/temperature",
                   {"zone_id": "fridge-1", "temperature_c": 7.9, "ts": "2026-11-17T08:00:00Z"})
    db.commit()
    (alert,) = client.get("/alerts").json()
    assert alert["kind"] == "temperature" and alert["severity"] == "critical"
    assert client.post(f"/alerts/{alert['id']}/resolve").json()["resolved"] is True
    assert client.get("/alerts").json() == []
    assert len(client.get("/alerts", params={"status": "all"}).json()) == 1


def test_stats(client, db):
    for t in (2.0, 3.0, 6.0):
        handle_message(db, "coldchain/sensors/fridge-1/temperature",
                       {"zone_id": "fridge-1", "temperature_c": t})
    db.commit()
    s = client.get("/stats").json()
    fridge = next(x for x in s["per_source"] if x["source"] == "fridge-1")
    assert fridge["readings"] == 3 and fridge["min"] == 2.0 and fridge["max"] == 6.0
    assert fridge["avg"] == 3.67 and fridge["in_range_pct"] == 66.7
    assert s["batches_by_status"] == {"ok": 4, "soon": 2, "expired": 1}
    assert s["alerts_by_kind_24h"]["temperature"] == 1
    assert s["kpis"]["zones_total"] == 3 and s["kpis"]["open_alerts"] == 1
    assert len(s["alerts_per_hour"]["values"]) == 12
    assert s["alerts_per_hour"]["values"][-1] == 1  # the alert falls in the current hour
    assert s["alerts_per_hour"]["labels"][-1].endswith(":00:00Z")


def test_readings_endpoint(client, db):
    handle_message(db, "coldchain/sensors/fridge-1/temperature", {"zone_id": "fridge-1", "temperature_c": 3.3})
    db.commit()
    pts = client.get("/readings", params={"source": "fridge-1", "minutes": 5}).json()
    assert len(pts) == 1 and pts[0]["temperature"] == 3.3


def test_metrics_endpoint(client):
    r = client.get("/metrics/")
    assert r.status_code == 200 and "coldchain_alerts_total" in r.text
