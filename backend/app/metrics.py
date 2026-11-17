"""Prometheus metrics exposed on /metrics."""
from prometheus_client import Counter, Gauge

TEMPERATURE = Gauge("coldchain_temperature_celsius", "Last temperature per sensor or truck", ["source"])
ALERTS_TOTAL = Counter("coldchain_alerts_total", "Alerts raised", ["kind", "severity"])
MQTT_MESSAGES = Counter("coldchain_mqtt_messages_total", "MQTT messages processed", ["kind"])
