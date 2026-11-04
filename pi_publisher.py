#!/usr/bin/env python3
"""
Raspberry Pi 3 Model B – Smart Classroom Sensor Publisher
==========================================================
Collects environmental data from:
  - 2x PIR Motion Sensors (e.g. GPIO 17 & 27)
  - 1x HC-SR04 Ultrasonic Distance Sensor (Trigger GPIO 23, Echo GPIO 24)
  - 1x DHT22 Temperature & Humidity Sensor (Data GPIO 4)
  - 1x LDR Light Dependent Resistor (RC timing or MCP3008 ADC)
  - 1x Raspberry Pi Camera Module V2 (captures still photos when motion is detected)

Publishes JSON sensor telemetry to Mosquitto MQTT broker on the laptop:
  Topic: classroom/sensors
"""

import os
import sys
import time
import json
import socket
import logging
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration - Adjust IP to your Laptop's Local Wi-Fi IP address!
# ---------------------------------------------------------------------------
MQTT_BROKER = os.environ.get("MQTT_BROKER", "192.168.1.100")  # Set to laptop Wi-Fi IP
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "classroom/sensors")
PUBLISH_INTERVAL = 3.0  # seconds

# GPIO Pin Configuration (BCM numbering)
PIR1_PIN = 17
PIR2_PIN = 27
TRIG_PIN = 23
ECHO_PIN = 24
DHT_PIN = 4
LDR_PIN = 18

IMAGE_SAVE_DIR = "captured_images"

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("PiSensorPublisher")

# ---------------------------------------------------------------------------
# Hardware Library Imports (with graceful simulation fallback)
# ---------------------------------------------------------------------------
IS_RASPBERRY_PI = False
try:
    import RPi.GPIO as GPIO
    import Adafruit_DHT
    from picamera import PiCamera
    IS_RASPBERRY_PI = True
    log.info("Running on native Raspberry Pi hardware.")
except (ImportError, RuntimeError):
    log.warning("Hardware libraries not available. Running in local test simulation mode.")

try:
    import paho.mqtt.client as mqtt
except ImportError:
    log.error("paho-mqtt is required. Run: pip install paho-mqtt")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Hardware Sensor Drivers
# ---------------------------------------------------------------------------
camera = None

def init_hardware():
    global camera
    if not IS_RASPBERRY_PI:
        return

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # PIR Pins
    GPIO.setup(PIR1_PIN, GPIO.IN)
    GPIO.setup(PIR2_PIN, GPIO.IN)

    # Ultrasonic Pins
    GPIO.setup(TRIG_PIN, GPIO.OUT)
    GPIO.setup(ECHO_PIN, GPIO.IN)
    GPIO.output(TRIG_PIN, False)

    # LDR Pin setup
    GPIO.setup(LDR_PIN, GPIO.IN)

    # Initialize Camera
    try:
        os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
        camera = PiCamera()
        camera.resolution = (1024, 768)
        time.sleep(1)  # Warmup
        log.info("Pi Camera Module V2 initialized.")
    except Exception as e:
        log.warning(f"Could not initialize Pi Camera: {e}")
        camera = None


def read_pir_sensors():
    """Reads PIR motion sensor digital states."""
    if not IS_RASPBERRY_PI:
        import random
        return random.random() < 0.4, random.random() < 0.3

    p1 = GPIO.input(PIR1_PIN) == GPIO.HIGH
    p2 = GPIO.input(PIR2_PIN) == GPIO.HIGH
    return p1, p2


def read_ultrasonic_distance():
    """Measures distance in cm using HC-SR04 sonar pulse timing."""
    if not IS_RASPBERRY_PI:
        import random
        return round(random.uniform(40.0, 180.0), 1)

    try:
        # Trigger 10us ultrasonic burst
        GPIO.output(TRIG_PIN, True)
        time.sleep(0.00001)
        GPIO.output(TRIG_PIN, False)

        pulse_start = time.time()
        timeout_start = pulse_start
        while GPIO.input(ECHO_PIN) == 0:
            pulse_start = time.time()
            if pulse_start - timeout_start > 0.04:  # timeout
                return None

        pulse_end = time.time()
        timeout_start = pulse_end
        while GPIO.input(ECHO_PIN) == 1:
            pulse_end = time.time()
            if pulse_end - timeout_start > 0.04:
                return None

        pulse_duration = pulse_end - pulse_start
        # Speed of sound is 34300 cm/s -> distance = (duration * 34300) / 2
        distance = round(pulse_duration * 17150, 1)

        if 2.0 <= distance <= 400.0:
            return distance
        return None
    except Exception as e:
        log.warning(f"Ultrasonic read error: {e}")
        return None


