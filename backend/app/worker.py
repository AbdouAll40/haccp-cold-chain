"""Background work: the MQTT subscriber and the periodic checks."""
import json
import logging
import threading
import time

from . import config
from .db import SessionLocal
from .services import handle_message, run_periodic_checks

log = logging.getLogger("coldchain.worker")
_lock = threading.Lock()  # one DB writer at a time (MQTT thread + checks thread)
_stop = threading.Event()
state = {"mqtt_connected": False}


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        log.warning("ignored non-JSON message on %s", msg.topic)
        return
    with _lock, SessionLocal() as db:
        try:
            handle_message(db, msg.topic, payload)
            db.commit()
        except (KeyError, TypeError, ValueError) as e:
            db.rollback()
            log.warning("ignored bad message on %s: %s", msg.topic, e)
        except Exception:
            db.rollback()
            log.exception("error handling %s", msg.topic)


def start_mqtt():
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="coldchain-api")

    def on_connect(c, userdata, flags, reason_code, properties):
        state["mqtt_connected"] = not reason_code.is_failure
        c.subscribe("coldchain/#", qos=1)
        log.info("MQTT connected to %s:%s, subscribed to coldchain/#", config.MQTT_HOST, config.MQTT_PORT)

    def on_disconnect(c, userdata, flags, reason_code, properties):
        state["mqtt_connected"] = False
        log.warning("MQTT disconnected (%s), reconnecting", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    client.loop_start()
    return client


def _checks_loop():
    while not _stop.wait(config.CHECK_INTERVAL):
        with _lock, SessionLocal() as db:
            try:
                run_periodic_checks(db)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("periodic checks failed")


def start_checks():
    t = threading.Thread(target=_checks_loop, name="checks", daemon=True)
    t.start()
    return t


def stop():
    _stop.set()
    time.sleep(0)
