/**
 * Smart Classroom Monitor - Frontend Application Logic
 * Single-Page Architecture with Chart.js, REST API polling, and Live/Demo Mode support.
 */

(function () {
  'use strict';

  // State
  let currentMode = 'demo';
  let currentPage = 'dashboard';
  let refreshIntervalMs = 5000;
  let refreshTimer = null;
  let chartPeriod = '1h';
  let activeAlertFilter = 'all';

  // History pagination state
  let historyPage = 1;
  const historyPageSize = 25;

  // Chart references
  let charts = {
    temp: null,
    humidity: null,
    light: null,
    distance: null,
    motion: null
  };

  // -------------------------------------------------------------
  // Initialisation
  // -------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    setupMobileMenu();
    setupModeSelector();
    setupChartFilters();
    setupAlertFilters();
    setupHistoryControls();
    setupSettingsForm();

    initCharts();

    // Route initial page from URL hash or default
    const hashPage = window.location.hash.replace('#', '') || 'dashboard';
    switchPage(hashPage);

    // Initial data fetch
    fetchSystemStatus();
    fetchLatestReadings();
    fetchHistoryChartData(chartPeriod);
    fetchEvents();
    fetchSettings();

    // Start auto-refresh
    startPolling();
  });

  // -------------------------------------------------------------
  // Router & Navigation
  // -------------------------------------------------------------
  function setupNavigation() {
    window.addEventListener('hashchange', () => {
      const page = window.location.hash.replace('#', '') || 'dashboard';
      switchPage(page);
    });

    document.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', (e) => {
        const targetPage = link.getAttribute('data-page');
        if (targetPage) {
          window.location.hash = targetPage;
          closeMobileMenu();
        }
      });
    });
  }

  function switchPage(pageName) {
    const validPages = ['dashboard', 'alerts', 'sensors', 'camera', 'history', 'settings'];
    const page = validPages.includes(pageName) ? pageName : 'dashboard';
    currentPage = page;

    // Update active section
    document.querySelectorAll('.page').forEach(sec => sec.classList.remove('active'));
    const targetSection = document.getElementById(`page-${page}`);
    if (targetSection) targetSection.classList.add('active');

    // Update active nav link
    document.querySelectorAll('.nav-link').forEach(link => {
      link.classList.toggle('active', link.getAttribute('data-page') === page);
    });

    // Update top header title
    const titles = {
      dashboard: 'Classroom Overview',
      alerts: 'Alerts & Notifications',
      sensors: 'Hardware Sensors Information',
      camera: 'Camera Motion Monitoring',
      history: 'Historical Sensor Records',
      settings: 'System & Threshold Settings'
    };
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = titles[page] || 'Dashboard';

    // Page-specific initial load
    if (page === 'alerts') fetchAlerts();
    if (page === 'sensors') fetchSensorDetails();
    if (page === 'camera') fetchCameraStatus();
    if (page === 'history') loadHistoryTable();
    if (page === 'settings') fetchSettings();
  }

  function setupMobileMenu() {
    const btn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (btn && sidebar && overlay) {
      btn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('active');
      });
      overlay.addEventListener('click', closeMobileMenu);
    }
  }

  function closeMobileMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
  }

  // -------------------------------------------------------------
  // Mode Selector (Demo vs Live)
  // -------------------------------------------------------------
  function setupModeSelector() {
    const selector = document.getElementById('mode-selector');
    if (!selector) return;

    selector.addEventListener('change', async (e) => {
      const newMode = e.target.value;
      try {
        const res = await fetch('/api/mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: newMode })
        });
        const data = await res.json();
        if (data.success || data.mode) {
          currentMode = data.mode;
          applyModeUI(data.mode);
          // Refresh everything immediately
          fetchSystemStatus();
          fetchLatestReadings();
          fetchHistoryChartData(chartPeriod);
          fetchEvents();
          if (currentPage === 'alerts') fetchAlerts();
          if (currentPage === 'history') loadHistoryTable();
        }
      } catch (err) {
        console.error('Failed to change mode:', err);
      }
    });
  }

  function applyModeUI(mode) {
    const badge = document.getElementById('demo-badge');
    const selector = document.getElementById('mode-selector');
    if (selector) selector.value = mode;

    if (badge) {
      if (mode === 'demo') {
        badge.textContent = 'DEMO MODE';
        badge.style.display = 'inline-flex';
        badge.style.backgroundColor = '#fef3c7';
        badge.style.color = '#b45309';
        badge.style.borderColor = '#fde68a';
      } else {
        badge.textContent = 'LIVE MQTT';
        badge.style.display = 'inline-flex';
        badge.style.backgroundColor = '#ecfdf5';
        badge.style.color = '#047857';
        badge.style.borderColor = '#a7f3d0';
      }
    }
  }

  // -------------------------------------------------------------
  // Auto Polling Loop
  // -------------------------------------------------------------
  function startPolling() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      fetchSystemStatus();
      fetchLatestReadings();
      if (currentPage === 'dashboard') {
        fetchEvents();
      } else if (currentPage === 'alerts') {
        fetchAlerts();
      } else if (currentPage === 'sensors') {
        fetchSensorDetails();
      } else if (currentPage === 'camera') {
        fetchCameraStatus();
      }
    }, refreshIntervalMs);
  }

  // -------------------------------------------------------------
  // API Fetch: Status
  // -------------------------------------------------------------
  async function fetchSystemStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) throw new Error('Status endpoint failed');
      const data = await res.json();

      currentMode = data.mode || 'demo';
      applyModeUI(currentMode);

      // System online indicator
      const dot = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      if (dot && text) {
        if (data.system_online) {
          dot.className = 'status-dot online';
          text.textContent = currentMode === 'live'
            ? (data.mqtt_connected ? 'MQTT Connected' : 'Broker Connecting...')
            : 'System Online';
        } else {
          dot.className = 'status-dot offline';
          text.textContent = 'System Offline';
        }
      }

      // Last update text
      const lastUpdateEl = document.getElementById('last-update');
      if (lastUpdateEl) {
        if (data.last_reading_time) {
          const dt = new Date(data.last_reading_time);
          lastUpdateEl.textContent = `Last update: ${formatTime(dt)}`;
        } else {
          lastUpdateEl.textContent = 'Last update: Waiting...';
        }
      }

      // Update connectivity grid
      renderConnectivityGrid(data.sensors, data.mqtt_connected);

    } catch (err) {
      console.warn('Status poll error:', err);
      const dot = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      if (dot && text) {
        dot.className = 'status-dot offline';
        text.textContent = 'Backend Offline';
      }
    }
  }

  function renderConnectivityGrid(sensors, mqttConnected) {
    const grid = document.getElementById('connectivity-grid');
    if (!grid) return;

    if (!sensors) {
      grid.innerHTML = '<div class="conn-item">No sensor data available</div>';
      return;
    }

    const sensorConfig = [
      { key: 'pir1', name: 'PIR Motion 1', detail: 'GPIO Input 1' },
      { key: 'pir2', name: 'PIR Motion 2', detail: 'GPIO Input 2' },
      { key: 'dht22', name: 'DHT22 Temp/Humidity', detail: '1-Wire Digital' },
      { key: 'ldr', name: 'LDR Light Sensor', detail: 'Analog / ADC Pin' },
      { key: 'ultrasonic', name: 'HC-SR04 Ultrasonic', detail: 'Trigger / Echo' },
      { key: 'camera', name: 'Pi Camera V2', detail: 'CSI Ribbon Cable' }
    ];

    grid.innerHTML = sensorConfig.map(s => {
      const info = sensors[s.key] || { connected: false };
      const isOnline = Boolean(info.connected);
      const stateLabel = isOnline ? 'Connected' : 'Offline';
      const stateClass = isOnline ? 'online' : 'offline';

      return `
        <div class="conn-item">
          <div class="conn-header">
            <span class="conn-name">${s.name}</span>
            <span class="conn-state ${stateClass}">${stateLabel}</span>
          </div>
          <span class="conn-detail">${s.detail}</span>
        </div>
      `;
    }).join('');
  }

  // -------------------------------------------------------------
  // API Fetch: Latest Sensor Readings
  // -------------------------------------------------------------
  async function fetchLatestReadings() {
    const waitingMsg = document.getElementById('waiting-message');
    const liveReadingsBox = document.getElementById('live-readings');

    try {
      const res = await fetch('/api/sensors/latest');
      if (!res.ok) throw new Error('Failed to fetch latest readings');
      const data = await res.json();

      if (data.waiting || data.error) {
        if (waitingMsg) waitingMsg.style.display = 'flex';
        if (liveReadingsBox) liveReadingsBox.style.opacity = '0.4';
        return;
      }

      if (waitingMsg) waitingMsg.style.display = 'none';
      if (liveReadingsBox) liveReadingsBox.style.opacity = '1';

      // 1. Occupancy Card
      const occVal = document.getElementById('occupancy-value');
      if (occVal) {
        occVal.textContent = data.occupancy_status || 'Unknown';
        if (data.occupancy_status === 'Occupied') {
          occVal.style.color = '#16a34a';
        } else if (data.occupancy_status === 'Possibly Occupied') {
          occVal.style.color = '#d97706';
        } else {
          occVal.style.color = '#64748b';
        }
      }

      const pir1Dot = document.getElementById('pir1-dot');
      const pir1Lbl = document.getElementById('pir1-label');
      const pir2Dot = document.getElementById('pir2-dot');
      const pir2Lbl = document.getElementById('pir2-label');

      if (pir1Dot && pir1Lbl) {
        pir1Dot.className = `status-dot ${data.pir1 ? 'active' : 'inactive'}`;
        pir1Lbl.textContent = data.pir1 ? 'Motion' : 'Idle';
      }
      if (pir2Dot && pir2Lbl) {
        pir2Dot.className = `status-dot ${data.pir2 ? 'active' : 'inactive'}`;
        pir2Lbl.textContent = data.pir2 ? 'Motion' : 'Idle';
      }

      // 2. Temperature Card
      const tempVal = document.getElementById('temp-value');
      const tempBadge = document.getElementById('temp-status-badge');
      if (tempVal) {
        tempVal.textContent = data.temperature !== null ? Number(data.temperature).toFixed(1) : '--';
      }
      if (tempBadge) {
        const status = data.temp_status || 'normal';
        tempBadge.textContent = status === 'normal' ? 'Normal Range' : (status === 'critical' ? 'High Temp Warning' : 'Low Temp Warning');
        tempBadge.className = `card-status status-badge-${status}`;
      }

      // 3. Humidity Card
      const humVal = document.getElementById('humidity-value');
      const humBadge = document.getElementById('humidity-status-badge');
      if (humVal) {
        humVal.textContent = data.humidity !== null ? Number(data.humidity).toFixed(1) : '--';
      }
      if (humBadge) {
        const status = data.humidity_status || 'normal';
        humBadge.textContent = status === 'normal' ? 'Optimal Range' : 'Outside Target';
        humBadge.className = `card-status status-badge-${status}`;
      }

      // 4. Light Card
      const lightVal = document.getElementById('light-value');
      if (lightVal) {
        const lvl = data.light || 'Unknown';
        lightVal.textContent = lvl;
        if (lvl === 'Bright') lightVal.style.color = '#d97706';
        else if (lvl === 'Moderate') lightVal.style.color = '#2563eb';
        else lightVal.style.color = '#475569';
      }

      // 5. Distance Card
      const distVal = document.getElementById('distance-value');
      const distBadge = document.getElementById('distance-status-badge');
      if (distVal) {
        distVal.textContent = data.distance !== null ? Number(data.distance).toFixed(1) : '--';
      }
      if (distBadge) {
        distBadge.textContent = 'Active Detection';
        distBadge.className = 'card-status status-badge-normal';
      }

      // Live Sensor Readings Strip
      setLiveItem('live-pir1', data.pir1 ? 'Motion Detected' : 'No Motion', data.pir1 ? '#16a34a' : '#64748b');
      setLiveItem('live-pir2', data.pir2 ? 'Motion Detected' : 'No Motion', data.pir2 ? '#16a34a' : '#64748b');
      setLiveItem('live-temp', data.temperature !== null ? `${Number(data.temperature).toFixed(1)} °C` : '--');
      setLiveItem('live-humidity', data.humidity !== null ? `${Number(data.humidity).toFixed(1)} %` : '--');
      setLiveItem('live-light', data.light || '--');
      setLiveItem('live-distance', data.distance !== null ? `${Number(data.distance).toFixed(1)} cm` : '--');

      // Update classroom status overview panel
      renderClassroomStatusPanel(data);

    } catch (err) {
      console.warn('Latest readings error:', err);
    }
  }

  function setLiveItem(elementId, valueText, color) {
    const el = document.getElementById(elementId);
    if (el) {
      el.textContent = valueText;
      if (color) el.style.color = color;
      else el.style.color = '';
    }
  }

  function renderClassroomStatusPanel(data) {
    const panel = document.getElementById('classroom-status-panel');
    if (!panel) return;

    const items = [];

    // Occupancy item
    if (data.occupancy_status === 'Occupied') {
      items.push({
        type: 'status-normal',
        title: 'Occupied',
        desc: 'Recent motion activity detected inside classroom.'
      });
    } else if (data.occupancy_status === 'Possibly Occupied') {
      items.push({
        type: 'status-warning',
        title: 'Possibly Occupied',
        desc: 'Intermittent motion detected recently.'
      });
    } else {
      items.push({
        type: 'status-neutral',
        title: 'No Recent Motion',
        desc: 'No motion detected during the observation period.'
      });
    }

    // Light item
    if (data.light === 'Bright') {
      items.push({
        type: data.occupancy_status === 'No Recent Motion' ? 'status-warning' : 'status-normal',
        title: 'Light Level: Bright',
        desc: data.occupancy_status === 'No Recent Motion'
          ? 'Bright conditions detected while classroom appears inactive.'
          : 'Sufficient ambient lighting for classroom activities.'
      });
    } else if (data.light === 'Moderate') {
      items.push({
        type: 'status-normal',
        title: 'Light Level: Moderate',
        desc: 'Ambient light level is in comfortable medium range.'
      });
    } else {
      items.push({
        type: 'status-neutral',
        title: 'Light Level: Dark',
        desc: 'Ambient illumination is low or lights are off.'
      });
    }

    // Temp status item
    if (data.temp_status === 'critical') {
      items.push({
        type: 'status-critical',
        title: 'Temperature Warning',
        desc: `High temperature reading of ${data.temperature}°C.`
      });
    } else if (data.temp_status === 'warning') {
      items.push({
        type: 'status-warning',
        title: 'Temperature Warning',
        desc: `Low temperature reading of ${data.temperature}°C.`
      });
    } else {
      items.push({
        type: 'status-normal',
        title: 'Comfortable Temperature',
        desc: `${data.temperature}°C within normal classroom target.`
      });
    }

    // Humidity status item
    if (data.humidity_status === 'warning') {
      items.push({
        type: 'status-warning',
        title: 'Humidity Alert',
        desc: `${data.humidity}% is outside configured relative humidity threshold.`
      });
    }

    panel.innerHTML = items.map(it => `
      <div class="status-panel-item ${it.type}">
        <div class="status-panel-text">
          <strong>${it.title}</strong>
          <span>${it.desc}</span>
        </div>
      </div>
    `).join('');
  }

  // -------------------------------------------------------------
  // Environmental Charts (Chart.js)
  // -------------------------------------------------------------
  function initCharts() {
    const commonScales = {
      x: {
        grid: { color: 'rgba(226, 232, 240, 0.6)' },
        ticks: { color: '#64748b', maxTicksLimit: 7 }
      },
      y: {
        grid: { color: 'rgba(226, 232, 240, 0.6)' },
        ticks: { color: '#64748b' }
      }
    };

    // 1. Temperature Chart
    const ctxTemp = document.getElementById('chart-temperature');
    if (ctxTemp) {
      charts.temp = new Chart(ctxTemp, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Temperature (°C)', data: [], borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.1)', tension: 0.3, fill: true, pointRadius: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: commonScales }
      });
    }

    // 2. Humidity Chart
    const ctxHum = document.getElementById('chart-humidity');
    if (ctxHum) {
      charts.humidity = new Chart(ctxHum, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Humidity (%)', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)', tension: 0.3, fill: true, pointRadius: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: commonScales }
      });
    }

    // 3. Light Chart
    const ctxLight = document.getElementById('chart-light');
    if (ctxLight) {
      charts.light = new Chart(ctxLight, {
        type: 'bar',
        data: { labels: [], datasets: [{ label: 'Light Intensity (ADC value)', data: [], backgroundColor: 'rgba(245, 158, 11, 0.8)', borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: commonScales }
      });
    }

    // 4. Distance Chart
    const ctxDist = document.getElementById('chart-distance');
    if (ctxDist) {
      charts.distance = new Chart(ctxDist, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Distance (cm)', data: [], borderColor: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.1)', tension: 0.2, fill: true, pointRadius: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: commonScales }
      });
    }

    // 5. PIR Motion Activity Chart
    const ctxMotion = document.getElementById('chart-motion');
    if (ctxMotion) {
      charts.motion = new Chart(ctxMotion, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'PIR 1 Motion', data: [], borderColor: '#16a34a', stepped: true, pointRadius: 1, borderWidth: 2 },
            { label: 'PIR 2 Motion', data: [], borderColor: '#0284c7', stepped: true, pointRadius: 1, borderWidth: 2 }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            x: commonScales.x,
            y: {
              min: 0,
              max: 1.2,
              ticks: {
                stepSize: 1,
                callback: (val) => val === 1 ? 'Active' : (val === 0 ? 'Idle' : '')
              }
            }
          }
        }
      });
    }
  }

  function setupChartFilters() {
    const container = document.getElementById('chart-filters');
    if (!container) return;

    container.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        chartPeriod = btn.getAttribute('data-period') || '1h';
        fetchHistoryChartData(chartPeriod);
      });
    });
  }

  async function fetchHistoryChartData(period) {
    try {
      const res = await fetch(`/api/sensors/history?period=${period}&limit=300`);
      if (!res.ok) throw new Error('History chart request failed');
      const data = await res.json();
      const readings = (data.readings || []).slice().reverse(); // Chronological order

      const labels = readings.map(r => formatTime(new Date(r.timestamp)));
      const temps = readings.map(r => r.temperature);
      const hums = readings.map(r => r.humidity);
      const lights = readings.map(r => r.light_raw !== null && r.light_raw !== undefined ? r.light_raw : (r.light === 'Bright' ? 800 : (r.light === 'Moderate' ? 500 : 150)));
      const dists = readings.map(r => r.distance);
      const pir1Vals = readings.map(r => r.pir1 ? 1 : 0);
      const pir2Vals = readings.map(r => r.pir2 ? 1 : 0);

      if (charts.temp) {
        charts.temp.data.labels = labels;
        charts.temp.data.datasets[0].data = temps;
        charts.temp.update();
      }

      if (charts.humidity) {
        charts.humidity.data.labels = labels;
        charts.humidity.data.datasets[0].data = hums;
        charts.humidity.update();
      }

      if (charts.light) {
        charts.light.data.labels = labels;
        charts.light.data.datasets[0].data = lights;
        charts.light.update();
      }

      if (charts.distance) {
        charts.distance.data.labels = labels;
        charts.distance.data.datasets[0].data = dists;
        charts.distance.update();
      }

      if (charts.motion) {
        charts.motion.data.labels = labels;
        charts.motion.data.datasets[0].data = pir1Vals;
        charts.motion.data.datasets[1].data = pir2Vals;
        charts.motion.update();
      }

    } catch (err) {
      console.warn('Error loading history charts:', err);
    }
  }

  // -------------------------------------------------------------
  // Recent Activity Events Table
  // -------------------------------------------------------------
  async function fetchEvents() {
    const tbody = document.getElementById('activity-tbody');
    const emptyMsg = document.getElementById('no-events-message');
    if (!tbody) return;

    try {
      const res = await fetch('/api/events?limit=15');
      if (!res.ok) throw new Error('Failed to fetch events');
      const data = await res.json();
      const events = data.events || [];

      if (events.length === 0) {
        tbody.innerHTML = '';
        if (emptyMsg) emptyMsg.style.display = 'block';
        return;
      }

      if (emptyMsg) emptyMsg.style.display = 'none';

      tbody.innerHTML = events.map(ev => `
        <tr>
          <td>${formatDate(new Date(ev.timestamp))} ${formatTime(new Date(ev.timestamp))}</td>
          <td><strong>${escapeHtml(ev.event)}</strong></td>
          <td>${escapeHtml(ev.sensor || '--')}</td>
          <td>${escapeHtml(ev.reading || '--')}</td>
        </tr>
      `).join('');

    } catch (err) {
      console.warn('Events fetch error:', err);
    }
  }

  // -------------------------------------------------------------
  // Alerts Page
  // -------------------------------------------------------------
  function setupAlertFilters() {
    const container = document.getElementById('alert-filters');
    if (!container) return;

    container.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeAlertFilter = btn.getAttribute('data-alert-filter') || 'all';
        fetchAlerts();
      });
    });
  }

  async function fetchAlerts() {
    const listEl = document.getElementById('alerts-list');
    const emptyEl = document.getElementById('no-alerts-message');
    const navBadge = document.getElementById('alert-count-badge');
    if (!listEl) return;

    try {
      const url = activeAlertFilter === 'all'
        ? '/api/alerts?limit=50'
        : `/api/alerts?status=${activeAlertFilter}&limit=50`;

      const res = await fetch(url);
      if (!res.ok) throw new Error('Alerts fetch failed');
      const data = await res.json();
      const alerts = data.alerts || [];

      // Update badge with count of active alerts
      const activeCount = alerts.filter(a => a.status === 'active').length;
      if (navBadge) {
        if (activeCount > 0) {
          navBadge.textContent = activeCount;
          navBadge.style.display = 'inline-block';
        } else {
          navBadge.style.display = 'none';
        }
      }

      if (alerts.length === 0) {
        listEl.innerHTML = '';
        if (emptyEl) emptyEl.style.display = 'block';
        return;
      }

      if (emptyEl) emptyEl.style.display = 'none';

      listEl.innerHTML = alerts.map(alert => {
        const isResolved = alert.status === 'resolved';
        return `
          <div class="alert-card severity-${alert.severity} status-${alert.status}">
            <div class="alert-content">
              <div class="alert-title-row">
                <span class="alert-title">${escapeHtml(alert.title)}</span>
                <span class="alert-badge ${alert.severity}">${alert.severity}</span>
                ${isResolved ? '<span class="alert-badge low">RESOLVED</span>' : ''}
              </div>
              <p class="alert-desc">${escapeHtml(alert.description)}</p>
              <div class="alert-meta">
                <span><strong>Sensor:</strong> ${escapeHtml(alert.sensor || 'General')}</span>
                <span><strong>Time:</strong> ${formatDate(new Date(alert.timestamp))} ${formatTime(new Date(alert.timestamp))}</span>
                ${alert.resolved_at ? `<span><strong>Resolved:</strong> ${formatTime(new Date(alert.resolved_at))}</span>` : ''}
              </div>
            </div>
            ${!isResolved ? `
              <button class="btn btn-secondary btn-sm resolve-btn" data-id="${alert.id}">
                Resolve
              </button>
            ` : ''}
          </div>
        `;
      }).join('');

      // Attach resolve handlers
      listEl.querySelectorAll('.resolve-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-id');
          await resolveAlert(id);
        });
      });

    } catch (err) {
      console.warn('Alerts fetch error:', err);
    }
  }

  async function resolveAlert(alertId) {
    try {
      const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: 'POST' });
      if (res.ok) {
        fetchAlerts();
      }
    } catch (err) {
      console.error('Failed to resolve alert:', err);
    }
  }

  // -------------------------------------------------------------
  // Sensors Page
  // -------------------------------------------------------------
  async function fetchSensorDetails() {
    const grid = document.getElementById('sensor-details-grid');
    if (!grid) return;

    try {
      const [statusRes, latestRes] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/sensors/latest')
      ]);

      const statusData = await statusRes.json();
      const latestData = await latestRes.json();
      const sensors = statusData.sensors || {};

      const sensorItems = [
        {
          name: 'PIR Motion Sensor 1',
          type: 'Passive Infrared (HC-SR501)',
          purpose: 'Detects human infrared radiation movement in Classroom Zone A.',
          tech: 'Dual element pyroelectric sensor with Fresnel lens covering 120° angle, up to 7m range.',
          status: sensors.pir1?.connected ? 'Online' : 'Offline',
          currentVal: latestData.pir1 ? 'Motion Detected' : 'No Motion',
          lastActive: sensors.pir1?.last_active ? formatTime(new Date(sensors.pir1.last_active)) : 'None'
        },
        {
          name: 'PIR Motion Sensor 2',
          type: 'Passive Infrared (HC-SR501)',
          purpose: 'Detects human infrared radiation movement in Classroom Zone B.',
          tech: 'Secondary PIR node for cross-validation of occupancy and minimizing false negatives.',
          status: sensors.pir2?.connected ? 'Online' : 'Offline',
          currentVal: latestData.pir2 ? 'Motion Detected' : 'No Motion',
          lastActive: sensors.pir2?.last_active ? formatTime(new Date(sensors.pir2.last_active)) : 'None'
        },
        {
          name: 'Ultrasonic Distance Sensor',
          type: 'HC-SR04 Ultrasonic Transducer',
          purpose: 'Measures proximity to entryway or nearest desk obstacle in cm.',
          tech: '40 kHz sonar burst transmitter and receiver; operating range 2 cm to 400 cm with 3mm precision.',
          status: sensors.ultrasonic?.connected ? 'Online' : 'Offline',
          currentVal: latestData.distance !== null && latestData.distance !== undefined ? `${Number(latestData.distance).toFixed(1)} cm` : '--',
          lastActive: sensors.ultrasonic?.last_reading ? formatTime(new Date(sensors.ultrasonic.last_reading)) : '--'
        },
        {
          name: 'Temperature & Humidity Sensor',
          type: 'DHT22 / AM2302 Capacitive Sensor',
          purpose: 'Monitors classroom ambient thermal comfort and ventilation moisture levels.',
          tech: 'Temperature range -40°C to 80°C (±0.5°C accuracy); Humidity range 0-100% RH (±2% accuracy).',
          status: sensors.dht22?.connected ? 'Online' : 'Offline',
          currentVal: latestData.temperature !== null ? `${Number(latestData.temperature).toFixed(1)}°C | ${Number(latestData.humidity).toFixed(1)}%` : '--',
          lastActive: sensors.dht22?.last_reading ? formatTime(new Date(sensors.dht22.last_reading)) : '--'
        },
        {
          name: 'Ambient Light Sensor',
          type: 'Light Dependent Resistor (LDR) Voltage Divider',
          purpose: 'Estimates relative classroom daylight and electric lighting level.',
          tech: 'Cadmium Sulfide (CdS) photoresistor. Resistance drops with increased incident photons. Categorized into Dark/Moderate/Bright.',
          status: sensors.ldr?.connected ? 'Online' : 'Offline',
          currentVal: `${latestData.light || '--'} (ADC: ${latestData.light_raw || '--'})`,
          lastActive: sensors.ldr?.last_reading ? formatTime(new Date(sensors.ldr.last_reading)) : '--'
        },
        {
          name: 'Pi Camera Module V2',
          type: 'Sony IMX219 8-Megapixel Sensor',
          purpose: 'Motion-triggered visual snapshot capture for classroom verification.',
          tech: 'Fixed focus camera connected directly to Raspberry Pi CSI bus; captures still photos on confirmed motion.',
          status: sensors.camera?.connected ? 'Available' : 'No Images Available',
          currentVal: sensors.camera?.status || 'Standby',
          lastActive: 'Motion-triggered'
        }
      ];

      grid.innerHTML = sensorItems.map(item => `
        <div class="sensor-detail-card">
          <div>
            <div class="sensor-detail-header">
              <h4>${escapeHtml(item.name)}</h4>
              <span class="card-status ${item.status === 'Online' || item.status === 'Available' ? 'status-badge-normal' : 'status-badge-warning'}">
                ${item.status}
              </span>
            </div>
            <p class="sensor-tech-desc">${escapeHtml(item.tech)}</p>
          </div>
          <table class="sensor-meta-table">
            <tbody>
              <tr><td>Sensor Type</td><td>${escapeHtml(item.type)}</td></tr>
              <tr><td>Current Value</td><td>${escapeHtml(item.currentVal)}</td></tr>
              <tr><td>Last Active / Read</td><td>${escapeHtml(item.lastActive)}</td></tr>
            </tbody>
          </table>
        </div>
      `).join('');

    } catch (err) {
      console.warn('Sensors detail fetch error:', err);
    }
  }

  // -------------------------------------------------------------
  // Camera Monitoring Page
  // -------------------------------------------------------------
  async function fetchCameraStatus() {
    const placeholder = document.getElementById('camera-placeholder');
    const imgEl = document.getElementById('camera-image');
    const statusEl = document.getElementById('camera-status');
    const timestampEl = document.getElementById('camera-timestamp');

    try {
      const res = await fetch('/api/camera/latest');
      if (!res.ok) throw new Error('Camera endpoint error');
      const data = await res.json();

      if (statusEl) statusEl.textContent = data.camera_status || 'Unavailable';

      if (data.available && data.image_url) {
        if (imgEl) {
          imgEl.src = data.image_url;
          imgEl.style.display = 'block';
        }
        if (placeholder) placeholder.style.display = 'none';
        if (timestampEl) timestampEl.textContent = formatDate(new Date(data.timestamp)) + ' ' + formatTime(new Date(data.timestamp));
      } else {
        if (imgEl) imgEl.style.display = 'none';
        if (placeholder) placeholder.style.display = 'block';
        if (timestampEl) timestampEl.textContent = 'None captured yet';
      }
    } catch (err) {
      console.warn('Camera fetch error:', err);
      if (statusEl) statusEl.textContent = 'Offline';
    }
  }

  // -------------------------------------------------------------
  // Historical Data Page
  // -------------------------------------------------------------
  function setupHistoryControls() {
    const searchBtn = document.getElementById('history-search-btn');
    const exportBtn = document.getElementById('history-export-btn');

    if (searchBtn) {
      searchBtn.addEventListener('click', () => {
        historyPage = 1;
        loadHistoryTable();
      });
    }

    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const sensor = document.getElementById('history-sensor')?.value || '';
        const start = document.getElementById('history-start')?.value || '';
        const end = document.getElementById('history-end')?.value || '';

        const params = new URLSearchParams();
        if (sensor) params.append('sensor', sensor);
        if (start) params.append('start', new Date(start).toISOString());
        if (end) params.append('end', new Date(end).toISOString());

        window.location.href = `/api/export/csv?${params.toString()}`;
      });
    }
  }

  async function loadHistoryTable() {
    const tbody = document.getElementById('history-tbody');
    const emptyMsg = document.getElementById('no-history-message');
    const paginationEl = document.getElementById('history-pagination');
    if (!tbody) return;

    const sensor = document.getElementById('history-sensor')?.value || '';
    const startInput = document.getElementById('history-start')?.value;
    const endInput = document.getElementById('history-end')?.value;

    const params = new URLSearchParams({
      limit: historyPageSize,
      offset: (historyPage - 1) * historyPageSize
    });

    if (sensor) params.append('sensor', sensor);
    if (startInput) params.append('start', new Date(startInput).toISOString());
    if (endInput) params.append('end', new Date(endInput).toISOString());

    try {
      const res = await fetch(`/api/sensors/history?${params.toString()}`);
      if (!res.ok) throw new Error('History fetch error');
      const data = await res.json();
      const rows = data.readings || [];
      const total = data.total || 0;

      if (rows.length === 0) {
        tbody.innerHTML = '';
        if (emptyMsg) emptyMsg.style.display = 'block';
        if (paginationEl) paginationEl.innerHTML = '';
        return;
      }

      if (emptyMsg) emptyMsg.style.display = 'none';

      tbody.innerHTML = rows.map(r => `
        <tr>
          <td>${formatDate(new Date(r.timestamp))} ${formatTime(new Date(r.timestamp))}</td>
          <td>${r.temperature !== null && r.temperature !== undefined ? Number(r.temperature).toFixed(1) : '--'}</td>
          <td>${r.humidity !== null && r.humidity !== undefined ? Number(r.humidity).toFixed(1) : '--'}</td>
          <td>${r.light || '--'}</td>
          <td>${r.distance !== null && r.distance !== undefined ? Number(r.distance).toFixed(1) : '--'}</td>
          <td><span class="status-dot ${r.pir1 ? 'active' : 'inactive'}"></span> ${r.pir1 ? 'Motion' : 'Idle'}</td>
          <td><span class="status-dot ${r.pir2 ? 'active' : 'inactive'}"></span> ${r.pir2 ? 'Motion' : 'Idle'}</td>
        </tr>
      `).join('');

      renderPagination(total, historyPageSize, historyPage, paginationEl);

    } catch (err) {
      console.warn('History table load error:', err);
    }
  }

  function renderPagination(total, pageSize, currentPage, container) {
    if (!container) return;
    const totalPages = Math.ceil(total / pageSize);
    if (totalPages <= 1) {
      container.innerHTML = `<span style="font-size:0.8rem; color:#64748b;">Showing all ${total} records</span>`;
      return;
    }

    let html = `
      <button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} data-p="${currentPage - 1}">Prev</button>
      <span style="font-size:0.82rem; margin: 0 8px; color:#475569;">Page ${currentPage} of ${totalPages} (${total} total)</span>
      <button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} data-p="${currentPage + 1}">Next</button>
    `;

    container.innerHTML = html;

    container.querySelectorAll('.page-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = parseInt(btn.getAttribute('data-p'), 10);
        if (p >= 1 && p <= totalPages) {
          historyPage = p;
          loadHistoryTable();
        }
      });
    });
  }

  // -------------------------------------------------------------
  // Settings Page
  // -------------------------------------------------------------
  function setupSettingsForm() {
    const form = document.getElementById('settings-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const statusEl = document.getElementById('settings-save-status');

      const payload = {
        temp_min: parseFloat(document.getElementById('setting-temp_min')?.value) || 18,
        temp_max: parseFloat(document.getElementById('setting-temp_max')?.value) || 35,
        humidity_min: parseFloat(document.getElementById('setting-humidity_min')?.value) || 30,
        humidity_max: parseFloat(document.getElementById('setting-humidity_max')?.value) || 80,
        light_moderate_threshold: parseInt(document.getElementById('setting-light_moderate_threshold')?.value, 10) || 300,
        light_bright_threshold: parseInt(document.getElementById('setting-light_bright_threshold')?.value, 10) || 700,
        inactivity_timeout: parseInt(document.getElementById('setting-inactivity_timeout')?.value, 10) || 300,
        sensor_timeout: parseInt(document.getElementById('setting-sensor_timeout')?.value, 10) || 60,
        refresh_interval: parseInt(document.getElementById('setting-refresh_interval')?.value, 10) || 5
      };

      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          if (statusEl) {
            statusEl.textContent = 'Settings saved successfully!';
            statusEl.className = 'save-status success';
            setTimeout(() => { statusEl.textContent = ''; }, 3000);
          }
          if (payload.refresh_interval && payload.refresh_interval * 1000 !== refreshIntervalMs) {
            refreshIntervalMs = payload.refresh_interval * 1000;
            startPolling();
          }
        } else {
          throw new Error('Save settings failed');
        }
      } catch (err) {
        if (statusEl) {
          statusEl.textContent = 'Failed to save settings.';
          statusEl.className = 'save-status error';
        }
      }
    });
  }

  async function fetchSettings() {
    try {
      const res = await fetch('/api/settings');
      if (!res.ok) return;
      const data = await res.json();

      setInputValue('setting-temp_min', data.temp_min);
      setInputValue('setting-temp_max', data.temp_max);
      setInputValue('setting-humidity_min', data.humidity_min);
      setInputValue('setting-humidity_max', data.humidity_max);
      setInputValue('setting-light_moderate_threshold', data.light_moderate_threshold);
      setInputValue('setting-light_bright_threshold', data.light_bright_threshold);
      setInputValue('setting-inactivity_timeout', data.inactivity_timeout);
      setInputValue('setting-sensor_timeout', data.sensor_timeout);
      setInputValue('setting-refresh_interval', data.refresh_interval);

      if (data.refresh_interval) {
        refreshIntervalMs = data.refresh_interval * 1000;
      }
    } catch (err) {
      console.warn('Failed to load settings:', err);
    }
  }

  function setInputValue(id, val) {
    const el = document.getElementById(id);
    if (el && val !== undefined && val !== null) {
      el.value = val;
    }
  }

  // -------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------
  function formatTime(d) {
    if (isNaN(d.getTime())) return '--:--:--';
    return d.toTimeString().split(' ')[0];
  }

  function formatDate(d) {
    if (isNaN(d.getTime())) return '----/--/--';
    return d.toISOString().split('T')[0];
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

})();

