# Smart Classroom Monitoring System – Web Dashboard

**IoT-Based Classroom Environment and Occupancy Monitoring System**

A full-stack, local-network IoT web application designed for academic college demonstrations and real-world classroom monitoring. The system displays environmental and occupancy data collected by sensors connected to a **Raspberry Pi 3 Model B**, relayed over **MQTT** to a **Flask backend** on a central laptop, and visualized on a modern responsive web dashboard.

---

## 1. System Architecture & Data Flow

```
+-------------------------------------------------------------+
|               HARDWARE LAYER (Raspberry Pi 3 Model B)       |
|                                                             |
|  [2x PIR Sensors]  [HC-SR04 Sonar]  [DHT22]  [LDR Sensor]   |
|        |                  |            |          |         |
|        +------------------+------------+----------+         |
|                           |                                 |
|                  pi_publisher.py (Python)                   |
|              [Pi Camera V2 Snapshot on Motion]              |
+---------------------------+---------------------------------+
                            | Wi-Fi (MQTT JSON)
                            v
+-------------------------------------------------------------+
|              COMMUNICATION LAYER (Central Laptop)           |
|                                                             |
|             Mosquitto MQTT Broker (Port 1883)               |
|               Topic: "classroom/sensors"                    |
+---------------------------+---------------------------------+
                            | Paho-MQTT Subscription
                            v
+-------------------------------------------------------------+
|               BACKEND LAYER (Flask / Python)                |
|                                                             |
|  mqtt_handler.py <---> app.py (REST APIs) <---> demo_data.py|
|          |                 |                                |
|          +--------> database.py (SQLite)                    |
|                            |                                |
|                      classroom.db                           |
+---------------------------+---------------------------------+
                            | HTTP REST / Polling (JSON)
                            v
+-------------------------------------------------------------+
|               FRONTEND LAYER (Responsive SPA)               |
|                                                             |
|  - HTML5 & CSS3 (Modern Light Theme, Dark Navy Sidebar)     |
|  - Vanilla JavaScript Engine (Hash Router, Auto-Refresh)    |
|  - Chart.js 4.x (5 Interactive Environmental Graphs)        |
|  - Responsive Mobile Navigation Drawer                      |
+-------------------------------------------------------------+
```

### Complete End-to-End Data Flow:
1. **Sensor Measurement**: On the Raspberry Pi, `pi_publisher.py` reads temperature and humidity from the DHT22, distance from the HC-SR04 ultrasonic transducer, motion states from PIR 1 and PIR 2, and ambient illumination from the LDR.
2. **Visual Capture**: If motion is detected by either PIR sensor, the Raspberry Pi Camera Module V2 captures a high-resolution snapshot.
3. **MQTT Transmission**: The readings are serialized into a standardized JSON payload and published over the local Wi-Fi network to the Mosquitto broker on topic `classroom/sensors`.
4. **Backend Reception & Persistence**: The Flask backend subscribes to `classroom/sensors` using `paho-mqtt`. Incoming readings are validated for range and sanity, saved to SQLite (`sensor_readings` table), and checked against configurable threshold rules via `alert_manager.py`.
5. **Dashboard Consumption**: The browser frontend periodically polls `/api/sensors/latest`, `/api/status`, and `/api/alerts` to refresh live cards, system health indicators, and active warnings without reloading the page.

---

## 2. Directory Structure

```
iot_project/
├── app.py                  # Flask web server & REST API controller
├── mqtt_handler.py         # Paho-MQTT v2 subscriber client & data validator
├── demo_data.py            # Realistic sensor data generator for Demo Mode
├── alert_manager.py        # Automated rule checking, alert & event generation
├── database.py             # SQLite ORM & thread-safe data operations
├── config.py               # Central configuration constants and default thresholds
├── requirements.txt        # Python dependency specifications
├── pi_publisher.py         # Raspberry Pi 3 Model B hardware sensor driver
├── mock_publisher.py       # Standalone test publisher for Live Mode testing
├── templates/
│   └── index.html          # Complete Single-Page Application interface
├── static/
│   ├── css/
│   │   └── style.css       # Clean, modern, responsive stylesheet
│   ├── js/
│   │   └── dashboard.js    # Client-side router, Chart.js & API integration
│   └── images/             # Static UI assets
├── captured_images/        # Storage directory for camera snapshots
└── classroom.db            # SQLite database (auto-generated on first run)
```

---

## 3. Sensor Wiring & Raspberry Pi Pinout

