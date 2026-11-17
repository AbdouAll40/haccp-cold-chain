"use strict";

const API = "/api";
const REFRESH_MS = 5000;
// Same route as simulators/truck.py (Khenchela -> Batna)
const ROUTE = [[35.4358, 7.1433], [35.46, 6.93], [35.49, 6.65], [35.52, 6.40], [35.5559, 6.1741]];
const KIND_LABELS = { temperature: "Temperature", transit_breach: "Transit breach", sensor_silent: "Silent sensor", expiry: "Expiry" };
const COLORS = { ok: "#1d8a5e", warn: "#e0a23a", bad: "#c94141", brand: "#0f6e56", line: "#9aa5b1", off: "#9ca3af" };

const state = { source: "fridge-1", hours: 1, sources: [], charts: {}, map: null, truckMarkers: {} };

// ------------------------------------------------------------------ helpers
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtT = (v) => (v === null || v === undefined ? "–" : `${Number(v).toFixed(1)} °C`);
const limits = (lo, hi) => (lo === null || lo === undefined ? `≤ ${hi} °C` : `${lo} to ${hi} °C`);
const timeOf = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "–");

function agoText(iso) {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}

async function get(path) {
  const r = await fetch(API + path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

function statusPill(status) {
  const map = { ok: ["pill-ok", "In range"], alert: ["pill-bad", "Out of range"], offline: ["pill-off", "Offline"], unknown: ["pill-wait", "Waiting"] };
  const [cls, txt] = map[status] || map.unknown;
  return `<span class="pill ${cls}">${txt}</span>`;
}

// ------------------------------------------------------------------ KPIs and zone cards
function renderKpis(k) {
  const items = [
    ["", `${k.zones_ok}/${k.zones_total}`, "Zones in range"],
    [k.open_alerts ? (k.critical_alerts ? "bad" : "warn") : "", k.open_alerts, `Open alerts (${k.critical_alerts} critical)`],
    ["", k.trucks_on_route, "Trucks on route"],
    [k.batches_expiring_soon ? "warn" : "", k.batches_expiring_soon, "Batches expiring ≤ 3 days"],
    [k.batches_expired ? "bad" : "", k.batches_expired, "Expired batches"],
    [k.batches_breach ? "bad" : "", k.batches_breach, "Cold-chain breaches"],
  ];
  $("#kpis").innerHTML = items.map(([cls, v, l]) => `<div class="kpi ${cls}"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`).join("");
}

function renderZones(equipment, trucks) {
  const cards = equipment.map((e) => ({ code: e.code, name: e.name, sub: e.location, status: e.status, temp: e.last_temp, lo: e.min_temp, hi: e.max_temp, seen: e.last_seen }));
  for (const t of trucks) {
    cards.push({ code: t.code, name: t.name, sub: t.delivery ? `${t.delivery.code} · ${t.speed_kmh ?? 0} km/h` : "No delivery", status: t.status, temp: t.last_temp, lo: t.min_temp, hi: t.max_temp, seen: t.last_seen });
  }
  state.sources = cards;
  $("#zones").innerHTML = cards.map((c) => `
    <article class="zone ${esc(c.status)} ${c.code === state.source ? "selected" : ""}" data-code="${esc(c.code)}" tabindex="0" aria-label="${esc(c.name)}">
      <div class="top-line"><div><div class="name">${esc(c.name)}</div><div class="muted small">${esc(c.sub)}</div></div>${statusPill(c.status)}</div>
      <div class="temp">${fmtT(c.temp)}</div>
      <div class="muted small">Limits ${esc(limits(c.lo, c.hi))} · ${esc(agoText(c.seen))}</div>
    </article>`).join("");
  document.querySelectorAll(".zone").forEach((el) => {
    const pick = () => selectSource(el.dataset.code);
    el.addEventListener("click", pick);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") pick(); });
  });
  $("#source-picker").innerHTML = cards.map((c) => `<button data-code="${esc(c.code)}" class="${c.code === state.source ? "on" : ""}">${esc(c.name)}</button>`).join("");
  document.querySelectorAll("#source-picker button").forEach((b) => b.addEventListener("click", () => selectSource(b.dataset.code)));
  $("#insp-equipment").innerHTML ||= equipment.map((e) => `<option value="${esc(e.code)}">${esc(e.name)}</option>`).join("");
}

function selectSource(code) {
  state.source = code;
  document.querySelectorAll(".zone").forEach((el) => el.classList.toggle("selected", el.dataset.code === code));
  document.querySelectorAll("#source-picker button").forEach((b) => b.classList.toggle("on", b.dataset.code === code));
  refreshTempChart();
}

// ------------------------------------------------------------------ temperature chart
function makeTempChart() {
  state.charts.temp = new Chart($("#temp-chart"), {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Temperature", data: [], borderColor: COLORS.brand, backgroundColor: "rgba(15,110,86,.08)", fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 },
      { label: "Max limit", data: [], borderColor: COLORS.bad, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
      { label: "Min limit", data: [], borderColor: COLORS.bad, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
    ] },
    options: {
      animation: false, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${Number(c.parsed.y).toFixed(2)} °C` } } },
      scales: { x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } }, y: { title: { display: true, text: "°C" } } },
    },
  });
}

async function refreshTempChart() {
  const src = state.sources.find((s) => s.code === state.source);
  const pts = await get(`/readings?source=${encodeURIComponent(state.source)}&minutes=30`);
  const ch = state.charts.temp;
  ch.data.labels = pts.map((p) => timeOf(p.ts));
  ch.data.datasets[0].data = pts.map((p) => p.temperature);
  ch.data.datasets[0].label = src ? src.name : state.source;
  ch.data.datasets[1].data = src ? pts.map(() => src.hi) : [];
  ch.data.datasets[2].data = src && src.lo !== null && src.lo !== undefined ? pts.map(() => src.lo) : [];
  ch.update();
  $("#temp-legend").textContent = src ? `${src.name}: ${pts.length} readings. Dashed red lines: HACCP limits (${limits(src.lo, src.hi)}).` : "";
}

// ------------------------------------------------------------------ map
function makeMap() {
  const map = L.map("map", { scrollWheelZoom: false }).fitBounds(ROUTE, { padding: [30, 30] });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(map);
  L.polyline(ROUTE, { color: COLORS.brand, weight: 4, opacity: 0.6, dashArray: "8 6" }).addTo(map);
  L.circleMarker(ROUTE[0], { radius: 7, color: COLORS.brand, fillOpacity: 1 }).addTo(map).bindTooltip("Warehouse · Khenchela");
  L.circleMarker(ROUTE[ROUTE.length - 1], { radius: 7, color: "#185fa5", fillOpacity: 1 }).addTo(map).bindTooltip("Shop · Batna");
  state.map = map;
}

function renderTrucks(trucks) {
  for (const t of trucks) {
    if (t.lat === null || t.lon === null) continue;
    const color = t.status === "alert" ? COLORS.bad : t.status === "offline" ? COLORS.off : COLORS.ok;
    const html = `<b>${esc(t.name)}</b><br>Cargo: ${fmtT(t.last_temp)}<br>Speed: ${esc(t.speed_kmh)} km/h${t.delivery ? `<br>Delivery ${esc(t.delivery.code)}: ${esc(t.delivery.origin)} → ${esc(t.delivery.destination)}` : ""}`;
    let m = state.truckMarkers[t.code];
    if (!m) {
      m = L.circleMarker([t.lat, t.lon], { radius: 10, weight: 3, color: "#fff", fillColor: color, fillOpacity: 1 }).addTo(state.map).bindPopup(html);
      state.truckMarkers[t.code] = m;
    } else {
      m.setLatLng([t.lat, t.lon]).setStyle({ fillColor: color }).setPopupContent(html);
    }
    m.bindTooltip(`${t.name} · ${fmtT(t.last_temp)}`, { permanent: true, direction: "top", offset: [0, -10] });
  }
  const t = trucks[0];
  $("#delivery-info").textContent = t && t.delivery ? `${t.delivery.code}: ${t.delivery.origin} → ${t.delivery.destination}` : "";
}

// ------------------------------------------------------------------ statistics
function renderStats(s) {
  const rows = s.per_source.map((r) => {
    const pct = r.in_range_pct;
    const bar = pct === null ? '<span class="muted small">no data</span>'
      : `<div style="display:flex;gap:8px;align-items:center"><div class="bar"><span style="width:${pct}%"></span></div><span class="small">${pct}%</span></div>`;
    return `<tr><td>${esc(r.name)}</td><td class="small muted">${esc(limits(r.min_limit, r.max_limit))}</td>
      <td class="num">${fmtT(r.min)}</td><td class="num">${fmtT(r.avg)}</td><td class="num">${fmtT(r.max)}</td>
      <td class="num">${esc(r.readings)}</td><td>${bar}</td></tr>`;
  });
  $("#stats-table tbody").innerHTML = rows.join("") || '<tr><td colspan="7" class="empty">No data yet</td></tr>';

  const kinds = Object.keys(KIND_LABELS);
  upsertChart("alertsKind", "#alerts-kind-chart", "bar", kinds.map((k) => KIND_LABELS[k]), [{
    data: kinds.map((k) => s.alerts_by_kind_24h[k] || 0), backgroundColor: [COLORS.bad, "#d9622b", COLORS.off, COLORS.warn], borderRadius: 4 }],
    { indexAxis: "y", scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } });

  const b = s.batches_by_status;
  upsertChart("batches", "#batches-chart", "doughnut", ["OK", "Expiring soon", "Expired"], [{
    data: [b.ok, b.soon, b.expired], backgroundColor: [COLORS.ok, COLORS.warn, COLORS.bad], borderWidth: 0 }],
    { plugins: { legend: { display: true, position: "right" } }, cutout: "60%" });

  const hourLabels = s.alerts_per_hour.labels.map((iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
  upsertChart("alertsHour", "#alerts-hour-chart", "bar", hourLabels, [{
    data: s.alerts_per_hour.values, backgroundColor: COLORS.brand, borderRadius: 3 }],
    { scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } });
}

function upsertChart(key, sel, type, labels, datasets, extra) {
  const ch = state.charts[key];
  if (ch) {
    ch.data.labels = labels;
    ch.data.datasets.forEach((d, i) => { d.data = datasets[i].data; });
    ch.update();
    return;
  }
  state.charts[key] = new Chart($(sel), {
    type, data: { labels, datasets },
    options: Object.assign({ animation: false, maintainAspectRatio: false, plugins: { legend: { display: false } } }, extra),
  });
}

// ------------------------------------------------------------------ tables
function renderAlerts(alerts) {
  $("#alerts-count").textContent = alerts.length ? `${alerts.length} open` : "";
  $("#alerts-table tbody").innerHTML = alerts.map((a) => `
    <tr><td class="small">${esc(timeOf(a.created_at))}</td>
      <td><span class="pill ${a.severity === "critical" ? "pill-bad" : "pill-warn"}">${esc(KIND_LABELS[a.kind] || a.kind)}</span></td>
      <td>${esc(a.source)}</td><td class="small">${esc(a.message)}</td>
      <td><button class="small-btn ghost" data-id="${a.id}">Resolve</button></td></tr>`).join("")
    || '<tr><td colspan="5" class="empty">No open alerts: the cold chain is under control.</td></tr>';
  document.querySelectorAll("#alerts-table button[data-id]").forEach((btn) => btn.addEventListener("click", async () => {
    btn.disabled = true;
    await fetch(`${API}/alerts/${btn.dataset.id}/resolve`, { method: "POST" });
    refresh();
  }));
}

function renderBatches(batches) {
  const pill = { ok: ["pill-ok", "OK"], soon: ["pill-warn", "Expires soon"], expired: ["pill-bad", "Expired"] };
  $("#batches-table tbody").innerHTML = batches.map((b) => {
    const [cls, txt] = pill[b.status];
    const days = b.days_left < 0 ? `${-b.days_left} d ago` : b.days_left === 0 ? "today" : `in ${b.days_left} d`;
    return `<tr><td>${esc(b.lot_code)}</td><td>${esc(b.product)}</td><td class="num">${esc(b.quantity)}</td>
      <td class="small">${esc(b.location)}</td><td class="small">${esc(b.expiry_date)} <span class="muted">(${esc(days)})</span></td>
      <td><span class="pill ${cls}">${txt}</span>${b.cold_chain_breach ? ' <span class="pill pill-bad" title="Cold chain broken while stored or transported">Breach</span>' : ""}</td></tr>`;
  }).join("");
}

function renderInspections(items) {
  $("#inspections-table tbody").innerHTML = items.map((i) => `
    <tr><td>${esc(i.inspection_date)}</td><td>${esc(i.equipment)}</td><td class="num">${fmtT(i.observed_temperature)}</td>
      <td><span class="pill ${i.compliant ? "pill-ok" : "pill-bad"}">${i.compliant ? "Compliant" : "Non-compliant"}</span></td>
      <td>${esc(i.inspector)}</td><td class="small">${esc(i.notes)}</td></tr>`).join("")
    || '<tr><td colspan="6" class="empty">No inspection recorded yet.</td></tr>';
}

$("#inspection-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = Object.fromEntries(f.entries());
  body.observed_temperature = Number(body.observed_temperature);
  const r = await fetch(`${API}/inspections`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const msg = $("#insp-msg");
  if (r.ok) {
    const i = await r.json();
    msg.textContent = i.compliant ? "Recorded: compliant." : "Recorded: NON-compliant.";
    msg.style.color = i.compliant ? COLORS.ok : COLORS.bad;
    e.target.reset();
    renderInspections(await get("/inspections"));
  } else {
    msg.textContent = `Error: ${(await r.json()).detail ?? r.status}`;
    msg.style.color = COLORS.bad;
  }
});

document.querySelectorAll("#window-picker button").forEach((b) => b.addEventListener("click", () => {
  state.hours = Number(b.dataset.h);
  document.querySelectorAll("#window-picker button").forEach((x) => x.classList.toggle("on", x === b));
  refresh();
}));

// ------------------------------------------------------------------ main loop
function setConn(id, ok, label) {
  const el = $(id);
  el.className = `pill ${ok ? "pill-ok" : "pill-bad"}`;
  el.textContent = label;
}

async function refresh() {
  try {
    const [health, equipment, trucks, stats, alerts, batches] = await Promise.all([
      get("/health"), get("/equipment"), get("/trucks"), get(`/stats?hours=${state.hours}`), get("/alerts"), get("/batches"),
    ]);
    setConn("#conn-api", true, "API connected");
    setConn("#conn-mqtt", health.mqtt_connected !== false, health.mqtt_connected === false ? "MQTT down" : "MQTT connected");
    renderKpis(stats.kpis);
    renderZones(equipment, trucks);
    renderTrucks(trucks);
    renderStats(stats);
    renderAlerts(alerts);
    renderBatches(batches);
    await refreshTempChart();
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    setConn("#conn-api", false, "API unreachable");
    console.error(err);
  }
}

makeTempChart();
makeMap();
refresh();
get("/inspections").then(renderInspections).catch(() => {});
setInterval(refresh, REFRESH_MS);
