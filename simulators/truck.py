"""Refrigerated delivery truck simulator (GPS + cargo temperature).

Drives back and forth along a route and publishes to:
  coldchain/trucks/<truck_id>/telemetry
Status topic: coldchain/trucks/<truck_id>/status   (retained, with last will)
"""
import json
import math
import os
import random
import time

from common import INTERVAL, Thermometer, connect, now_iso

TRUCK_ID = os.getenv("TRUCK_ID", "truck-1")
DELIVERY_ID = os.getenv("DELIVERY_ID", "DLV-0001")
SPEED_KMH = float(os.getenv("SPEED_KMH", "70"))
# Simulated seconds per real second, so a demo trip takes minutes, not hours.
TIME_SCALE = float(os.getenv("TIME_SCALE", "60"))

TOPIC = f"coldchain/trucks/{TRUCK_ID}/telemetry"
STATUS_TOPIC = f"coldchain/trucks/{TRUCK_ID}/status"

# Demo route: warehouse in Khenchela -> shop in Batna (lat, lon)
ROUTE = [
    (35.4358, 7.1433),  # Khenchela
    (35.4600, 6.9300),
    (35.4900, 6.6500),
    (35.5200, 6.4000),
    (35.5559, 6.1741),  # Batna
]


def distance_km(a, b):
    """Haversine distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def positions(step_km):
    """Yield points every step_km along the route, forever, back and forth."""
    route = ROUTE
    while True:
        for a, b in zip(route, route[1:]):
            leg = distance_km(a, b)
            n = max(1, round(leg / step_km))
            for i in range(n):
                t = i / n
                yield (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        route = route[::-1]


def main():
    client = connect(TRUCK_ID, STATUS_TOPIC)
    thermo = Thermometer("fridge")
    step_km = SPEED_KMH * INTERVAL * TIME_SCALE / 3600
    for pos in positions(step_km):
        speed = max(0.0, random.gauss(SPEED_KMH, 5))
        payload = {
            "truck_id": TRUCK_ID,
            "delivery_id": DELIVERY_ID,
            "lat": round(pos[0], 6),
            "lon": round(pos[1], 6),
            "speed_kmh": round(speed, 1),
            "temperature_c": thermo.read(),
            "ts": now_iso(),
        }
        client.publish(TOPIC, json.dumps(payload), qos=1)
        print(f"{TOPIC} {payload}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
