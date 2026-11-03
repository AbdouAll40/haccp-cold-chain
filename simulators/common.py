"""Shared helpers for the simulators (see docs/mqtt.md for the message format)."""
import json
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
INTERVAL = float(os.getenv("SENSOR_INTERVAL", "5"))

# Target temperature and HACCP limit per zone type (°C)
ZONES = {
    "fridge": {"target": 3.0, "noise": 0.3},
    "freezer": {"target": -20.0, "noise": 0.5},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def connect(client_id: str, status_topic: str) -> mqtt.Client:
    """Connect with retry. Publishes a retained 'online' status, and the broker
    publishes 'offline' (last will) if the simulator dies."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.will_set(status_topic, json.dumps({"status": "offline"}), qos=1, retain=True)

    def on_connect(c, userdata, flags, reason_code, properties):
        print(f"[{client_id}] connected to {MQTT_HOST}:{MQTT_PORT} ({reason_code})")
        c.publish(status_topic, json.dumps({"status": "online", "ts": now_iso()}), qos=1, retain=True)

    client.on_connect = on_connect
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except OSError as e:
            print(f"[{client_id}] broker not reachable ({e}), retrying in 3s")
            time.sleep(3)
    client.loop_start()
    return client


class Thermometer:
    """Random walk around the target temperature, with occasional anomalies
    (door left open, power loss) so the alert rules have something to catch."""

    def __init__(self, zone_type: str, anomaly_rate: float = 0.03):
        cfg = ZONES[zone_type]
        self.target = cfg["target"]
        self.noise = cfg["noise"]
        self.temp = self.target
        self.anomaly_rate = anomaly_rate
        self.anomaly_left = 0

    def read(self) -> float:
        if self.anomaly_left == 0 and random.random() < self.anomaly_rate:
            self.anomaly_left = random.randint(5, 12)
        if self.anomaly_left > 0:
            self.temp += random.uniform(0.5, 1.2)  # warming up
            self.anomaly_left -= 1
        else:
            self.temp += (self.target - self.temp) * 0.3  # back toward target
        self.temp += random.gauss(0, self.noise)
        return round(self.temp, 2)
