"""Fridge / freezer temperature sensor simulator.

Publishes to: coldchain/sensors/<zone_id>/temperature
Status topic: coldchain/sensors/<zone_id>/status   (retained, with last will)
"""
import json
import os
import time

from common import INTERVAL, Thermometer, connect, now_iso

ZONE_ID = os.getenv("ZONE_ID", "fridge-1")
ZONE_TYPE = os.getenv("ZONE_TYPE", "fridge")
SENSOR_ID = os.getenv("SENSOR_ID", f"sensor-{ZONE_ID}")

TOPIC = f"coldchain/sensors/{ZONE_ID}/temperature"
STATUS_TOPIC = f"coldchain/sensors/{ZONE_ID}/status"


def main():
    client = connect(SENSOR_ID, STATUS_TOPIC)
    thermo = Thermometer(ZONE_TYPE)
    while True:
        payload = {
            "sensor_id": SENSOR_ID,
            "zone_id": ZONE_ID,
            "zone_type": ZONE_TYPE,
            "temperature_c": thermo.read(),
            "ts": now_iso(),
        }
        client.publish(TOPIC, json.dumps(payload), qos=1)
        print(f"{TOPIC} {payload}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