def read_dht22():
    """Reads temperature (°C) and humidity (%) from DHT22."""
    if not IS_RASPBERRY_PI:
        import random
        return round(random.uniform(26.0, 29.5), 1), round(random.uniform(50.0, 65.0), 1)

    try:
        humidity, temperature = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, DHT_PIN)
        if humidity is not None and temperature is not None:
            return round(temperature, 1), round(humidity, 1)
        return None, None
    except Exception as e:
        log.warning(f"DHT22 read error: {e}")
        return None, None


def read_ldr_light():
    """
    Reads ambient light level using RC timing technique or MCP3008 ADC.
    Returns (light_classification, raw_value).
    """
    if not IS_RASPBERRY_PI:
        import random
        raw = random.randint(200, 850)
        state = "Bright" if raw > 700 else ("Moderate" if raw > 300 else "Dark")
        return state, raw

    try:
        # Simple RC charge timing measurement
        count = 0
        GPIO.setup(LDR_PIN, GPIO.OUT)
        GPIO.output(LDR_PIN, GPIO.LOW)
        time.sleep(0.01)

        GPIO.setup(LDR_PIN, GPIO.IN)
        while GPIO.input(LDR_PIN) == GPIO.LOW and count < 10000:
            count += 1

        # In RC timing, lower count = brighter, higher count = darker
        # Map roughly to 0-1023 raw scale
        raw_scale = max(0, min(1023, int(1023 - (count / 10))))
        if raw_scale >= 700:
            classification = "Bright"
        elif raw_scale >= 300:
            classification = "Moderate"
        else:
            classification = "Dark"
        return classification, raw_scale
    except Exception as e:
        log.warning(f"LDR read error: {e}")
        return "Moderate", 500


def capture_motion_photo():
    """Captures a timestamped still image when motion is detected."""
    global camera
    if not camera:
        return None

    try:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{timestamp_str}.jpg"
        filepath = os.path.join(IMAGE_SAVE_DIR, filename)
        camera.capture(filepath)
        log.info(f"Captured security snapshot: {filepath}")
        return filepath
    except Exception as e:
        log.warning(f"Camera capture error: {e}")
        return None


# ---------------------------------------------------------------------------
# Main Publisher Loop
# ---------------------------------------------------------------------------
def main():
    log.info(f"Starting Raspberry Pi Smart Classroom Publisher...")
    log.info(f"Target MQTT Broker: {MQTT_BROKER}:{MQTT_PORT} (Topic: {MQTT_TOPIC})")

    init_hardware()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2 if hasattr(mqtt, 'CallbackAPIVersion') else None, client_id="pi-classroom-publisher")

    connected = False
    while not connected:
        try:
            log.info(f"Connecting to broker at {MQTT_BROKER}...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start()
            connected = True
            log.info("Successfully connected to Mosquitto broker!")
        except Exception as e:
            log.warning(f"MQTT connection failed ({e}). Retrying in 5 seconds...")
            time.sleep(5)

    last_photo_time = 0

    try:
        while True:
            # 1. Read all sensors
            pir1, pir2 = read_pir_sensors()
            distance = read_ultrasonic_distance()
            temp, hum = read_dht22()
            light_state, light_raw = read_ldr_light()

            now_iso = datetime.now(timezone.utc).isoformat()

            # 2. Trigger camera snapshot on motion (rate limited to once every 60s)
            if (pir1 or pir2) and (time.time() - last_photo_time > 60):
                photo_path = capture_motion_photo()
                if photo_path:
                    last_photo_time = time.time()

            # 3. Construct standard telemetry payload
            payload = {
                "pir1": pir1,
                "pir2": pir2,
                "temperature": temp,
                "humidity": hum,
                "light": light_state,
                "light_raw": light_raw,
                "distance": distance,
                "timestamp": now_iso
            }

            json_data = json.dumps(payload)
            client.publish(MQTT_TOPIC, json_data, qos=0)
            log.info(f"Published: {json_data}")

            time.sleep(PUBLISH_INTERVAL)

    except KeyboardInterrupt:
        log.info("Publisher stopped by user.")
    finally:
        client.loop_stop()
        client.disconnect()
        if IS_RASPBERRY_PI:
            GPIO.cleanup()
            if camera:
                camera.close()
        log.info("Cleaned up resources and exited.")


if __name__ == "__main__":
    main()

