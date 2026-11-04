"""
Smart Classroom Monitor – Application Configuration
=====================================================
Central configuration for the Smart Classroom Monitoring System.
All configurable values should be defined here rather than hard-coded
throughout the application.
"""

import os

# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "smart-classroom-default-secret-key")
DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

# ---------------------------------------------------------------------------
# MQTT Broker (Mosquitto on the laptop)
# ---------------------------------------------------------------------------
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", 1883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "classroom/sensors")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "smart-classroom-backend")
MQTT_KEEPALIVE = 60          # seconds
MQTT_RECONNECT_DELAY = 5     # seconds between reconnect attempts

# ---------------------------------------------------------------------------
# SQLite Database
# ---------------------------------------------------------------------------
DATABASE_PATH = os.environ.get("DATABASE_PATH",
                               os.path.join(os.path.dirname(__file__), "classroom.db"))

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAPTURED_IMAGES_DIR = os.environ.get(
    "CAPTURED_IMAGES_DIR",
    os.path.join(os.path.dirname(__file__), "captured_images"))

# ---------------------------------------------------------------------------
# Operating Mode – "demo" or "live"
# ---------------------------------------------------------------------------
DEFAULT_MODE = os.environ.get("DEFAULT_MODE", "demo")

# ---------------------------------------------------------------------------
# Demo-data generator
# ---------------------------------------------------------------------------
DEMO_UPDATE_INTERVAL = float(os.environ.get("DEMO_UPDATE_INTERVAL", 4))  # seconds

# ---------------------------------------------------------------------------
# Default sensor / alert thresholds (stored in DB; these are initial values)
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    # Temperature (°C)
    "temp_min": 18.0,
    "temp_max": 35.0,

    # Relative humidity (%)
    "humidity_min": 30.0,
    "humidity_max": 80.0,

    # LDR brightness thresholds (raw ADC or mapped 0-1023)
    "light_bright_threshold": 700,
    "light_moderate_threshold": 300,

    # Inactivity timeout – seconds with no PIR motion before "No Recent Motion"
    "inactivity_timeout": 300,

    # Sensor data timeout – seconds before a sensor is considered disconnected
    "sensor_timeout": 60,

    # Dashboard auto-refresh interval (seconds) – used by frontend polling
    "refresh_interval": 5,

    # Demo data update interval (seconds)
    "demo_update_interval": 4,
}

