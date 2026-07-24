function localISODate(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const state = {
  period: "day",
  anchor: localISODate(),
  dashboard: null,
  phaseDashboard: null
};
const anchorInput = document.getElementById("anchor-date");
anchorInput.value = state.anchor;

const formatNumber = (value, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  return Number(value).toLocaleString("de-DE", {minimumFractionDigits: digits, maximumFractionDigits: digits});
};
const kwh = value => `${formatNumber(value, 3)} kWh`;
const pct = value => value === null || value === undefined ? "–" : `${formatNumber(value, 1)} %`;

function shiftAnchor(direction) {
  const date = new Date(state.anchor + "T12:00:00");
  if (state.period === "day") date.setDate(date.getDate() + direction);
  if (state.period === "week") date.setDate(date.getDate() + 7 * direction);
  if (state.period === "year") date.setFullYear(date.getFullYear() + direction);
  state.anchor = localISODate(date);
  anchorInput.value = state.anchor;
  loadDashboard();
}

document.querySelectorAll("[data-period]").forEach(button => {
  button.addEventListener("click", () => {
    state.period = button.dataset.period;
    document.querySelectorAll("[data-period]").forEach(item => item.classList.toggle("active", item === button));
    loadDashboard();
  });
});
anchorInput.addEventListener("change", () => { state.anchor = anchorInput.value; loadDashboard(); });
document.getElementById("previous-period").addEventListener("click", () => shiftAnchor(-1));
document.getElementById("next-period").addEventListener("click", () => shiftAnchor(1));
document.getElementById("today-period").addEventListener("click", () => {
  state.anchor = localISODate();
  anchorInput.value = state.anchor;
  loadDashboard();
});

async function loadDashboard() {
  const response = await fetch(`/api/dashboard?period=${state.period}&anchor=${state.anchor}`);
  state.dashboard = await response.json();
  document.getElementById("period-title").textContent = state.dashboard.title;
  const k = state.dashboard.kpi;
  document.getElementById("kpi-solar").textContent = kwh(k.solar_kwh);
  document.getElementById("kpi-house").textContent = kwh(k.house_kwh);
  document.getElementById("kpi-import").textContent = kwh(k.grid_import_kwh);
  document.getElementById("kpi-export").textContent = kwh(k.feed_in_kwh);
  document.getElementById("kpi-self-pct").textContent = pct(k.self_consumption_pct);
  document.getElementById("kpi-autarky").textContent = pct(k.autarky_pct);
  document.getElementById("kpi-one-pv").textContent = kwh(k.solakon_pv_kwh);
  document.getElementById("kpi-one-ac").textContent = kwh(k.solakon_ac_kwh);
  document.getElementById("kpi-shelly-ac").textContent = kwh(k.shelly_ac_kwh);
  document.getElementById("kpi-battery-charge").textContent = kwh(k.battery_charge_kwh);
  document.getElementById("kpi-battery-discharge").textContent = kwh(k.battery_discharge_kwh);
  document.getElementById("kpi-battery-soc").textContent = k.battery_soc_avg === null
    ? "–"
    : `${formatNumber(k.battery_soc_avg, 1)} / ${formatNumber(k.battery_soc_min, 1)} / ${formatNumber(k.battery_soc_max, 1)} %`;
  document.getElementById("kpi-difference").textContent = k.difference_avg_w === null
    ? "–"
    : `${formatNumber(k.difference_avg_w, 1)} W · ${formatNumber(k.difference_avg_pct, 1)} %`;
  document.getElementById("period-source").textContent = k.solar_source || "Keine Quelle";
  document.getElementById("kpi-grid-source").textContent = k.grid_source || "–";
  drawChart();
  await loadPhaseDashboard();
}

function setText(id, value, digits = 0) {
  document.getElementById(id).textContent = formatNumber(value, digits);
}

async function loadLive() {
  try {
    const response = await fetch("/api/live");
    const data = await response.json();
    const latest = data.latest;
    setText("live-solar", latest?.solar_power_w);
    setText("live-house", latest?.house_power_w);
    setText("live-import", latest?.grid_import_w);
    setText("live-export", latest?.feed_in_w);
    setText("live-one-pv", latest?.solakon_pv_power_w);
    setText("live-one-ac", latest?.solakon_ac_power_w);
    setText("live-one-soc", latest?.solakon_battery_soc_pct, 1);
    setText("live-one-battery", latest?.solakon_battery_power_w);
    setText("live-one-load", latest?.solakon_load_power_w);
    setText("live-one-temp", latest?.solakon_temperature_c, 1);
    document.getElementById("live-shelly-ac").textContent = `${formatNumber(latest?.shelly_solar_power_w)} W`;
    document.getElementById("live-solakon-ac-compare").textContent = `${formatNumber(latest?.solakon_ac_power_w)} W`;
    document.getElementById("live-difference").textContent = latest?.solar_difference_w === null || latest?.solar_difference_w === undefined
      ? "–"
      : `${formatNumber(latest.solar_difference_w, 1)} W · ${formatNumber(latest.solar_difference_pct, 1)} %`;
    document.getElementById("live-source").textContent = latest?.solar_source || "–";
    renderGridMeter(
      data.grid_meter,
      data.active_sources,
      latest
    );

    const batteryPower = latest?.solakon_battery_power_w;
    document.getElementById("battery-direction").textContent = batteryPower === null || batteryPower === undefined
      ? "–"
      : batteryPower > 5 ? "Laden" : batteryPower < -5 ? "Entladen" : "Ruhe";

    const oneStatus = document.getElementById("solakon-live-status");
    const oneConnected = Boolean(latest?.solakon_ok);
    oneStatus.className = `mini-pill ${oneConnected ? "on" : "off"}`;
    oneStatus.textContent = oneConnected ? (latest.solakon_status || "verbunden") : "nicht verbunden";
    const info = [latest?.solakon_model, latest?.solakon_serial].filter(Boolean).join(" · ");
    document.getElementById("solakon-device-info").textContent = info || "Noch keine Modbus-Messung vorhanden.";

    const meta = document.getElementById("live-meta");
    if (latest) {
      const message = latest.error_text ? ` · Warnung: ${latest.error_text}` : "";
      meta.textContent = `Letzte Messung ${new Date(latest.ts_epoch * 1000).toLocaleString("de-DE")} · vor ${latest.age_seconds} s${message}`;
    } else {
      meta.textContent = "Noch keine Messung vorhanden.";
    }
    const header = document.getElementById("header-status");
    header.className = "status-pill " + (data.collector.running ? "running" : "stopped");
    header.innerHTML = `<span></span>${data.collector.running ? "Erfassung aktiv" : "Erfassung gestoppt"}`;
    await loadPhaseLive();
  } catch (error) {
    document.getElementById("live-meta").textContent = "Livewerte konnten nicht geladen werden.";
  }
}

function renderGridMeter(gridMeter, activeSources, latest) {
  const importPower = gridMeter?.import_power_w ?? latest?.grid_import_w;
  const exportPower = gridMeter?.export_power_w ?? latest?.feed_in_w;
  setText("grid-meter-import", importPower);
  setText("grid-meter-export", exportPower);
  document.getElementById("grid-meter-import-total").textContent =
    gridMeter?.import_total_kwh === null || gridMeter?.import_total_kwh === undefined
      ? "–"
      : formatNumber(gridMeter.import_total_kwh, 3);
  document.getElementById("grid-meter-export-total").textContent =
    gridMeter?.export_total_kwh === null || gridMeter?.export_total_kwh === undefined
      ? "–"
      : formatNumber(gridMeter.export_total_kwh, 3);

  const status = document.getElementById("grid-meter-status");
  const statusValue = gridMeter?.status || "nicht verfügbar";
  status.className = `mini-pill ${statusValue === "online" ? "on" : "off"}`;
  status.textContent = statusValue;

  const details = [
    gridMeter?.name,
    gridMeter?.adapter,
    gridMeter?.source_id
  ].filter(Boolean).join(" · ");
  const warning = gridMeter?.error ? ` · ${gridMeter.error}` : "";
  document.getElementById("grid-meter-device-info").textContent =
    details ? `${details}${warning}` : "Noch keine offizielle Zählermessung vorhanden.";

  document.getElementById("grid-meter-source").textContent =
    activeSources?.grid_power_label || activeSources?.grid_power || "keine Quelle";
  document.getElementById("grid-meter-quality").textContent =
    gridMeter?.quality || "nicht verfügbar";
  document.getElementById("grid-meter-update").textContent =
    gridMeter?.last_update
      ? new Date(gridMeter.last_update).toLocaleString("de-DE")
      : "nicht verfügbar";
  document.getElementById("grid-meter-age").textContent =
    gridMeter?.age_seconds === null || gridMeter?.age_seconds === undefined
      ? "nicht verfügbar"
      : `vor ${gridMeter.age_seconds} s`;
}

async function loadPhaseLive() {
  const response = await fetch("/api/phases/live?source=house_meter");
  if (!response.ok) throw new Error("Phasen-Livewerte konnten nicht geladen werden.");
  const payload = await response.json();
  const latest = payload.latest;
  const status = document.getElementById("phase-live-status");

  if (!latest) {
    status.className = "mini-pill off";
    status.textContent = "nicht verfügbar";
    document.getElementById("phase-device-info").textContent = "Noch keine Phasenmessung vorhanden.";
    renderPhaseLive(null);
    return;
  }

  const isOnline = latest.device_status === "online";
  status.className = `mini-pill ${isOnline ? "on" : "off"}`;
  status.textContent = latest.device_status || "unbekannt";
  const details = [latest.source_id, latest.ts_local].filter(Boolean).join(" · ");
  document.getElementById("phase-device-info").textContent = details || "Phasenmessung vorhanden.";
  renderPhaseLive(latest);
}

function renderPhaseLive(latest) {
  ["l1", "l2", "l3"].forEach(phase => {
    const values = latest?.phases?.[phase];
    setText(`phase-${phase}-power`, values?.power_w);
    document.getElementById(`phase-${phase}-voltage`).textContent = values?.voltage_v === null || values?.voltage_v === undefined
      ? "–"
      : `${formatNumber(values.voltage_v, 1)} V`;
    document.getElementById(`phase-${phase}-current`).textContent = values?.current_a === null || values?.current_a === undefined
      ? "–"
      : `${formatNumber(values.current_a, 2)} A`;
    document.getElementById(`phase-${phase}-pf`).textContent = formatNumber(values?.power_factor, 3);
    document.getElementById(`phase-${phase}-share`).textContent = pct(latest?.analysis?.share_pct?.[phase]);
    const quality = document.getElementById(`phase-${phase}-quality`);
    quality.textContent = values?.quality || "–";
    quality.className = `phase-quality ${values?.quality || "unknown"}`;
  });

  document.getElementById("phase-role").textContent = latest?.measurement_role || "–";
  document.getElementById("phase-sum").textContent = latest?.analysis?.sum_w === null || latest?.analysis?.sum_w === undefined
    ? "–"
    : `${formatNumber(latest.analysis.sum_w, 1)} W`;
  document.getElementById("phase-spread").textContent = latest?.analysis?.spread_w === null || latest?.analysis?.spread_w === undefined
    ? "–"
    : `${formatNumber(latest.analysis.spread_w, 1)} W`;

  const delta = latest?.analysis?.total_delta_w;
  const deltaPct = latest?.analysis?.total_delta_pct;
  const consistent = latest?.analysis?.total_consistent;
  document.getElementById("phase-delta").textContent = delta === null || delta === undefined
    ? "nicht vergleichbar"
    : `${formatNumber(delta, 1)} W · ${formatNumber(deltaPct, 1)} % · ${consistent ? "plausibel" : "auffällig"}`;
}

async function loadPhaseDashboard() {
  try {
    const response = await fetch(`/api/phases/dashboard?period=${state.period}&anchor=${state.anchor}&source=house_meter`);
    if (!response.ok) throw new Error("Phasenverlauf konnte nicht geladen werden.");
    state.phaseDashboard = await response.json();
    const summary = state.phaseDashboard.summary;
    document.getElementById("phase-period-summary").textContent = summary.sample_count
      ? `${summary.sample_count} Messungen · ${summary.suspect_sample_count} auffällig · maximale Spreizung ${formatNumber(summary.max_spread_w, 1)} W`
      : "Noch keine Phasendaten.";
    drawPhaseChart();
  } catch (error) {
    state.phaseDashboard = null;
    document.getElementById("phase-period-summary").textContent = "Phasenverlauf konnte nicht geladen werden.";
    drawPhaseChart();
  }
}

function drawPhaseChart() {
  const canvas = document.getElementById("phase-power-chart");
  const empty = document.getElementById("phase-chart-empty");
  const data = state.phaseDashboard;
  if (!canvas || !empty) return;

  const values = data
    ? [
        ...data.series.l1_power_w,
        ...data.series.l2_power_w,
        ...data.series.l3_power_w
      ].filter(value => value !== null && value !== undefined && Number.isFinite(Number(value)))
    : [];
  empty.style.display = values.length ? "none" : "grid";

  const dpr = window.devicePixelRatio || 1;
  const cssWidth = canvas.parentElement.clientWidth;
  const cssHeight = 280;
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  canvas.style.width = cssWidth + "px";
  canvas.style.height = cssHeight + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  if (!data || !values.length) return;

  const margin = {left: 58, right: 18, top: 18, bottom: 44};
  const width = cssWidth - margin.left - margin.right;
  const height = cssHeight - margin.top - margin.bottom;
  const maxAbs = niceMax(Math.max(...values.map(value => Math.abs(Number(value))), 1));
  const styles = getComputedStyle(document.documentElement);
  const series = [
    {values: data.series.l1_power_w, color: styles.getPropertyValue("--green").trim()},
    {values: data.series.l2_power_w, color: styles.getPropertyValue("--blue").trim()},
    {values: data.series.l3_power_w, color: styles.getPropertyValue("--yellow").trim()}
  ];

  ctx.font = "11px system-ui";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const value = maxAbs - (maxAbs * 2 * i / 4);
    const y = margin.top + height * i / 4;
    ctx.strokeStyle = value === 0 ? "#9aaba4" : "#dce5e1";
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(cssWidth - margin.right, y);
    ctx.stroke();
    ctx.fillStyle = "#65736d";
    ctx.textAlign = "right";
    ctx.fillText(formatNumber(value, 0), margin.left - 8, y + 4);
  }

  const xFor = index => margin.left + (data.labels.length <= 1 ? width / 2 : width * index / (data.labels.length - 1));
  const yFor = value => margin.top + (maxAbs - value) / (maxAbs * 2) * height;

  series.forEach(item => {
    ctx.strokeStyle = item.color;
    ctx.fillStyle = item.color;
    ctx.lineWidth = 2.2;
    let drawing = false;
    ctx.beginPath();
    item.values.forEach((rawValue, index) => {
      if (rawValue === null || rawValue === undefined) {
        drawing = false;
        return;
      }
      const x = xFor(index);
      const y = yFor(Number(rawValue));
      if (!drawing) {
        ctx.moveTo(x, y);
        drawing = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    item.values.forEach((rawValue, index) => {
      if (rawValue === null || rawValue === undefined) return;
      ctx.beginPath();
      ctx.arc(xFor(index), yFor(Number(rawValue)), 2.5, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  const showEvery = data.labels.length > 16 ? 3 : 1;
  data.labels.forEach((label, index) => {
    if (index % showEvery !== 0) return;
    ctx.fillStyle = "#65736d";
    ctx.textAlign = "center";
    ctx.fillText(label, xFor(index), cssHeight - 18);
  });

  ctx.save();
  ctx.translate(15, margin.top + height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillStyle = "#65736d";
  ctx.fillText("W", 0, 0);
  ctx.restore();
}

function drawChart() {
  const canvas = document.getElementById("energy-chart");
  const empty = document.getElementById("chart-empty");
  const data = state.dashboard;
  if (!data) return;
  const all = [
    ...data.series.solar_kwh,
    ...data.series.house_kwh,
    ...data.series.grid_import_kwh,
    ...data.series.feed_in_kwh
  ];
  const maxValue = Math.max(...all, 0);
  empty.style.display = maxValue <= 0 ? "grid" : "none";

  const dpr = window.devicePixelRatio || 1;
  const cssWidth = canvas.parentElement.clientWidth;
  const cssHeight = 340;
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  canvas.style.width = cssWidth + "px";
  canvas.style.height = cssHeight + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const margin = {left: 55, right: 18, top: 15, bottom: 48};
  const width = cssWidth - margin.left - margin.right;
  const height = cssHeight - margin.top - margin.bottom;
  const yMax = niceMax(maxValue);
  const styles = getComputedStyle(document.documentElement);
  const colors = [
    styles.getPropertyValue("--green").trim(),
    styles.getPropertyValue("--yellow").trim(),
    styles.getPropertyValue("--blue").trim(),
    styles.getPropertyValue("--lime").trim()
  ];
  const series = [
    data.series.solar_kwh,
    data.series.house_kwh,
    data.series.grid_import_kwh,
    data.series.feed_in_kwh
  ];

  ctx.font = "11px system-ui";
  ctx.strokeStyle = "#dce5e1";
  ctx.fillStyle = "#65736d";
  ctx.lineWidth = 1;

  for (let i = 0; i <= 5; i++) {
    const y = margin.top + height - (height * i / 5);
    ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(cssWidth - margin.right, y); ctx.stroke();
    const value = yMax * i / 5;
    ctx.textAlign = "right";
    ctx.fillText(formatNumber(value, yMax < 1 ? 2 : 1), margin.left - 8, y + 4);
  }

  const groupWidth = width / data.labels.length;
  const barArea = Math.min(groupWidth * .75, 42);
  const barWidth = Math.max(1.5, barArea / series.length - 1);

  data.labels.forEach((label, index) => {
    const xCenter = margin.left + groupWidth * index + groupWidth / 2;
    series.forEach((values, sIndex) => {
      const value = values[index] || 0;
      const barHeight = yMax ? value / yMax * height : 0;
      const x = xCenter - barArea / 2 + sIndex * (barWidth + 1);
      const y = margin.top + height - barHeight;
      ctx.fillStyle = colors[sIndex];
      roundedRect(ctx, x, y, barWidth, barHeight, Math.min(3, barWidth / 2));
      ctx.fill();
    });
    const showEvery = data.labels.length > 16 ? 3 : 1;
    if (index % showEvery === 0) {
      ctx.fillStyle = "#65736d";
      ctx.textAlign = "center";
      ctx.fillText(label, xCenter, cssHeight - 20);
    }
  });

  ctx.save();
  ctx.translate(14, margin.top + height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillStyle = "#65736d";
  ctx.fillText("kWh", 0, 0);
  ctx.restore();
}

function niceMax(value) {
  if (value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / Math.pow(10, exponent);
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return niceFraction * Math.pow(10, exponent);
}

function roundedRect(ctx, x, y, width, height, radius) {
  if (height <= 0 || width <= 0) { ctx.beginPath(); return; }
  radius = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

window.addEventListener("resize", () => {
  if (state.dashboard) drawChart();
  if (state.phaseDashboard) drawPhaseChart();
});
loadDashboard();
loadLive();
setInterval(loadLive, 5000);
setInterval(loadDashboard, 60000);
