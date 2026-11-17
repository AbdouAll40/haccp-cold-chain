"""Settings read from environment variables (see .env.example)."""
import os


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./coldchain.db")

MQTT_ENABLED = _bool("MQTT_ENABLED", "true")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "haccp")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "telemetry")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")

# Expected seconds between two readings of a sensor (same as the simulators).
SENSOR_INTERVAL = float(os.getenv("SENSOR_INTERVAL", "5"))
# A sensor is "silent" after this many intervals without a reading.
SILENT_FACTOR = float(os.getenv("SILENT_FACTOR", "3"))
# A batch is "expiring soon" when it expires within this many days.
EXPIRY_SOON_DAYS = int(os.getenv("EXPIRY_SOON_DAYS", "3"))
# How often the background checks (silent sensors, expiry) run, in seconds.
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "10"))
# Readings older than this are deleted from PostgreSQL (InfluxDB keeps history).
READINGS_RETENTION_HOURS = int(os.getenv("READINGS_RETENTION_HOURS", "48"))

SEED_DEMO_DATA = _bool("SEED_DEMO_DATA", "true")