| Sensor Component | Physical Pin | BCM GPIO | Description |
| :--- | :--- | :--- | :--- |
| **PIR Motion Sensor 1** | Pin 11 | GPIO 17 | Front/Zone A occupancy motion input |
| **PIR Motion Sensor 2** | Pin 13 | GPIO 27 | Rear/Zone B occupancy motion input |
| **HC-SR04 Ultrasonic Trigger** | Pin 16 | GPIO 23 | 10µs trigger pulse output |
| **HC-SR04 Ultrasonic Echo** | Pin 18 | GPIO 24 | Echo pulse input (*use 1k/2k voltage divider*) |
| **DHT22 Data Pin** | Pin 7 | GPIO 4 | Digital 1-wire temperature & humidity input |
| **LDR Light Sensor** | Pin 12 | GPIO 18 | RC circuit timing or ADC input |
| **Pi Camera Module V2** | CSI Port | Ribbon Cable | Dedicated camera serial interface |

> [!IMPORTANT]
> **Voltage Divider for HC-SR04 Echo**: The HC-SR04 Echo pin outputs 5V logic. Raspberry Pi GPIO pins accept a maximum of 3.3V. Always use a simple resistor voltage divider (e.g., 1 kΩ in series with a 2 kΩ resistor to GND) between the Echo pin and GPIO 24 to protect the Raspberry Pi.

---

## 4. Setup and Installation

### A. Laptop (Central Server) Prerequisites
Ensure **Python 3.10+** and the **Mosquitto MQTT Broker** are installed on the laptop.

