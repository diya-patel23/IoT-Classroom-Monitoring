"""
Smart Classroom Monitor – Alert Manager
========================================
Checks every incoming sensor reading against configurable thresholds and
generates alerts / events when anomalies are detected.  Automatically
resolves alerts when conditions return to normal.
"""

import logging
import time
from datetime import datetime, timezone

import database

log = logging.getLogger(__name__)

# Minimum seconds between repeated alerts of the same type
_COOLDOWN = 300  # 5 minutes


class AlertManager:
    """Stateful alert engine – tracks conditions to avoid duplicate alerts
    and auto-resolves when conditions normalise."""

    def __init__(self):
        # Track timestamps of last alert per category to enforce cooldowns
        self._last_alert_time: dict[str, float] = {}
        # Previous sensor states for detecting transitions
        self._prev_pir1: bool | None = None
        self._prev_pir2: bool | None = None
        self._prev_light: str | None = None
        self._prev_temp_status: str | None = None
        self._prev_humidity_status: str | None = None
        self._last_motion_time: float = time.time()
        self._prev_had_temp: bool = True
        self._prev_had_humidity: bool = True
        self._prev_had_distance: bool = True
        self._prev_had_light: bool = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_reading(self, reading: dict, source: str = "demo"):
        """Evaluate a single reading against all alert rules."""
        settings = database.get_settings()
        now = time.time()

        temp = reading.get("temperature")
        hum = reading.get("humidity")
        light = reading.get("light")
        dist = reading.get("distance")
        pir1 = reading.get("pir1")
        pir2 = reading.get("pir2")

        # ---- Motion tracking ----
        if pir1 or pir2:
            self._last_motion_time = now

        # ---- 1. Temperature alerts ----
        if temp is not None:
            temp_max = float(settings.get("temp_max", 35))
            temp_min = float(settings.get("temp_min", 18))

            if temp > temp_max:
                self._maybe_alert(
                    key="temp_high",
                    title="High Temperature Warning",
                    description=f"Temperature is {temp}°C, exceeding the configured maximum of {temp_max}°C.",
                    severity="high",
                    sensor="dht22",
                    source=source,
                )
                self._prev_temp_status = "high"
            elif temp < temp_min:
                self._maybe_alert(
                    key="temp_low",
                    title="Low Temperature Warning",
                    description=f"Temperature is {temp}°C, below the configured minimum of {temp_min}°C.",
                    severity="medium",
                    sensor="dht22",
                    source=source,
                )
                self._prev_temp_status = "low"
            else:
                # Auto-resolve temperature alerts
                if self._prev_temp_status in ("high", "low"):
                    self._auto_resolve("Temperature", source)
                self._prev_temp_status = "normal"

        # ---- 2. Humidity alerts ----
        if hum is not None:
            hum_max = float(settings.get("humidity_max", 80))
            hum_min = float(settings.get("humidity_min", 30))

            if hum > hum_max:
                self._maybe_alert(
                    key="hum_high",
                    title="High Humidity Warning",
                    description=f"Humidity is {hum}%, exceeding the configured maximum of {hum_max}%.",
                    severity="medium",
                    sensor="dht22",
                    source=source,
                )
                self._prev_humidity_status = "high"
            elif hum < hum_min:
                self._maybe_alert(
                    key="hum_low",
                    title="Low Humidity Warning",
                    description=f"Humidity is {hum}%, below the configured minimum of {hum_min}%.",
                    severity="low",
                    sensor="dht22",
                    source=source,
                )
                self._prev_humidity_status = "low"
            else:
                if self._prev_humidity_status in ("high", "low"):
                    self._auto_resolve("Humidity", source)
                self._prev_humidity_status = "normal"

        # ---- 3. Inactivity alert ----
        inactivity_timeout = float(settings.get("inactivity_timeout", 300))
        elapsed_since_motion = now - self._last_motion_time

        if elapsed_since_motion > inactivity_timeout:
            self._maybe_alert(
                key="inactive",
                title="Classroom Inactive",
                description=(
                    f"No motion has been detected for "
                    f"{int(elapsed_since_motion // 60)} minutes."
                ),
                severity="low",
                sensor="pir",
                source=source,
            )
        else:
            self._auto_resolve("Inactive", source)

        # ---- 4. Lights possibly left on ----
        if (elapsed_since_motion > inactivity_timeout
                and light == "Bright"):
            self._maybe_alert(
                key="lights_on",
                title="Possible Lights Left On",
                description=(
                    "Classroom appears inactive but ambient brightness is high. "
                    "This may indicate that lights have been left on, though the "
                    "LDR measures ambient light and cannot confirm the electrical "
                    "state of lighting."
                ),
                severity="medium",
                sensor="ldr",
                source=source,
            )
        elif light != "Bright" or elapsed_since_motion <= inactivity_timeout:
            self._auto_resolve("Lights", source)

        # ---- 5. Sensor reading unavailable ----
        self._check_sensor_availability("temperature", temp, "dht22",
                                        self._prev_had_temp, source)
        self._prev_had_temp = temp is not None

        self._check_sensor_availability("humidity", hum, "dht22",
                                        self._prev_had_humidity, source)
        self._prev_had_humidity = hum is not None

        self._check_sensor_availability("distance", dist, "ultrasonic",
                                        self._prev_had_distance, source)
        self._prev_had_distance = dist is not None

        self._check_sensor_availability("light", light, "ldr",
                                        self._prev_had_light, source)
        self._prev_had_light = light is not None

        # ---- Events for state transitions ----
        self._check_motion_events(pir1, pir2, source)
        self._check_light_event(light, source)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_alert(self, *, key: str, title: str, description: str,
                     severity: str, sensor: str, source: str):
        """Create an alert only if the cooldown has elapsed."""
        now = time.time()
        last = self._last_alert_time.get(key, 0)
        if now - last < _COOLDOWN:
            return
        database.save_alert(title, description, severity, sensor, source)
        self._last_alert_time[key] = now
        log.info("Alert created: %s [%s]", title, severity)

    def _auto_resolve(self, keyword: str, source: str):
        """Resolve active alerts whose title contains *keyword*."""
        active = database.get_alerts(status="active", limit=100)
        for alert in active:
            if keyword.lower() in alert["title"].lower() and alert.get("source") == source:
                database.resolve_alert(alert["id"])
                log.info("Auto-resolved alert #%s: %s", alert["id"], alert["title"])

    def _check_sensor_availability(self, name, value, sensor_name,
                                   previously_available, source):
        """Alert when a previously available sensor starts returning None."""
        if value is None and previously_available:
            self._maybe_alert(
                key=f"sensor_{name}",
                title=f"Sensor Reading Unavailable – {name.title()}",
                description=f"The {sensor_name} sensor did not return a valid {name} reading.",
                severity="medium",
                sensor=sensor_name,
                source=source,
            )
        elif value is not None and not previously_available:
            # Sensor recovered – resolve
            self._auto_resolve(f"Unavailable – {name.title()}", source)
            database.save_event(
                f"Sensor communication restored – {name}",
                sensor=sensor_name,
                reading=str(value),
                source=source,
            )

    def _check_motion_events(self, pir1, pir2, source):
        """Log events when PIR sensors detect new motion."""
        if pir1 and not self._prev_pir1:
            database.save_event("Motion detected", sensor="PIR 1",
                                reading="Active", source=source)
        if pir2 and not self._prev_pir2:
            database.save_event("Motion detected", sensor="PIR 2",
                                reading="Active", source=source)
        self._prev_pir1 = pir1
        self._prev_pir2 = pir2

    def _check_light_event(self, light, source):
        """Log an event when the brightness state changes."""
        if light and self._prev_light and light != self._prev_light:
            database.save_event(
                f"Brightness level changed from {self._prev_light} to {light}",
                sensor="LDR",
                reading=light,
                source=source,
            )
        self._prev_light = light

