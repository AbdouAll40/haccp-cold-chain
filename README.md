# FoodSafe

FoodSafe is a smart food safety and cold-chain monitoring platform for tracking temperature compliance, equipment status, product expiry, and HACCP inspection records in one place.

## Architecture

- Backend: FastAPI API with SQLAlchemy models and PostgreSQL support
- Frontend: static dashboard served by Nginx with real API-driven data
- Simulator: background service that posts realistic temperature readings
- Monitoring: Prometheus for scraping and Grafana dashboards for operational visibility
- Testing: Pytest for API and regression coverage

## Local setup

1. Copy the sample environment file and adjust values if needed:
   ```bash
   cp .env.example .env
   ```
2. Start the app:
   ```bash
   docker compose up --build
   ```
3. Access the services:
   - Dashboard: http://localhost:8080
   - API docs: http://localhost:8000/docs
   - Metrics: http://localhost:8000/metrics

## Monitoring profile

```bash
docker compose --profile monitoring up --build
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Default Grafana credentials: admin / admin (or use the values from `.env`)

## Backend development

```bash
cd api
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
```

## Environment variables

The project reads from the local `.env` file when present. Available values are defined in [.env.example](.env.example).

Key settings:
- `DATABASE_URL`: PostgreSQL connection string for the API
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: database configuration
- `API_PORT`, `DASHBOARD_PORT`, `PROMETHEUS_PORT`, `GRAFANA_PORT`: exposed service ports

## Included functionality

- Equipment lifecycle management and threshold tracking
- Product inventory with expiry monitoring
- Alert generation and resolution
- HACCP inspection recording
- Temperature history and analytics export
- Prometheus metrics for API monitoring

## Troubleshooting

- If the API is not ready, wait for the `db` and `api` health checks to pass.
- If the simulator appears inactive, confirm the `api` container is healthy and that the service is not failing during startup.
- If Grafana is empty, make sure the monitoring profile is enabled with `--profile monitoring`.
- If the database is not connecting, check the `DATABASE_URL` value and the Postgres container status.

## Project layout

```text
api/          FastAPI service and PostgreSQL-backed API
simulator/    sensor simulator posting temperature samples
monitoring/   Prometheus and Grafana configuration
Dashboard/    static dashboard served by Nginx
.github/      CI workflow for tests and image validation
``` 
