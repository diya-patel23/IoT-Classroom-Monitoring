"""
Smart Classroom Monitor – Flask Application
============================================
Central web server exposing REST APIs for the frontend dashboard.
Manages mode switching between Demo and Live, MQTT connection, and
demo-data generation.
"""

import csv
import io
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import (Flask, jsonify, make_response, render_template, request,
                   send_from_directory)

import config
import database
from alert_manager import AlertManager
from demo_data import DemoDataGenerator
from mqtt_handler import MQTTHandler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = config.SECRET_KEY

# ---------------------------------------------------------------------------
# Shared state (protected by _state_lock)
# ---------------------------------------------------------------------------
_state_lock = threading.Lock()
_current_mode: str = config.DEFAULT_MODE  # "demo" | "live"
_latest_reading: dict | None = None
_last_reading_time: str | None = None
_last_pir1_motion: str | None = None
_last_pir2_motion: str | None = None

# Module instances
_alert_manager = AlertManager()
_demo_generator: DemoDataGenerator | None = None
_mqtt_handler: MQTTHandler | None = None


# ---------------------------------------------------------------------------
# CORS – allow local-network access
# ---------------------------------------------------------------------------
@app.after_request
def _add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


# ---------------------------------------------------------------------------
# Sensor reading callback (called by MQTT handler or demo generator)
# ---------------------------------------------------------------------------
def _on_sensor_reading(reading: dict):
    global _latest_reading, _last_reading_time, _last_pir1_motion, _last_pir2_motion

    with _state_lock:
        _latest_reading = reading
        _last_reading_time = reading.get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )
        if reading.get("pir1"):
            _last_pir1_motion = _last_reading_time
        if reading.get("pir2"):
            _last_pir2_motion = _last_reading_time

    source = _current_mode
    database.save_reading(reading, source=source)
    _alert_manager.check_reading(reading, source=source)


# ---------------------------------------------------------------------------
# Routes – Pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes – Mode
# ---------------------------------------------------------------------------
@app.route("/api/mode", methods=["GET"])
def get_mode():
    return jsonify({"mode": _current_mode})


@app.route("/api/mode", methods=["POST"])
def set_mode():
    global _current_mode, _demo_generator, _mqtt_handler

    data = request.get_json(silent=True) or {}
    new_mode = data.get("mode", "").lower()
    if new_mode not in ("demo", "live"):
        return jsonify({"error": "mode must be 'demo' or 'live'"}), 400

    if new_mode == _current_mode:
        return jsonify({"mode": _current_mode, "success": True})

    log.info("Switching mode: %s → %s", _current_mode, new_mode)

    if new_mode == "demo":
        # Stop live, start demo
        if _mqtt_handler:
            _mqtt_handler.disconnect()
        database.clear_demo_data()
        _current_mode = "demo"
        _start_demo()
    else:
        # Stop demo, start live
        if _demo_generator:
            _demo_generator.stop()
        _current_mode = "live"
        _start_live()

    return jsonify({"mode": _current_mode, "success": True})


# ---------------------------------------------------------------------------
# Routes – System status
# ---------------------------------------------------------------------------
@app.route("/api/status", methods=["GET"])
def get_status():
    with _state_lock:
        reading = _latest_reading
        last_ts = _last_reading_time
        pir1_ts = _last_pir1_motion
        pir2_ts = _last_pir2_motion

    is_demo = _current_mode == "demo"
    mqtt_connected = bool(_mqtt_handler and _mqtt_handler.is_connected)
    system_online = is_demo or mqtt_connected

    sensor_timeout = float(database.get_setting("sensor_timeout") or 60)

    def _sensor_connected(value):
        """Check if a sensor field is present and recent."""
        if reading is None:
            return False
        if is_demo:
            return True
        # In live mode, check timestamp recency
        if last_ts:
            try:
                ts = datetime.fromisoformat(last_ts)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                return age < sensor_timeout and value is not None
            except (ValueError, TypeError):
                pass
        return value is not None

    sensors = {
        "pir1": {
            "connected": _sensor_connected(reading.get("pir1") if reading else None),
            "last_active": pir1_ts,
        },
        "pir2": {
            "connected": _sensor_connected(reading.get("pir2") if reading else None),
            "last_active": pir2_ts,
        },
        "dht22": {
            "connected": _sensor_connected(
                reading.get("temperature") if reading else None
            ),
            "last_reading": last_ts,
        },
        "ldr": {
            "connected": _sensor_connected(reading.get("light") if reading else None),
            "last_reading": last_ts,
        },
        "ultrasonic": {
            "connected": _sensor_connected(
                reading.get("distance") if reading else None
            ),
            "last_reading": last_ts,
        },
        "camera": {
            "connected": _camera_available(),
            "status": "Available" if _camera_available() else "Not Connected",
        },
    }

    return jsonify({
        "mode": _current_mode,
        "system_online": system_online,
        "mqtt_connected": mqtt_connected,
        "last_reading_time": last_ts,
        "sensors": sensors,
    })


