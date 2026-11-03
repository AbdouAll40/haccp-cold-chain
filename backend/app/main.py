"""Backend API skeleton (Member 1).

TODO (see GitHub issues):
- MQTT ingestion -> InfluxDB
- Alert rules (temperature range, sensor silent, expiry)
- CRUD products / batches, trucks, alerts
"""
from fastapi import FastAPI

app = FastAPI(title="HACCP Cold Chain API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
