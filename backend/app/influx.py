"""Optional writer to InfluxDB (used by Grafana). Never blocks the API if InfluxDB is down."""
import logging
from datetime import datetime

from . import config

log = logging.getLogger("coldchain.influx")


class InfluxWriter:
    def __init__(self):
        self._api = None
        self._warned = False
        if not (config.INFLUXDB_URL and config.INFLUXDB_TOKEN):
            return
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS

            client = InfluxDBClient(url=config.INFLUXDB_URL, token=config.INFLUXDB_TOKEN,
                                    org=config.INFLUXDB_ORG, timeout=3000)
            self._api = client.write_api(write_options=SYNCHRONOUS)
        except Exception as e:  # pragma: no cover
            log.warning("InfluxDB disabled: %s", e)

    def _write(self, record) -> None:
        if self._api is None:
            return
        try:
            self._api.write(bucket=config.INFLUXDB_BUCKET, org=config.INFLUXDB_ORG, record=record)
            self._warned = False
        except Exception as e:
            if not self._warned:
                log.warning("InfluxDB write failed (will keep trying): %s", e)
                self._warned = True

    def write_temperature(self, source: str, zone_type: str, value: float, ts: datetime) -> None:
        if self._api is None:
            return
        from influxdb_client import Point
        self._write(Point("temperature").tag("source", source).tag("zone_type", zone_type)
                    .field("value", value).time(ts))

    def write_truck(self, truck: str, temp: float, speed: float, lat: float, lon: float, ts: datetime) -> None:
        if self._api is None:
            return
        from influxdb_client import Point
        self._write(Point("temperature").tag("source", truck).tag("zone_type", "truck")
                    .field("value", temp).time(ts))
        self._write(Point("truck").tag("truck", truck).field("speed_kmh", speed)
                    .field("lat", lat).field("lon", lon).time(ts))


influx = InfluxWriter()
