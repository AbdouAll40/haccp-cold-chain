# FoodSafe: cold-chain monitoring (HACCP)

Monitors fridges, freezers and cold rooms, records temperatures, raises an alert when a
reading leaves the safe range, and tracks product expiry dates.

## Run it
```bash
docker compose up --build
```
- Dashboard: http://localhost:8080
- API docs (Swagger): http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

The simulator posts readings every 2 s and randomly "opens a door" so alerts appear.

### With monitoring (Prometheus + Grafana)
```bash
docker compose --profile monitoring up --build
```
- Prometheus: http://localhost:9090 (try `foodsafe_temperature_celsius`)
- Grafana: http://localhost:3000 (admin / admin). The Prometheus data source is pre-configured;
  create a time-series panel with `foodsafe_temperature_celsius` and a stat panel with
  `sum(foodsafe_alerts_total)`.

## Tests
```bash
cd api
pip install -r requirements-dev.txt
pytest -q
```

## Layout
```
api/         FastAPI + SQLAlchemy (PostgreSQL), tests
simulator/   sensor simulator
dashboard/   static page served by nginx (proxies /api to the API)
monitoring/  Prometheus + Grafana config
.github/     CI pipeline (lint, test, build, Trivy scan, push to GHCR) + PR template
```

## Git workflow
Branch from `develop`, open a PR to `develop`; `main` only receives merges from `develop`.
Images are pushed to GHCR only on `main`.
