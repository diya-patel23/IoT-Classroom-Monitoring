#!/usr/bin/env python3
"""
Smart Classroom Monitor – Standalone Test Publisher
===================================================
A lightweight test publisher that pushes realistic sensor data
directly into the local Mosquitto MQTT broker (`classroom/sensors`).

Use this script to test and demonstrate 'Live Mode' without physical
Raspberry Pi hardware connected.
"""

import time
import json
import random
import logging
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt is required to run this test publisher.")
    print("Install it with: pip install paho-mqtt")
    exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MockPublisher")

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC = "classroom/sensors"
INTERVAL = 3.0  # seconds

def main():
    log.info(f"Connecting to MQTT Broker at {BROKER_HOST}:{BROKER_PORT}...")
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2 if hasattr(mqtt, "CallbackAPIVersion") else None,
        client_id="mock-classroom-publisher"
    )

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_start()
        log.info(f"Connected to Mosquitto! Publishing sensor data to '{TOPIC}' every {INTERVAL}s")
        log.info("Press Ctrl+C to stop.\n")
    except Exception as e:
        log.error(f"Failed to connect to Mosquitto: {e}")
        log.error("Please verify that Mosquitto is running on your laptop.")
        return

    temp = 27.0
    humidity = 60.0
    light_options = ["Bright", "Moderate", "Dark"]

    try:
        tick = 0
        while True:
            tick += 1
            # Simulate natural drift
            temp = round(max(20.0, min(36.0, temp + random.uniform(-0.3, 0.3))), 1)
            humidity = round(max(30.0, min(85.0, humidity + random.uniform(-0.6, 0.6))), 1)
            distance = round(random.uniform(30.0, 180.0), 1)

            # PIR detection
            pir1 = random.random() < 0.45
            pir2 = random.random() < 0.35

            # Light level
            light = light_options[0] if tick % 15 < 8 else (light_options[1] if tick % 15 < 12 else light_options[2])
            light_raw = 820 if light == "Bright" else (480 if light == "Moderate" else 160)

            payload = {
                "pir1": pir1,
                "pir2": pir2,
                "temperature": temp,
                "humidity": humidity,
                "light": light,
                "light_raw": light_raw,
                "distance": distance,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            client.publish(TOPIC, json.dumps(payload), qos=0)
            log.info(f"Published payload -> Temp: {temp}°C | Hum: {humidity}% | Light: {light} | Dist: {distance}cm | PIR: [{pir1},{pir2}]")

            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        log.info("Stopping mock publisher...")
    finally:
        client.loop_stop()
        client.disconnect()
        log.info("Disconnected cleanly.")

if __name__ == "__main__":
    main()