# ---------------------------------------------------------------------------
# Routes – Sensor readings
# ---------------------------------------------------------------------------
@app.route("/api/sensors/latest", methods=["GET"])
def get_latest():
    with _state_lock:
        reading = _latest_reading
        pir1_ts = _last_pir1_motion

    if reading is None:
        return jsonify({"error": "No sensor data available", "waiting": True})

    settings = database.get_settings()
    temp = reading.get("temperature")
    hum = reading.get("humidity")

    # Occupancy status
    occ_status = "No Recent Motion"
    inactivity = float(settings.get("inactivity_timeout", 300))
    if pir1_ts:
        try:
            ts = datetime.fromisoformat(pir1_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age < 30:
                occ_status = "Occupied"
            elif age < inactivity:
                occ_status = "Possibly Occupied"
        except (ValueError, TypeError):
            pass
    if reading.get("pir1") or reading.get("pir2"):
        occ_status = "Occupied"

    # Temp status
    temp_status = "normal"
    if temp is not None:
        if temp > float(settings.get("temp_max", 35)):
            temp_status = "critical"
        elif temp < float(settings.get("temp_min", 18)):
            temp_status = "warning"

    # Humidity status
    hum_status = "normal"
    if hum is not None:
        if (hum > float(settings.get("humidity_max", 80))
                or hum < float(settings.get("humidity_min", 30))):
            hum_status = "warning"

    result = {
        **reading,
        "occupancy_status": occ_status,
        "temp_status": temp_status,
        "humidity_status": hum_status,
        "light_status": reading.get("light", "Unknown"),
        "distance_status": "normal",
    }
    return jsonify(result)


@app.route("/api/sensors/history", methods=["GET"])
def get_history():
    period = request.args.get("period")
    sensor = request.args.get("sensor")
    start = request.args.get("start")
    end = request.args.get("end")
    limit = min(int(request.args.get("limit", 500)), 5000)
    offset = int(request.args.get("offset", 0))

    now = datetime.now(timezone.utc)
    if period:
        mapping = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
        hours = mapping.get(period, 1)
        start = (now - timedelta(hours=hours)).isoformat()
        end = now.isoformat()

    source = _current_mode
    readings = database.get_history(sensor=sensor, start=start, end=end,
                                    limit=limit, offset=offset, source=source)
    total = database.get_readings_count(sensor=sensor, start=start, end=end,
                                        source=source)

    return jsonify({
        "readings": readings,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


# ---------------------------------------------------------------------------
# Routes – Alerts
# ---------------------------------------------------------------------------
@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    status = request.args.get("status")
    if status == "all":
        status = None
    limit = int(request.args.get("limit", 50))
    alerts = database.get_alerts(status=status, limit=limit)
    return jsonify({"alerts": alerts})


@app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id):
    ok = database.resolve_alert(alert_id)
    if ok:
        return jsonify({"success": True})
    return jsonify({"error": "Alert not found"}), 404


# ---------------------------------------------------------------------------
# Routes – Events
# ---------------------------------------------------------------------------
@app.route("/api/events", methods=["GET"])
def get_events():
    limit = int(request.args.get("limit", 50))
    events = database.get_events(limit=limit)
    return jsonify({"events": events})


# ---------------------------------------------------------------------------
# Routes – Camera
# ---------------------------------------------------------------------------
@app.route("/api/camera/latest", methods=["GET"])
def camera_latest():
    img_dir = config.CAPTURED_IMAGES_DIR
    if not os.path.isdir(img_dir):
        return jsonify({
            "available": False,
            "camera_status": "No images available",
            "message": ("No captured images found. Images will appear here "
                        "when the Raspberry Pi camera captures them upon "
                        "motion detection."),
        })

    images = sorted(
        [f for f in os.listdir(img_dir)
         if f.lower().endswith((".jpg", ".jpeg", ".png"))],
        reverse=True,
    )

    if not images:
        return jsonify({
            "available": False,
            "camera_status": "No images available",
            "message": ("No captured images found. Images will appear here "
                        "when the Raspberry Pi camera captures them upon "
                        "motion detection."),
        })

    newest = images[0]
    mtime = os.path.getmtime(os.path.join(img_dir, newest))
    ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    return jsonify({
        "available": True,
        "image_url": f"/captured_images/{newest}",
        "timestamp": ts,
        "camera_status": "Available",
    })


@app.route("/captured_images/<path:filename>")
def serve_captured_image(filename):
    return send_from_directory(config.CAPTURED_IMAGES_DIR, filename)


# ---------------------------------------------------------------------------
# Routes – Settings
# ---------------------------------------------------------------------------
@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(database.get_settings())


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json(silent=True) or {}
    valid_keys = set(config.DEFAULT_SETTINGS.keys())
    cleaned = {}
    for k, v in data.items():
        if k in valid_keys:
            try:
                cleaned[k] = float(v)
            except (ValueError, TypeError):
                cleaned[k] = v
    if cleaned:
        database.update_settings(cleaned)
    return jsonify(database.get_settings())


# ---------------------------------------------------------------------------
# Routes – CSV export
# ---------------------------------------------------------------------------
@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    start = request.args.get("start")
    end = request.args.get("end")
    sensor = request.args.get("sensor")
    source = request.args.get("source", _current_mode)

    readings = database.get_history(sensor=sensor, start=start, end=end,
                                    limit=50000, offset=0, source=source)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "Temperature (°C)", "Humidity (%)", "Light Level",
        "Light Raw", "Distance (cm)", "PIR 1", "PIR 2", "Source",
    ])
    for r in readings:
        writer.writerow([
            r.get("timestamp", ""),
            r.get("temperature", ""),
            r.get("humidity", ""),
            r.get("light", ""),
            r.get("light_raw", ""),
            r.get("distance", ""),
            r.get("pir1", ""),
            r.get("pir2", ""),
            r.get("source", ""),
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = (
        "attachment; filename=classroom_readings.csv"
    )
    return response


# ---------------------------------------------------------------------------
# Helper – camera availability
# ---------------------------------------------------------------------------
def _camera_available() -> bool:
    img_dir = config.CAPTURED_IMAGES_DIR
    if not os.path.isdir(img_dir):
        return False
    return any(f.lower().endswith((".jpg", ".jpeg", ".png"))
               for f in os.listdir(img_dir))


# ---------------------------------------------------------------------------
# Mode management
# ---------------------------------------------------------------------------
def _start_demo():
    global _demo_generator
    _demo_generator = DemoDataGenerator(
        _on_sensor_reading, config.DEMO_UPDATE_INTERVAL
    )
    # Pre-populate historical data if database doesn't have sufficient historical records
    count = database.get_readings_count(source="demo")
    if count < 50:
        log.info("Generating 24 h of demo historical data …")
        historical = _demo_generator.generate_historical_data(hours=24)
        database.save_readings_batch(historical, source="demo")
        # Only run alert checks on recent subset to avoid flooding
        recent = historical[-20:] if len(historical) > 20 else historical
        for r in recent:
            _alert_manager.check_reading(r, source="demo")
        log.info("Inserted %d historical demo readings", len(historical))
    _demo_generator.start()


def _start_live():
    global _mqtt_handler
    _mqtt_handler = MQTTHandler(
        config.MQTT_BROKER_HOST,
        config.MQTT_BROKER_PORT,
        config.MQTT_TOPIC,
        _on_sensor_reading,
    )
    _mqtt_handler.connect()


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------
def main():
    database.init_db()

    if _current_mode == "demo":
        _start_demo()
    else:
        _start_live()

    log.info("Starting Smart Classroom Monitor (mode=%s) on 0.0.0.0:5000",
             _current_mode)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

