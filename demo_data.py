"""
Smart Classroom Monitor – Demo Data Generator
==============================================
Produces realistic simulated sensor readings for demonstration when
physical hardware is not connected.  Readings drift naturally rather
than jumping randomly.
"""

import logging
import math
import random
import threading
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


class DemoDataGenerator:
    """Background thread that emits simulated sensor readings at a fixed
    interval."""

    def __init__(self, on_reading_callback, interval: float = 4.0):
        self._callback = on_reading_callback
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # --- Internal state for continuity ---
        self._base_temp = random.uniform(26.0, 28.0)
        self._base_humidity = random.uniform(55.0, 65.0)
        self._light_state = random.choice(["Bright", "Moderate", "Dark"])
        self._light_raw = {"Bright": 800, "Moderate": 500, "Dark": 150}[
            self._light_state
        ]
        self._distance = random.uniform(50.0, 150.0)
        self._classroom_occupied = True
        self._occupied_since = time.time()
        self._tick = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start generating readings in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="demo-data")
        self._thread.start()
        log.info("Demo data generator started (interval=%.1fs)", self._interval)

    def stop(self):
        """Signal the generator to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Demo data generator stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def generate_historical_data(self, hours: int = 24) -> list[dict]:
        """Return a list of readings spanning the last *hours* at ~30-s
        intervals.  Useful for pre-populating the database on first run."""
        readings = []
        now = datetime.now(timezone.utc)
        interval_s = 30
        n_points = int((hours * 3600) / interval_s)

        temp = random.uniform(25.0, 28.0)
        hum = random.uniform(50.0, 65.0)
        light_states = ["Bright", "Moderate", "Dark"]
        light_idx = 0
        dist = random.uniform(60.0, 140.0)
        occupied = True
        occ_counter = 0

        for i in range(n_points):
            ts = now - timedelta(seconds=(n_points - i) * interval_s)

            # Drift temperature with a slight sine wave (day-night cycle)
            hour_frac = (ts.hour + ts.minute / 60) / 24
            temp += random.gauss(0, 0.15)
            temp += 0.05 * math.sin(2 * math.pi * hour_frac)
            temp = max(20.0, min(38.0, temp))

            # Humidity inversely correlates with temp
            hum += random.gauss(0, 0.3)
            hum -= 0.1 * (temp - 27.0)
            hum = max(25.0, min(90.0, hum))

            # Light changes every ~30 min during day, dark at night
            if i % 60 == 0:
                if 8 <= ts.hour <= 18:
                    light_idx = random.choice([0, 0, 1])
                else:
                    light_idx = random.choice([1, 2, 2])
            light_str = light_states[light_idx]
            light_raw_map = {"Bright": random.randint(700, 950),
                             "Moderate": random.randint(300, 699),
                             "Dark": random.randint(30, 299)}

            # Occupancy cycle: occupied for ~1-2h, then empty for ~30min
            occ_counter += 1
            if occupied and occ_counter > random.randint(120, 240):
                occupied = False
                occ_counter = 0
            elif not occupied and occ_counter > random.randint(30, 60):
                occupied = True
                occ_counter = 0
            # No occupancy at night
            if ts.hour < 7 or ts.hour > 21:
                occupied = False

            pir1 = random.random() < (0.6 if occupied else 0.02)
            pir2 = random.random() < (0.5 if occupied else 0.02)

            dist += random.gauss(0, 2)
            if occupied:
                dist = max(15.0, min(120.0, dist))
            else:
                dist = max(80.0, min(300.0, dist))

            readings.append({
                "timestamp": ts.isoformat(),
                "temperature": round(temp, 1),
                "humidity": round(hum, 1),
                "light": light_str,
                "light_raw": light_raw_map[light_str],
                "distance": round(dist, 1),
                "pir1": pir1,
                "pir2": pir2,
            })

        return readings

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self):
        while not self._stop_event.is_set():
            reading = self._generate_reading()
            if self._callback:
                try:
                    self._callback(reading)
                except Exception:
                    log.exception("Error in demo reading callback")
            self._stop_event.wait(self._interval)

    def _generate_reading(self) -> dict:
        self._tick += 1

        # --- Occupancy state machine ---
        if self._tick % 80 == 0:
            self._classroom_occupied = not self._classroom_occupied
            self._occupied_since = time.time()
        # Random flip with low probability
        if random.random() < 0.01:
            self._classroom_occupied = not self._classroom_occupied

        # --- Temperature drift ---
        self._base_temp += random.gauss(0, 0.12)
        # Slight upward pressure when occupied
        if self._classroom_occupied:
            self._base_temp += 0.02
        else:
            self._base_temp -= 0.01
        self._base_temp = max(20.0, min(38.0, self._base_temp))

        # --- Humidity drift (inverse to temp) ---
        self._base_humidity += random.gauss(0, 0.2)
        self._base_humidity -= 0.05 * (self._base_temp - 27)
        self._base_humidity = max(25.0, min(90.0, self._base_humidity))

        # --- Light ---
        if self._tick % 30 == 0 or random.random() < 0.03:
            choices = ["Bright", "Moderate", "Dark"]
            weights = (
                [0.6, 0.3, 0.1] if self._classroom_occupied else [0.2, 0.3, 0.5]
            )
            self._light_state = random.choices(choices, weights=weights, k=1)[0]
        raw_map = {"Bright": random.randint(720, 950),
                   "Moderate": random.randint(320, 690),
                   "Dark": random.randint(30, 280)}
        self._light_raw = raw_map[self._light_state]

        # --- Distance ---
        self._distance += random.gauss(0, 1.5)
        if self._classroom_occupied:
            self._distance = max(10.0, min(150.0, self._distance))
        else:
            self._distance = max(60.0, min(350.0, self._distance))

        # --- PIR ---
        pir1 = random.random() < (0.55 if self._classroom_occupied else 0.03)
        pir2 = random.random() < (0.45 if self._classroom_occupied else 0.03)

        # --- Occasional glitch (1 in 50) ---
        reading: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": round(self._base_temp, 1),
            "humidity": round(self._base_humidity, 1),
            "light": self._light_state,
            "light_raw": self._light_raw,
            "distance": round(self._distance, 1),
            "pir1": pir1,
            "pir2": pir2,
        }

        if random.random() < 0.02:
            glitch_key = random.choice(
                ["temperature", "humidity", "distance", "light"]
            )
            reading[glitch_key] = None
            if glitch_key == "light":
                reading["light_raw"] = None

        return reading

