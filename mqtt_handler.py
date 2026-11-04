"""
Smart Classroom Monitor – MQTT Handler
=======================================
Subscribes to the Mosquitto broker and processes sensor data from the
Raspberry Pi.  Uses paho-mqtt v2.x callback API.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False

import config

log = logging.getLogger(__name__)


class MQTTHandler:
    """Manages the MQTT connection, subscription and message processing."""

    def __init__(self, broker_host: str, broker_port: int, topic: str,
                 on_reading_callback):
        """
        Args:
            broker_host:  Mosquitto broker IP / hostname.
            broker_port:  Broker port (default 1883).
            topic:        MQTT topic to subscribe to.
            on_reading_callback:  callable(reading_dict) invoked for each
                                  valid sensor message.
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self._callback = on_reading_callback
        self._connected = False
        self._lock = threading.Lock()
        self._client = None
        self._should_run = False

        if not PAHO_AVAILABLE:
            log.warning("paho-mqtt is not installed – MQTT will be unavailable")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def connect(self):
        """Start the MQTT client loop in a background thread."""
        if not PAHO_AVAILABLE:
            log.error("Cannot connect: paho-mqtt not installed")
            return

        if self._client is not None:
            self.disconnect()

        self._should_run = True

        try:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=config.MQTT_CLIENT_ID,
            )
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            log.info("Connecting to MQTT broker at %s:%s …",
                     self.broker_host, self.broker_port)
            self._client.connect_async(self.broker_host, self.broker_port,
                                       keepalive=config.MQTT_KEEPALIVE)
            self._client.loop_start()
        except Exception:
            log.exception("MQTT connect failed")
            with self._lock:
                self._connected = False

    def disconnect(self):
        """Cleanly disconnect and stop the background loop."""
        self._should_run = False
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                log.exception("Error during MQTT disconnect")
            self._client = None
        with self._lock:
            self._connected = False
        log.info("MQTT disconnected")

    # ------------------------------------------------------------------
    # Callbacks (paho-mqtt v2 signatures)
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            log.info("MQTT connected – subscribing to '%s'", self.topic)
            client.subscribe(self.topic)
            with self._lock:
                self._connected = True
        else:
            log.warning("MQTT connect returned reason_code=%s", reason_code)
            with self._lock:
                self._connected = False

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        with self._lock:
            self._connected = False
        if reason_code != 0:
            log.warning("MQTT unexpected disconnect (rc=%s). Will reconnect…",
                        reason_code)
        else:
            log.info("MQTT clean disconnect")

    def _on_message(self, client, userdata, msg):
        """Parse, validate and forward the sensor reading."""
        try:
            payload = msg.payload.decode("utf-8")
            data = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("Invalid MQTT payload on '%s': %s", msg.topic, exc)
            return

        reading = self._validate(data)
        if reading is not None and self._callback:
            try:
                self._callback(reading)
            except Exception:
                log.exception("Error in reading callback")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(data: dict) -> dict | None:
        """Normalise and validate an incoming sensor message.

        Returns a cleaned dict or None if the message is unusable.
        """
        reading = {}

        # Timestamp – use provided or generate
        ts = data.get("timestamp")
        if ts:
            try:
                datetime.fromisoformat(str(ts))
                reading["timestamp"] = str(ts)
            except ValueError:
                reading["timestamp"] = datetime.now(timezone.utc).isoformat()
        else:
            reading["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Temperature (-40 … 80 °C)
        temp = data.get("temperature")
        if temp is not None:
            try:
                temp = float(temp)
                reading["temperature"] = temp if -40 <= temp <= 80 else None
            except (ValueError, TypeError):
                reading["temperature"] = None
        else:
            reading["temperature"] = None

        # Humidity (0 … 100 %)
        hum = data.get("humidity")
        if hum is not None:
            try:
                hum = float(hum)
                reading["humidity"] = hum if 0 <= hum <= 100 else None
            except (ValueError, TypeError):
                reading["humidity"] = None
        else:
            reading["humidity"] = None

        # Light – accept string ("Bright"/"Moderate"/"Dark") or raw int
        light = data.get("light")
        light_raw = data.get("light_raw")
        if isinstance(light, str) and light in ("Bright", "Moderate", "Dark"):
            reading["light"] = light
        elif isinstance(light, (int, float)):
            light_raw = int(light)
            reading["light"] = MQTTHandler._classify_light(light_raw)
        else:
            reading["light"] = None

        if light_raw is not None:
            try:
                reading["light_raw"] = int(light_raw)
            except (ValueError, TypeError):
                reading["light_raw"] = None
        else:
            reading["light_raw"] = None

        # Distance (0 … 400 cm for HC-SR04)
        dist = data.get("distance")
        if dist is not None:
            try:
                dist = float(dist)
                reading["distance"] = dist if 0 <= dist <= 400 else None
            except (ValueError, TypeError):
                reading["distance"] = None
        else:
            reading["distance"] = None

        # PIR sensors – bool / int
        for key in ("pir1", "pir2"):
            val = data.get(key)
            if val is not None:
                reading[key] = bool(val)
            else:
                reading[key] = None

        return reading

    @staticmethod
    def _classify_light(raw_value: int) -> str:
        """Classify a raw LDR value into Dark / Moderate / Bright."""
        from database import get_setting
        bright_th = get_setting("light_bright_threshold") or 700
        mod_th = get_setting("light_moderate_threshold") or 300
        if raw_value >= bright_th:
            return "Bright"
        elif raw_value >= mod_th:
            return "Moderate"
        else:
            return "Dark"

