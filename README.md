# HACCP Cold Chain Monitoring

DevOps module project, theme "safety food": temperature monitoring of fridges,
freezers and delivery trucks (HACCP), product expiry dates, and live delivery tracking.

## Services

| Service | What it does | URL |
|---|---|---|
| `mosquitto` | MQTT broker | `localhost:1883` |
| `fridge-1`, `freezer-1` | Temperature sensor simulators | — |
| `truck-1` | Delivery truck simulator (GPS + temperature) | — |
| `api` | Backend API (FastAPI) | http://localhost:8000/health |
| `postgres` | Products, batches, deliveries, alerts | internal |
| `influxdb` | Temperature and GPS history | http://localhost:8086 |
| `web` | Dashboard | http://localhost:8080 |
| `grafana` | Charts and alerts | http://localhost:3000 |

## Quick start

```bash
cp .env.example .env        # then change the passwords
docker compose up -d --build
docker compose ps           # every service should be "running" / "healthy"
```

Watch the simulated data:

```bash
docker compose exec mosquitto mosquitto_sub -t 'coldchain/#' -v
```

Stop everything: `docker compose down` (add `-v` to also delete the data).

## Docs

- [MQTT topics and message format](docs/mqtt.md)

## Team

| Member | Area |
|---|---|
| Member 1 | Data & backend (simulators, MQTT, API, databases) |
| Member 2 | Web dashboard + map |
| Member 3 | DevOps (Docker, CI/CD, monitoring) |
