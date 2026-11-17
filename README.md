# HACCP Cold Chain Monitoring

[![CI/CD](https://github.com/AbdouAll40/haccp-cold-chain/actions/workflows/ci.yml/badge.svg)](https://github.com/AbdouAll40/haccp-cold-chain/actions/workflows/ci.yml)

DevOps module project, theme "safety food". The system monitors the food cold chain following HACCP:

- **Temperatures** of fridges, freezers, a cold room and a refrigerated truck, with alerts when a reading leaves the HACCP limits or a sensor goes silent.
- **Expiry dates** of product batches: OK, expiring soon, expired. Expired batches cannot be shipped.
- **Delivery tracking**: the truck's GPS position on a live map. A temperature breach in transit flags every batch on board.

## Architecture

```
 fridge-1 ┐
freezer-1 ├─ MQTT ─► mosquitto ─► api (FastAPI) ─┬─► PostgreSQL (equipment, batches, alerts, readings)
coldroom-1┤                        HACCP rules    └─► InfluxDB ─► Grafana (dashboards)
  truck-1 ┘                             │
                                        └─ REST ◄─ web (nginx) ◄─ browser: dashboard, map, charts
                                        └─ /metrics ◄─ Prometheus (optional profile)
```

| Service | Role | URL |
|---|---|---|
| `mosquitto` | MQTT broker | `localhost:1883` |
| `fridge-1`, `freezer-1`, `coldroom-1` | Temperature sensor simulators | — |
| `truck-1` | Refrigerated truck simulator (GPS + cargo temperature) | — |
| `api` | Ingests MQTT, applies HACCP rules, REST API, Swagger docs | http://localhost:8000/docs |
| `postgres` | Equipment, products, batches, deliveries, alerts, inspections | internal |
| `influxdb` | Temperature and GPS history | http://localhost:8086 |
| `web` | Dashboard: KPIs, live map, charts, statistics, alerts, batches, inspections | http://localhost:8080 |
| `grafana` | Provisioned "HACCP Cold Chain" dashboard | http://localhost:3000 |
| `prometheus` | Scrapes API metrics (profile `monitoring`) | http://localhost:9090 |

## Quick start

```bash
cp .env.example .env          # then change the passwords
docker compose up -d --build
docker compose ps             # every service Up, health-checked ones "healthy"
```

Open the dashboard at http://localhost:8080. Grafana login: `admin` / the `GRAFANA_ADMIN_PASSWORD` from `.env`.

Watch the raw MQTT data:

```bash
docker compose exec mosquitto mosquitto_sub -t "coldchain/#" -v
```

Trigger an alert by hand (a fridge at 9.5 °C):

```bash
docker compose exec mosquitto mosquitto_pub -t coldchain/sensors/fridge-1/temperature \
  -m '{"zone_id":"fridge-1","zone_type":"fridge","temperature_c":9.5}'
```

Optional Prometheus: `docker compose --profile monitoring up -d`.
Stop: `docker compose down` (add `-v` to delete the data).

## HACCP rules

| Rule | Where |
|---|---|
| Fridge, cold room, truck: 0 to 4 °C; freezer: ≤ −18 °C. 3 °C past the limit = critical | `backend/app/rules.py` |
| Sensor silent after 3 × `SENSOR_INTERVAL`, or MQTT "last will" received | `rules.is_silent`, `services.handle_status` |
| Batch expiring within 3 days = warning, expired = critical; expired batches cannot be loaded into a delivery | `rules.expiry_status`, `rules.can_ship` |
| Breach in a fridge or truck flags the batches stored or carried there | `services.handle_sensor_reading`, `handle_truck_telemetry` |

## API (main endpoints)

`GET /health` · `GET /equipment` · `GET /trucks` · `GET /deliveries` · `GET /readings?source=fridge-1&minutes=30` ·
`GET /batches?status=soon` · `POST /batches` · `POST /deliveries/{code}/batches/{lot}` ·
`GET /alerts?status=open` · `POST /alerts/{id}/resolve` · `GET|POST /inspections` · `GET /stats?hours=1` · `GET /metrics/`

Full interactive documentation: http://localhost:8000/docs

## Development

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q          # 25 unit and API tests
ruff check .
```

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request:

1. **Lint and tests**: `ruff` and `pytest`.
2. **Compose validation**: `docker compose config`.
3. **Images**: build `api`, `simulators` and `web`, scan each with **Trivy** (HIGH/CRITICAL), and on `main` push them to GitHub Container Registry (`ghcr.io/<owner>/haccp-*`).

Dependabot keeps pip, npm, Docker and GitHub Actions dependencies up to date. `main` is protected: changes go through a reviewed pull request.

## Docs

- [MQTT topics and message format](docs/mqtt.md)

## Team

| Member | Area |
|---|---|
| Abdou | Leader, DevOps (Docker, CI/CD, monitoring) |
| Aymen | Data and backend |
| Achref | Dashboard and map; proposed the FoodSafe data model (equipment, products, alerts, inspections) |
