# MQTT topics and message format

This is the contract between the simulators, the backend and the dashboard.
Change it only through a pull request that all three members approve.

## General rules

- Broker: `mosquitto:1883` inside Docker, `localhost:1883` from your machine.
- All topics start with `coldchain/`.
- Payloads are JSON, UTF-8.
- `ts` is the time of the reading in ISO 8601 UTC, e.g. `2026-11-03T08:15:00Z`.
- Units are part of the field name: `temperature_c` (°C), `speed_kmh` (km/h).
- IDs are lowercase with dashes: `fridge-1`, `freezer-1`, `truck-1`.
- QoS 1 for every message (delivered at least once).

## Topics

| Topic | Publisher | Retained | Purpose |
|---|---|---|---|
| `coldchain/sensors/<zone_id>/temperature` | sensor simulator | no | Temperature reading of a storage zone |
| `coldchain/sensors/<zone_id>/status` | sensor simulator / broker (last will) | yes | Sensor online or offline |
| `coldchain/trucks/<truck_id>/telemetry` | truck simulator | no | GPS position + cargo temperature |
| `coldchain/trucks/<truck_id>/status` | truck simulator / broker (last will) | yes | Truck online or offline |

Wildcards for subscribers:
- all sensor readings: `coldchain/sensors/+/temperature`
- all truck telemetry: `coldchain/trucks/+/telemetry`
- everything: `coldchain/#`

## Payloads

### Sensor temperature

```json
{
  "sensor_id": "sensor-fridge-1",
  "zone_id": "fridge-1",
  "zone_type": "fridge",
  "temperature_c": 3.42,
  "ts": "2026-11-03T08:15:00Z"
}
```

`zone_type` is `fridge` or `freezer`.

### Truck telemetry

```json
{
  "truck_id": "truck-1",
  "delivery_id": "DLV-0001",
  "lat": 35.4358,
  "lon": 7.1433,
  "speed_kmh": 62.5,
  "temperature_c": 3.10,
  "ts": "2026-11-03T08:15:00Z"
}
```

`delivery_id` links the truck to the batches it carries (PostgreSQL `deliveries` table).

### Status (sensors and trucks)

```json
{ "status": "online", "ts": "2026-11-03T08:15:00Z" }
```

On connect the simulator publishes `online` (retained). If it crashes or loses the
connection, the broker publishes its last will: `{ "status": "offline" }`.

## HACCP limits used by the alert rules

| Zone type | Allowed range | Alert when |
|---|---|---|
| `fridge` (and truck cargo) | 0 °C to 4 °C | reading < 0 or > 4 |
| `freezer` | ≤ −18 °C | reading > −18 |
| any sensor | — | no reading for more than 3 × `SENSOR_INTERVAL`, or status `offline` |

## Testing by hand

See every message:

```bash
docker compose exec mosquitto mosquitto_sub -t 'coldchain/#' -v
```

Send a fake out-of-range reading to test an alert:

```bash
docker compose exec mosquitto mosquitto_pub -t coldchain/sensors/fridge-1/temperature \
  -m '{"sensor_id":"sensor-fridge-1","zone_id":"fridge-1","zone_type":"fridge","temperature_c":9.5,"ts":"2026-11-03T08:15:00Z"}'
```