#### 1. Install Mosquitto Broker
- **Windows**: Download the official installer from [mosquitto.org](https://mosquitto.org/download/).
  Run the installer and make sure the Mosquitto service is running:
  ```powershell
  # Start Mosquitto in Windows PowerShell
  net start mosquitto
  ```
  *Tip: Ensure your `mosquitto.conf` contains:*
  ```text
  listener 1883
  allow_anonymous true
  ```
- **Linux/macOS**:
  ```bash
  sudo apt-get install mosquitto mosquitto-clients
  sudo systemctl start mosquitto
  ```

#### 2. Install Python Dependencies
Open PowerShell or your terminal in the project directory:
```powershell
cd d:\Projects\iot_project
pip install -r requirements.txt
```

#### 3. Find Your Laptop's Local Wi-Fi IP Address
Both the laptop and Raspberry Pi must be on the **same Wi-Fi network**.
- **Windows**:
  ```powershell
  ipconfig
  ```
  Look for `IPv4 Address` under your Wi-Fi adapter (e.g., `192.168.1.100`).
- **Linux**:
  ```bash
  hostname -I
  ```

---

## 5. Running the Application

### Step 1: Start the Flask Backend Server
In Windows PowerShell or terminal:
```powershell
python app.py
```
Output:
```
[INFO] database: Database initialised at d:\Projects\iot_project\classroom.db
[INFO] demo_data: Demo data generator started (interval=4.0s)
[INFO] app: Starting Smart Classroom Monitor (mode=demo) on 0.0.0.0:5000
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.1.100:5000
```

### Step 2: Access the Web Dashboard
- **From the Laptop**: Open your browser and navigate to:
  ```
  http://localhost:5000
  ```
- **From a Mobile Phone or Tablet (on the same Wi-Fi)**:
  Open the mobile browser and navigate to:
  ```
  http://<YOUR_LAPTOP_IP>:5000
  (e.g., http://192.168.1.100:5000)
  ```

---

## 6. Operating Modes: Demo Mode vs. Live Mode

The application includes two distinct, switchable operating modes:

### 1. Demo Mode (Default)
Ideal for testing, grading evaluations, and offline presentations when physical sensors are not present:
- Displays a visible **DEMO MODE** badge in the header.
- Automatically seeds 24 hours of realistic historical data on first launch.
- Continuous background generator simulates natural sensor drift:
  - Temperature drifts smoothly between 24°C and 35°C.
  - Humidity shifts inversely with temperature between 35% and 80%.
  - PIR sensors simulate classroom entry, active discussion, and inactivity periods.
  - Generates realistic warnings when thresholds are crossed.

### 2. Live Mode
Connects directly to the physical Raspberry Pi or local Mosquitto MQTT broker:
- Switch to **Live Mode** via the dropdown selector in the top-right header or Settings page.
- Subscribes to the MQTT topic `classroom/sensors`.
- If no sensor data is received, the dashboard shows **"Waiting for sensor data..."** and displays connection status.
- Real sensor readings are stored in SQLite and flagged with `source='live'`.

---

## 7. Testing Without Hardware: Mock Publisher

To test **Live Mode** and MQTT messaging without Raspberry Pi hardware:

1. Keep the Flask server running in your first terminal.
2. Ensure the Mosquitto broker is running (`net start mosquitto`).
3. Switch the web dashboard to **Live Mode** using the header dropdown.
4. Open a second terminal window and run:
   ```powershell
   python mock_publisher.py
   ```
5. You will see realistic JSON payloads being published to `classroom/sensors` and immediately reflected on your dashboard cards, charts, and activity log!

---

## 8. Raspberry Pi Deployment (`pi_publisher.py`)

When ready to connect the physical hardware:

1. Copy `pi_publisher.py` to your Raspberry Pi:
   ```bash
   scp pi_publisher.py pi@<PI_IP>:~/
   ```
2. SSH into your Raspberry Pi:
   ```bash
   ssh pi@<PI_IP>
   ```
3. Install the required hardware packages on the Pi:
   ```bash
   sudo apt-get update
   sudo apt-get install python3-pip python3-picamera
   pip3 install paho-mqtt Adafruit_DHT RPi.GPIO
   ```
4. Set the laptop's Wi-Fi IP address in `pi_publisher.py` or pass it as an environment variable:
   ```bash
   export MQTT_BROKER="192.168.1.100"   # Replace with your laptop IP
   python3 pi_publisher.py
   ```

---

## 9. REST API Reference

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/api/status` | `GET` | Overall system online status, MQTT connectivity, sensor health |
| `/api/mode` | `GET` | Returns current operating mode (`"demo"` or `"live"`) |
| `/api/mode` | `POST` | Switches mode: `{"mode": "demo"}` or `{"mode": "live"}` |
| `/api/sensors/latest` | `GET` | Most recent reading with derived occupancy & comfort status |
| `/api/sensors/history` | `GET` | Time-series data with filters (`?period=1h\|6h\|24h\|7d&limit=300`) |
| `/api/alerts` | `GET` | List active or resolved alerts (`?status=active\|resolved`) |
| `/api/alerts/<id>/resolve` | `POST`| Marks a specific alert as resolved |
| `/api/events` | `GET` | Recent system activity log (PIR triggers, threshold crossings) |
| `/api/camera/latest` | `GET` | Latest motion-triggered camera capture metadata & URL |
| `/captured_images/<file>`| `GET` | Serves motion snapshot images |
| `/api/settings` | `GET` | Retrieves current warning thresholds and timeouts |
| `/api/settings` | `POST`| Updates user-configured thresholds and intervals |
| `/api/export/csv` | `GET` | Exports sensor records as a downloadable `.csv` file |

---

## 10. Troubleshooting & Common Questions

### 1. "Broker Connecting..." or MQTT Disconnected in Live Mode
- Ensure Mosquitto service is running (`net start mosquitto` on Windows or `sudo systemctl status mosquitto` on Linux).
- Verify that Windows Firewall allows inbound connections on TCP port `1883`. Run in administrative PowerShell:
  ```powershell
  New-NetFirewallRule -DisplayName "Mosquitto MQTT" -Direction Inbound -LocalPort 1883 -Protocol TCP -Action Allow
  ```
- In `C:\Program Files\mosquitto\mosquitto.conf`, ensure `listener 1883` and `allow_anonymous true` are present.

### 2. Cannot Access Dashboard from Mobile Phone
- Confirm both the laptop and phone are on the **exact same Wi-Fi SSID** (avoid guest networks with client isolation).
- Allow Python Flask through Windows Firewall on port 5000:
  ```powershell
  New-NetFirewallRule -DisplayName "Flask Web App" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
  ```

### 3. Occupancy Estimation Clarity
- PIR sensors detect differential infrared changes from human movement. They do not count exact heads. The dashboard explicitly indicates:
  - **Occupied**: Motion actively detected within the last 30 seconds.
  - **Possibly Occupied**: Intermittent motion within the inactivity window.
  - **No Recent Motion**: Room has had no detected movement beyond the configured timeout.

---

## 11. Academic Project Credits
- **Course**: IoT & Embedded Systems Laboratory
- **Platform**: Raspberry Pi 3 Model B & Mosquitto MQTT
- **Backend**: Python 3 / Flask / SQLite
- **Frontend**: HTML5 / CSS3 / Vanilla JS / Chart.js

