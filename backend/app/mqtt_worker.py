"""MQTT subscriber: validate each message, store it, push it to live clients.

paho-mqtt runs its own network thread (loop_start), which also reconnects
automatically if the broker goes away.
"""

import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlalchemy import Engine

from .db import insert_reading
from .models import TelemetryMessage

log = logging.getLogger(__name__)


def handle_payload(
    payload: bytes, engine: Engine, on_saved: Callable[[dict], None] | None = None
) -> TelemetryMessage | None:
    """Parse, validate and store one message. Returns None if it was rejected.

    Kept separate from the paho callbacks so tests can call it directly.
    """
    try:
        msg = TelemetryMessage.model_validate(json.loads(payload))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        log.warning("rejected MQTT message: %s", exc)
        return None

    insert_reading(engine, msg)
    if on_saved is not None:
        data = msg.model_dump(mode="json")
        on_saved(data)
    return msg


class MqttWorker:
    def __init__(
        self,
        host: str,
        port: int,
        topic: str,
        engine: Engine,
        on_saved: Callable[[dict], None] | None = None,
    ):
        self.topic = topic
        self.engine = engine
        self.on_saved = on_saved
        self.connected = False
        self._host, self._port = host, port

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="battery-backend"
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def start(self) -> None:
        # connect_async + loop_start: retries in the background until the
        # broker is reachable, so the API starts even if MQTT is down.
        self._client.connect_async(self._host, self._port, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    # paho callbacks (run on paho's thread) --------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("MQTT connect refused: %s", reason_code)
            return
        self.connected = True
        # Subscribing here means we re-subscribe after every reconnect.
        client.subscribe(self.topic, qos=0)
        log.info("MQTT connected to %s:%s, subscribed to %s", self._host, self._port, self.topic)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        log.warning("MQTT disconnected (%s), will reconnect", reason_code)

    def _on_message(self, client, userdata, message):
        try:
            handle_payload(message.payload, self.engine, self.on_saved)
        except Exception:  # a DB hiccup must not kill the MQTT thread
            log.exception("failed to store MQTT message")
