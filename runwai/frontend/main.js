/**
 * RunwAI — CYYZ (Toronto Pearson) inspired 2D airport simulation
 * Parallel runway finals only (no crossing landing tracks), sectors, weather discs,
 * trajectory alerts, crash explosions.
 */

import { scenarios, getScenario } from "./mockScenarios.js";
import {
  RULES,
  GEO_ANCHOR,
  haversine_nm,
  xyToLatLon,
  nmPerPixel,
  stormZonePixelsToGeo,
  weatherEnvelopeFromPhenomenon,
  projectLatLon,
  minimumSeparationViolated,
  predictTrajectorySamples,
  projectedStormIntrusion,
  findPredictedSeparationConflict,
  segmentIntersection,
  wakeViolationEvidence,
  severityFromConfidence,
  trimHistory,
} from "./aviationRules.js";

// ─── CANVAS & CONFIG ────────────────────────────────────────────────────────

const canvas = document.getElementById("airportCanvas");
const ctx = canvas.getContext("2d");
const container = document.getElementById("mapContainer");

const CONFIG = {
  AIRPORT_WIDTH: 4000,
  AIRPORT_HEIGHT: 2400,
  /** Single mesoscale cell ≈ this fraction of total map area (πr²) */
  STORM_AREA_FRACTION: 0.3,
  MIN_ZOOM: 0.14,
  MAX_ZOOM: 2.0,
  ZOOM_STEP: 0.1,
  SPAWN_INTERVAL: 5500,
  UPDATE_INTERVAL: 50,
  MAX_AIRCRAFT: 5,
  PROJECT_PATH_LEN: 480,
  /** Loss of separation on map (pixels) — also checked via NM */
  CRASH_DIST: 22,
  CRASH_NM: 0.04,
};

// ─── CYYZ-STYLE LAYOUT (stylized 2D map — parallel complex, no crossing finals) ─
// Real Pearson uses parallel 05/23, 06L/R — we route ALL traffic on parallels only.
// Short 15/33 segment shown north for familiarity; no arrivals use it (avoids crossing finals).

const RUNWAYS = [
  { id: "05/23", x: 920, y: 700, length: 2300, width: 56, angle: 0, active: true },
  { id: "06L/24R", x: 920, y: 1020, length: 2300, width: 58, angle: 0, active: true },
  { id: "06R/24L", x: 920, y: 1340, length: 2260, width: 56, angle: 0, active: true },
  { id: "15/33", x: 1880, y: 140, length: 480, width: 44, angle: Math.PI / 2, active: false },
];

/** Five airspace sectors — holds for reroute when runway busy */
const SECTORS = [
  {
    id: "A12",
    label: "A12 North",
    color: "rgba(61, 213, 255, 0.11)",
    border: "rgba(61, 213, 255, 0.32)",
    poly: [
      [80, 40],
      [3920, 40],
      [3920, 420],
      [80, 420],
    ],
    hold: { x: 2000, y: 230 },
  },
  {
    id: "C03",
    label: "C03 West",
    color: "rgba(248, 113, 113, 0.07)",
    border: "rgba(248, 113, 113, 0.28)",
    poly: [
      [80, 420],
      [780, 420],
      [780, 1780],
      [80, 1780],
    ],
    hold: { x: 430, y: 1100 },
  },
  {
    id: "E05",
    label: "E05 Core",
    color: "rgba(74, 222, 128, 0.07)",
    border: "rgba(74, 222, 128, 0.28)",
    poly: [
      [780, 420],
      [3400, 420],
      [3400, 1780],
      [780, 1780],
    ],
    hold: { x: 2090, y: 1100 },
  },
  {
    id: "B07",
    label: "B07 East",
    color: "rgba(167, 139, 250, 0.1)",
    border: "rgba(167, 139, 250, 0.32)",
    poly: [
      [3400, 420],
      [3920, 420],
      [3920, 1780],
      [3400, 1780],
    ],
    hold: { x: 3660, y: 1100 },
  },
  {
    id: "D14",
    label: "D14 South",
    color: "rgba(251, 191, 36, 0.08)",
    border: "rgba(251, 191, 36, 0.3)",
    poly: [
      [80, 1780],
      [3920, 1780],
      [3920, 2140],
      [80, 2140],
    ],
    hold: { x: 2000, y: 1960 },
  },
];

const HOLD_SECTOR_IDS = ["A12", "C03", "E05", "B07", "D14"];

const TAXIWAYS = [
  { points: [[760, 700], [760, 1020], [760, 1340]], width: 28 },
  { points: [[760, 1020], [920, 1020]], width: 28 },
  { points: [[760, 860], [920, 860], [920, 700]], width: 22 },
  { points: [[760, 1180], [920, 1180], [920, 1340]], width: 22 },
  { points: [[1300, 700], [1300, 1340]], width: 22 },
  { points: [[1900, 700], [1900, 1340]], width: 22 },
  { points: [[2500, 700], [2500, 1340]], width: 22 },
  { points: [[1880, 140], [1880, 420]], width: 20 },
  { points: [[400, 1100], [780, 1100]], width: 22 },
  { points: [[3400, 1100], [3780, 1100]], width: 22 },
];

// ─── STATE ────────────────────────────────────────────────────────────────────

let zoom = 0.24;
let panX = 0;
let panY = 0;
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let time = 0;

let aircraft = [];
let violations = [];
let trajectoryAlerts = [];
let explosions = [];
let weather = {
  wind_dir_deg: 270,
  wind_speed_kts: 14,
  wind_gust_kts: 18,
  wind_severity: "moderate",
  visibility_sm: 10,
  ceiling_ft: 4500,
  storm: true,
  /** Canvas storm disc — { cx, cy, r, type, label } */
  zone: null,
  /** Geo + training — { center_lat, center_lon, radius_nm, phenomenon_type, label } */
  storm_geo: null,
  /** Alias for JSON export (model training) */
  storm_sectors: [],
};
let currentMode = "live";
let spawnIntervalId = null;
/** Preserved scenario JSON violations when not in live mode */
let scenarioStaticViolations = [];

/** runway id -> release frame (simple busy gate) */
const runwayBusyUntil = Object.create(null);

const ui = {
  aircraftCount: document.getElementById("aircraftCount"),
  violationCount: document.getElementById("violationCount"),
  windValue: document.getElementById("windValue"),
  zoomLevel: document.getElementById("zoomLevel"),
  alertsList: document.getElementById("alertsList"),
  aiContent: document.getElementById("aiContent"),
  flightsList: document.getElementById("flightsList"),
  headerStatus: document.getElementById("headerStatus"),
  stormBanner: document.getElementById("stormBanner"),
  stormBannerText: document.getElementById("stormBannerText"),
  alertsPanel: document.getElementById("alertsPanel"),
};

// ─── GEOMETRY / STATE SYNC ───────────────────────────────────────────────────

function findSectorHold(sectorId) {
  const s = SECTORS.find((x) => x.id === sectorId);
  return s ? { ...s.hold } : { x: 2000, y: 230 };
}

function alternateSectorId(currentId) {
  const pool = HOLD_SECTOR_IDS.filter((id) => id !== currentId);
  return pool[Math.floor(Math.random() * pool.length)] ?? "A12";
}

function syncAircraftGeo(ac) {
  const ll = xyToLatLon(ac.x, ac.y);
  ac.lat = ll.lat;
  ac.lon = ll.lon;
  ac.heading_deg = ((((ac.heading * 180) / Math.PI) % 360) + 360) % 360;
}

/** Phase-based altitude & VS — consistent with approach / departure profiles */
function updateAltitudeAndVs(ac) {
  const rwy = getRunwayById(ac.runway);
  const thr = rwy ? runwayThreshold(rwy) : { x: ac.x, y: ac.y };
  const distPx = Math.hypot(thr.x - ac.x, thr.y - ac.y);

  if (ac.phase === "DEPART") {
    ac.vertical_speed_fpm = ac.altitude_ft < 2800 ? 2000 + Math.random() * 200 : 0;
    ac.altitude_ft = Math.min(
      9500,
      ac.altitude_ft + ac.vertical_speed_fpm * (CONFIG.UPDATE_INTERVAL / 60000),
    );
  } else if (ac.phase === "ARRIVE" || ac.phase === "VECTOR") {
    const targetAlt = Math.max(600, Math.min(4200, 750 + distPx * 1.05));
    ac.vertical_speed_fpm = Math.min(
      0,
      Math.max(-1600, (targetAlt - ac.altitude_ft) * 1.8 - distPx * 0.35),
    );
    ac.altitude_ft += ac.vertical_speed_fpm * (CONFIG.UPDATE_INTERVAL / 60000);
    ac.altitude_ft = Math.max(400, ac.altitude_ft);
  } else if (ac.phase === "HOLD") {
    ac.vertical_speed_fpm = 0;
  } else {
    ac.vertical_speed_fpm = 0;
  }

  const nmPerTick = ac.speed * nmPerPixel();
  if (nmPerTick < 1e-8) {
    ac.velocity_kts = 0;
  } else {
    ac.velocity_kts = Math.min(
      450,
      Math.max(40, nmPerTick * (1000 / CONFIG.UPDATE_INTERVAL) * 3600),
    );
  }
}

function appendTrackSample(ac) {
  const now = Date.now();
  if (!ac.trackHistory) ac.trackHistory = [];
  ac.trackHistory.push({
    t: now,
    lat: ac.lat,
    lon: ac.lon,
    alt_ft: Math.round(ac.altitude_ft),
    velocity_kts: Math.round(ac.velocity_kts),
    heading_deg: Math.round(ac.heading_deg * 10) / 10,
  });
  trimHistory(ac.trackHistory, RULES.HISTORY_MAX_MS, now);
}

function getSimulationExport() {
  return {
    exported_at_ms: Date.now(),
    geo_anchor: GEO_ANCHOR,
    weather: {
      wind_dir_deg: weather.wind_dir_deg,
      wind_speed_kts: weather.wind_speed_kts,
      wind_gust_kts: weather.wind_gust_kts,
      wind_severity: weather.wind_severity,
      visibility_sm: weather.visibility_sm,
      ceiling_ft: weather.ceiling_ft,
      storm_sectors: weather.storm_sectors,
      phenomenon: weather.zone?.type,
    },
    aircraft: aircraft.map((ac) => ({
      id: ac.id,
      callsign: ac.id,
      aircraft_code: ac.type,
      weight_class: ac.weight,
      runway: ac.runway,
      phase: ac.phase,
      lat: ac.lat,
      lon: ac.lon,
      altitude_ft: Math.round(ac.altitude_ft),
      velocity_kts: Math.round(ac.velocity_kts),
      heading_deg: Math.round(ac.heading_deg * 100) / 100,
      vertical_speed_fpm: Math.round(ac.vertical_speed_fpm || 0),
      sector_id: ac.sector,
      track_history: ac.trackHistory || [],
    })),
    alerts: violations,
  };
}

function rerouteForStorm(acId, etaSec) {
  const ac = aircraft.find((a) => a.id === acId);
  const alt = alternateSectorId(ac?.sector || "E05");
  return `Vector ${acId} onto sector ${alt} holding pattern; forecast entry into mesoscale cell in ~${etaSec}s — maintain ≥${RULES.MIN_HORIZONTAL_SEP_NM} NM from hazard. Visibility ${weather.visibility_sm} SM / ceiling ${weather.ceiling_ft} ft.`;
}

function rerouteForSeparation(ids, evidence, crossedTracks) {
  const [a, b] = ids;
  const cross = crossedTracks ? " Crossing projected tracks." : "";
  return `Minimum separation (${RULES.MIN_HORIZONTAL_SEP_NM} NM horizontal AND ${RULES.MIN_VERTICAL_SEP_FT} ft vertical): resolve via heading offset or altitude crossing.${cross} Vector ${b} to restore spacing vs ${a}.`;
}

function rerouteForWake(leader, follower, ev) {
  return `Wake turbulence: increase trail to ≥6 NM or assign ${follower} +1000 ft above ${leader} wake path. Trail ${ev.trail_nm.toFixed(2)} NM, alt below leader ${ev.alt_below_ft.toFixed(0)} ft.`;
}

/** ~30% of map area; random phenomenon; METAR-like envelope + storm_sectors for training JSON */
function rollRandomStorm() {
  const W = CONFIG.AIRPORT_WIDTH;
  const H = CONFIG.AIRPORT_HEIGHT;
  const mapArea = W * H;
  const r = Math.sqrt((CONFIG.STORM_AREA_FRACTION * mapArea) / Math.PI);
  const lakeTop = H - 240;
  const margin = Math.min(r + 50, W * 0.15);
  const cx = margin + Math.random() * (W - 2 * margin);
  const cy = margin + Math.random() * (lakeTop - 2 * margin);
  const types = [
    { type: "heavy_rain", label: "Heavy rain" },
    { type: "snow_storm", label: "Heavy snow" },
    { type: "thunderstorm", label: "Thunderstorm" },
    { type: "fog", label: "Dense fog" },
  ];
  const pick = types[Math.floor(Math.random() * types.length)];
  const zone = { cx, cy, r, type: pick.type, label: pick.label };
  const env = weatherEnvelopeFromPhenomenon(pick.type);
  const storm_geo = stormZonePixelsToGeo(zone);
  weather.wind_severity = env.wind_severity;
  weather.wind_gust_kts = env.wind_gust_kts;
  weather.visibility_sm = Math.round(env.visibility_sm * 100) / 100;
  weather.ceiling_ft = env.ceiling_ft;
  weather.wind_speed_kts = Math.min(
    45,
    8 + (env.wind_severity === "severe" ? 18 : env.wind_severity === "moderate" ? 10 : 4),
  );
  weather.wind_dir_deg = (260 + Math.floor(Math.random() * 40)) % 360;
  weather.storm_geo = storm_geo;
  weather.storm_sectors = [storm_geo];
  return zone;
}

function getRunwayById(id) {
  return RUNWAYS.find((r) => r.id === id && r.active);
}

function runwayThreshold(rwy) {
  const x = rwy.x + rwy.length * 0.88;
  const y = rwy.y;
  return { x, y };
}

function pointInPolygon(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0],
      yi = poly[i][1];
    const xj = poly[j][0],
      yj = poly[j][1];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function sectorAtPoint(x, y) {
  for (const s of SECTORS) {
    if (pointInPolygon(x, y, s.poly)) return s.id;
  }
  return "—";
}

// ─── CANVAS SETUP ───────────────────────────────────────────────────────────

function resizeCanvas() {
  canvas.width = CONFIG.AIRPORT_WIDTH;
  canvas.height = CONFIG.AIRPORT_HEIGHT;
  centerView();
}

function centerView() {
  const rect = container.getBoundingClientRect();
  panX = (rect.width - CONFIG.AIRPORT_WIDTH * zoom) / 2;
  panY = (rect.height - CONFIG.AIRPORT_HEIGHT * zoom) / 2;
  updateCanvasTransform();
}

function clampPan() {
  const rect = container.getBoundingClientRect();
  const scaledW = CONFIG.AIRPORT_WIDTH * zoom;
  const scaledH = CONFIG.AIRPORT_HEIGHT * zoom;
  if (scaledW <= rect.width) panX = (rect.width - scaledW) / 2;
  else {
    const minX = rect.width - scaledW - 50;
    const maxX = 50;
    panX = Math.max(minX, Math.min(maxX, panX));
  }
  if (scaledH <= rect.height) panY = (rect.height - scaledH) / 2;
  else {
    const minY = rect.height - scaledH - 50;
    const maxY = 50;
    panY = Math.max(minY, Math.min(maxY, panY));
  }
}

function updateCanvasTransform() {
  clampPan();
  canvas.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
  ui.zoomLevel.textContent = `${Math.round(zoom * 100)}%`;
}

// ─── MAP: LAKE ONTARIO + TERMINALS + GROUND ───────────────────────────────────

function drawLakeOntario() {
  const g = ctx.createLinearGradient(0, CONFIG.AIRPORT_HEIGHT - 300, 0, CONFIG.AIRPORT_HEIGHT);
  g.addColorStop(0, "rgba(30, 55, 95, 0.35)");
  g.addColorStop(1, "rgba(15, 35, 70, 0.85)");
  ctx.fillStyle = g;
  ctx.fillRect(0, CONFIG.AIRPORT_HEIGHT - 240, CONFIG.AIRPORT_WIDTH, 240);
  ctx.fillStyle = "rgba(120, 180, 220, 0.15)";
  for (let i = 0; i < 40; i++) {
    const wx = (time * 0.8 + i * 67) % CONFIG.AIRPORT_WIDTH;
    ctx.fillRect(wx, CONFIG.AIRPORT_HEIGHT - 200 + (i % 5) * 8, 80, 3);
  }
  ctx.fillStyle = "rgba(180, 210, 240, 0.5)";
  ctx.font = "italic 13px sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("Lake Ontario (south)", CONFIG.AIRPORT_WIDTH - 28, CONFIG.AIRPORT_HEIGHT - 28);
}

function drawSectors() {
  SECTORS.forEach((s) => {
    ctx.beginPath();
    ctx.moveTo(s.poly[0][0], s.poly[0][1]);
    s.poly.slice(1).forEach((p) => ctx.lineTo(p[0], p[1]));
    ctx.closePath();
    ctx.fillStyle = s.color;
    ctx.fill();
    ctx.strokeStyle = s.border;
    ctx.lineWidth = 2;
    ctx.setLineDash([12, 8]);
    ctx.stroke();
    ctx.setLineDash([]);
    const cx = s.poly.reduce((a, p) => a + p[0], 0) / s.poly.length;
    const cy = s.poly.reduce((a, p) => a + p[1], 0) / s.poly.length;
    ctx.fillStyle = "rgba(200, 220, 255, 0.85)";
    ctx.font = "bold 14px monospace";
    ctx.textAlign = "center";
    ctx.fillText(s.id, cx, cy);
    ctx.font = "11px monospace";
    ctx.fillStyle = "rgba(160, 180, 210, 0.75)";
    ctx.fillText(s.label.replace(/^.*? /, ""), cx, cy + 14);
  });
}

function drawGround() {
  const grass = ctx.createLinearGradient(0, 0, CONFIG.AIRPORT_WIDTH, CONFIG.AIRPORT_HEIGHT);
  grass.addColorStop(0, "#263822");
  grass.addColorStop(0.5, "#2d4228");
  grass.addColorStop(1, "#243020");
  ctx.fillStyle = grass;
  ctx.fillRect(0, 0, CONFIG.AIRPORT_WIDTH, CONFIG.AIRPORT_HEIGHT - 240);

  ctx.strokeStyle = "rgba(55, 75, 45, 0.25)";
  ctx.lineWidth = 1;
  for (let y = 0; y < CONFIG.AIRPORT_HEIGHT - 240; y += 24) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(CONFIG.AIRPORT_WIDTH, y + Math.sin(y * 0.08) * 2);
    ctx.stroke();
  }

  // Highway 401 stylized (north of field)
  ctx.strokeStyle = "rgba(90, 95, 100, 0.55)";
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.moveTo(120, 72);
  ctx.lineTo(3880, 68);
  ctx.stroke();
  ctx.fillStyle = "rgba(255, 200, 80, 0.35)";
  ctx.font = "11px monospace";
  ctx.textAlign = "left";
  ctx.fillText("401", 180, 78);

  // Terminal / apron cluster (Term 1 / 3 style blob)
  ctx.fillStyle = "#3d4248";
  ctx.fillRect(820, 460, 380, 160);
  ctx.strokeStyle = "rgba(140, 170, 210, 0.35)";
  ctx.lineWidth = 2;
  ctx.strokeRect(820, 460, 380, 160);

  ctx.fillStyle = "#2f343a";
  ctx.fillRect(850, 490, 150, 110);
  ctx.fillRect(1020, 500, 160, 100);
  ctx.fillStyle = "rgba(160, 210, 255, 0.35)";
  for (let gy = 510; gy < 600; gy += 24) {
    for (let gx = 860; gx < 1180; gx += 30) ctx.fillRect(gx, gy, 20, 14);
  }

  ctx.fillStyle = "#353a40";
  ctx.fillRect(1140, 520, 48, 80);
  ctx.fillStyle = "rgba(100, 200, 255, 0.5)";
  ctx.fillRect(1146, 526, 36, 26);

  ctx.fillStyle = "rgba(230, 240, 255, 0.9)";
  ctx.font = "bold 16px sans-serif";
  ctx.textAlign = "left";
  ctx.fillText("Toronto Pearson (CYYZ)", 828, 448);

  drawLakeOntario();
}

function drawTaxiways() {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  TAXIWAYS.forEach((tw) => {
    ctx.strokeStyle = "#4a4e54";
    ctx.lineWidth = tw.width;
    ctx.beginPath();
    ctx.moveTo(tw.points[0][0], tw.points[0][1]);
    tw.points.slice(1).forEach((p) => ctx.lineTo(p[0], p[1]));
    ctx.stroke();
    ctx.strokeStyle = "rgba(255, 210, 0, 0.65)";
    ctx.lineWidth = 2;
    ctx.setLineDash([14, 10]);
    ctx.beginPath();
    ctx.moveTo(tw.points[0][0], tw.points[0][1]);
    tw.points.slice(1).forEach((p) => ctx.lineTo(p[0], p[1]));
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function drawRunway(rwy) {
  const { x, y, length, width, angle, id, active } = rwy;
  const hasConflict = violations.some((v) => v.runway === id);

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);

  const surf = ctx.createLinearGradient(0, -width / 2, 0, width / 2);
  if (!active) {
    surf.addColorStop(0, "#3a3538");
    surf.addColorStop(1, "#353035");
  } else if (hasConflict) {
    surf.addColorStop(0, "#5a2520");
    surf.addColorStop(0.5, "#3d1815");
    surf.addColorStop(1, "#4a2018");
  } else {
    surf.addColorStop(0, "#4a4e54");
    surf.addColorStop(0.5, "#3e4248");
    surf.addColorStop(1, "#484c52");
  }
  ctx.fillStyle = surf;
  ctx.fillRect(0, -width / 2, length, width);

  ctx.strokeStyle = hasConflict ? "rgba(255, 100, 80, 0.85)" : "rgba(255, 255, 255, 0.55)";
  ctx.lineWidth = active ? 3 : 2;
  ctx.beginPath();
  ctx.moveTo(0, -width / 2);
  ctx.lineTo(length, -width / 2);
  ctx.moveTo(0, width / 2);
  ctx.lineTo(length, width / 2);
  ctx.stroke();

  if (active) {
    ctx.fillStyle = "rgba(255, 255, 255, 0.88)";
    for (let i = 0; i < 6; i++) {
      const sy = -width / 2 + 8 + (i * (width - 16)) / 5;
      ctx.fillRect(14, sy, 28, 7);
      ctx.fillRect(length - 42, sy, 28, 7);
    }
    ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
    ctx.lineWidth = 3;
    ctx.setLineDash([36, 28]);
    ctx.beginPath();
    ctx.moveTo(72, 0);
    ctx.lineTo(length - 72, 0);
    ctx.stroke();
    ctx.setLineDash([]);
  } else {
    ctx.fillStyle = "rgba(200, 200, 210, 0.5)";
    ctx.font = "11px monospace";
    ctx.textAlign = "center";
    ctx.fillText("visual", length / 2, -width / 2 - 8);
  }

  const pulse = 0.65 + 0.35 * Math.sin(time * 0.08);
  const lightColor = hasConflict
    ? `rgba(255, 60, 60, ${pulse})`
    : `rgba(255, 250, 200, ${pulse * 0.75})`;
  if (active) {
    for (let lx = 48; lx < length - 36; lx += 58) {
      ctx.beginPath();
      ctx.arc(lx, -width / 2 - 4, 2.5, 0, Math.PI * 2);
      ctx.arc(lx, width / 2 + 4, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = lightColor;
      ctx.fill();
    }
  }

  ctx.fillStyle = "rgba(255, 255, 255, 0.82)";
  ctx.font = `bold ${active ? 22 : 16}px monospace`;
  ctx.textAlign = "center";
  const nums = id.split("/");
  ctx.fillText(nums[0], 52, 7);
  ctx.save();
  ctx.translate(length - 52, 0);
  ctx.rotate(Math.PI);
  ctx.fillText(nums[1], 0, 7);
  ctx.restore();

  ctx.restore();
}

function drawWeatherStorm() {
  const z = weather.zone;
  if (!z) return;

  const { cx, cy, r, type } = z;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  if (type === "heavy_rain") {
    ctx.fillStyle = `rgba(55, 95, 150, ${0.28 + 0.07 * Math.sin(time * 0.05)})`;
    ctx.strokeStyle = "rgba(130, 190, 255, 0.5)";
    ctx.lineWidth = 4;
  } else if (type === "snow_storm") {
    ctx.fillStyle = `rgba(210, 220, 235, ${0.26 + 0.06 * Math.sin(time * 0.04)})`;
    ctx.strokeStyle = "rgba(250, 252, 255, 0.45)";
    ctx.lineWidth = 4;
  } else if (type === "fog") {
    const g = ctx.createRadialGradient(cx, cy, r * 0.15, cx, cy, r);
    g.addColorStop(0, `rgba(140, 150, 165, ${0.38 + 0.08 * Math.sin(time * 0.03)})`);
    g.addColorStop(0.55, "rgba(110, 118, 130, 0.32)");
    g.addColorStop(1, "rgba(85, 92, 102, 0.15)");
    ctx.fillStyle = g;
    ctx.strokeStyle = "rgba(180, 190, 200, 0.4)";
    ctx.lineWidth = 4;
  } else {
    ctx.fillStyle = `rgba(75, 55, 110, ${0.22 + 0.07 * Math.sin(time * 0.06)})`;
    ctx.strokeStyle = "rgba(255, 200, 100, 0.42)";
    ctx.lineWidth = 4;
  }
  ctx.fill();
  ctx.stroke();

  if (type === "heavy_rain") {
    ctx.strokeStyle = "rgba(170, 200, 240, 0.32)";
    ctx.lineWidth = 1.2;
    const steps = Math.min(140, Math.floor(r / 6));
    for (let i = 0; i < steps; i++) {
      const rx = cx - r + ((time * 6 + i * 97) % (2 * r));
      const ry = cy - r + ((time * 16 + i * 73) % (2 * r));
      if ((rx - cx) ** 2 + (ry - cy) ** 2 > r * r) continue;
      ctx.beginPath();
      ctx.moveTo(rx, ry);
      ctx.lineTo(rx - 4, ry + 18);
      ctx.stroke();
    }
  } else if (type === "snow_storm") {
    ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
    const flakes = Math.min(100, Math.floor(r / 8));
    for (let i = 0; i < flakes; i++) {
      const rx = cx - r + ((time * 2.5 + i * 83) % (2 * r));
      const ry = cy - r + ((time * 3.5 + i * 59) % (2 * r));
      if ((rx - cx) ** 2 + (ry - cy) ** 2 > r * r) continue;
      ctx.beginPath();
      ctx.arc(rx, ry, 1.4, 0, Math.PI * 2);
      ctx.fill();
    }
  } else if (type === "fog") {
    ctx.fillStyle = `rgba(200, 208, 218, ${0.08 + 0.04 * Math.sin(time * 0.04)})`;
    for (let i = 0; i < 45; i++) {
      const rx = cx - r + ((time * 1.2 + i * 111) % (2 * r));
      const ry = cy - r + ((time * 0.9 + i * 67) % (2 * r));
      if ((rx - cx) ** 2 + (ry - cy) ** 2 > r * r) continue;
      ctx.beginPath();
      ctx.arc(rx, ry, 3 + (i % 4), 0, Math.PI * 2);
      ctx.fill();
    }
  } else {
    ctx.strokeStyle = `rgba(255, 230, 140, ${0.3 + 0.22 * Math.sin(time * 0.18)})`;
    ctx.lineWidth = 2.5;
    for (let k = 0; k < 6; k++) {
      const ang = time * 0.07 + k * 1.05;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * r * 0.12, cy + Math.sin(ang) * r * 0.12);
      ctx.lineTo(cx + Math.cos(ang + 0.35) * r * 0.92, cy + Math.sin(ang + 0.35) * r * 0.92);
      ctx.stroke();
    }
  }

  ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
  ctx.font = "bold 15px monospace";
  ctx.textAlign = "center";
  ctx.fillText(z.label, cx, cy + 6);
  ctx.font = "11px monospace";
  ctx.fillStyle = "rgba(220, 230, 245, 0.75)";
  ctx.fillText("Mesoscale cell (~30% area)", cx, cy + 24);

  ctx.restore();
}

// ─── AIRCRAFT ───────────────────────────────────────────────────────────────

const AIRCRAFT_TYPES = [
  { code: "B77W", weight: "Heavy", size: 1.25 },
  { code: "A321", weight: "Medium", size: 1.0 },
  { code: "B738", weight: "Medium", size: 1.0 },
  { code: "E175", weight: "Medium", size: 0.88 },
];

const CALLSIGNS = ["ACA", "WJA", "DAL", "UAL"];

function activeParallelRunways() {
  return RUNWAYS.filter((r) => r.active);
}

function pickRunwaySlot() {
  const list = activeParallelRunways();
  return list[Math.floor(Math.random() * list.length)];
}

function isRunwayBusy(rwyId, nowFrame) {
  const until = runwayBusyUntil[rwyId];
  return until != null && until > nowFrame;
}

function spawnAircraft() {
  if (aircraft.length >= CONFIG.MAX_AIRCRAFT) return;

  const type = AIRCRAFT_TYPES[Math.floor(Math.random() * AIRCRAFT_TYPES.length)];
  const prefix = CALLSIGNS[Math.floor(Math.random() * CALLSIGNS.length)];
  const num = Math.floor(Math.random() * 700) + 200;
  const rwy = pickRunwaySlot();
  const thr = runwayThreshold(rwy);
  const depart = Math.random() > 0.48;

  if (depart) {
    const startX = thr.x - 80;
    const startY = thr.y + (Math.random() * 10 - 5);
    const ac = {
      id: `${prefix}${num}`,
      type: type.code,
      weight: type.weight,
      size: type.size,
      x: startX,
      y: startY,
      targetX: CONFIG.AIRPORT_WIDTH + 200,
      targetY: thr.y + (Math.random() * 24 - 12),
      heading: 0,
      speed: 2.2 + Math.random() * 1.4,
      runway: rwy.id,
      phase: "DEPART",
      sector: sectorAtPoint(startX, startY),
      rerouted: false,
      trail: [],
      waypointQueue: [],
      altitude_ft: 450 + Math.random() * 120,
      vertical_speed_fpm: 1800,
      trackHistory: [],
      on_ground: false,
    };
    syncAircraftGeo(ac);
    updateAltitudeAndVs(ac);
    appendTrackSample(ac);
    aircraft.push(ac);
    runwayBusyUntil[rwy.id] = time + 180;
  } else {
    const startX = -120;
    const startY = thr.y + (Math.random() * 36 - 18);
    const holdSector =
      HOLD_SECTOR_IDS[Math.floor(Math.random() * HOLD_SECTOR_IDS.length)];
    const busy = isRunwayBusy(rwy.id, time);

    const ac = {
      id: `${prefix}${num}`,
      type: type.code,
      weight: type.weight,
      size: type.size,
      x: startX,
      y: startY,
      targetX: thr.x,
      targetY: thr.y,
      heading: Math.atan2(thr.y - startY, thr.x - startX),
      speed: 2.0 + Math.random() * 1.2,
      runway: rwy.id,
      phase: busy ? "HOLD" : "ARRIVE",
      sector: sectorAtPoint(startX, startY),
      rerouted: busy,
      holdSector,
      trail: [],
      waypointQueue: [],
      altitude_ft: 3800 + Math.random() * 600,
      vertical_speed_fpm: -900,
      trackHistory: [],
      on_ground: false,
    };

    if (busy) {
      const hp = findSectorHold(holdSector);
      ac.waypointQueue.push({ x: hp.x, y: hp.y, kind: "hold" });
      ac.waypointQueue.push({ x: thr.x - 400, y: thr.y, kind: "vector" });
      ac.waypointQueue.push({ x: thr.x, y: thr.y, kind: "final" });
      ac.targetX = ac.waypointQueue[0].x;
      ac.targetY = ac.waypointQueue[0].y;
      ac.phase = "HOLD";
      ac.heading = Math.atan2(ac.targetY - ac.y, ac.targetX - ac.x);
    }

    syncAircraftGeo(ac);
    updateAltitudeAndVs(ac);
    appendTrackSample(ac);
    aircraft.push(ac);
  }
}

function advanceWaypoint(ac) {
  if (!ac.waypointQueue?.length) return;
  ac.waypointQueue.shift();
  if (ac.waypointQueue.length) {
    ac.targetX = ac.waypointQueue[0].x;
    ac.targetY = ac.waypointQueue[0].y;
    if (ac.waypointQueue[0].kind === "final") ac.phase = "ARRIVE";
  }
}

function updateAircraft() {
  const toRemove = new Set();

  aircraft.forEach((ac, idx) => {
    const dx = ac.targetX - ac.x;
    const dy = ac.targetY - ac.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    // HOLD: wait until runway free, then continue approach
    if (ac.phase === "HOLD" && ac.waypointQueue?.length) {
      const rwy = getRunwayById(ac.runway);
      if (rwy && !isRunwayBusy(ac.runway, time) && ac.waypointQueue[0]?.kind === "hold") {
        advanceWaypoint(ac);
        ac.phase = "VECTOR";
      }
    }

    if (dist < 28) {
      if (ac.waypointQueue?.length) {
        advanceWaypoint(ac);
        return;
      }
      if (ac.phase === "HOLD" || ac.phase === "TAXI") {
        return;
      }
      if (ac.phase === "DEPART") {
        toRemove.add(idx);
        return;
      }
      if (ac.phase === "ARRIVE" || ac.phase === "VECTOR") {
        runwayBusyUntil[ac.runway] = time + 200;
        toRemove.add(idx);
        return;
      }
      toRemove.add(idx);
      return;
    }

    ac.heading = Math.atan2(dy, dx);
    ac.x += Math.cos(ac.heading) * ac.speed;
    ac.y += Math.sin(ac.heading) * ac.speed;
    ac.sector = sectorAtPoint(ac.x, ac.y);

    syncAircraftGeo(ac);
    updateAltitudeAndVs(ac);
    appendTrackSample(ac);

    ac.trail.push({ x: ac.x, y: ac.y, age: 0 });
    ac.trail.forEach((t) => t.age++);
    ac.trail = ac.trail.filter((t) => t.age < 36);
  });

  aircraft = aircraft.filter((_, i) => !toRemove.has(i));
}

function projectedSegment(ac) {
  const L = CONFIG.PROJECT_PATH_LEN;
  const x2 = ac.x + Math.cos(ac.heading) * L;
  const y2 = ac.y + Math.sin(ac.heading) * L;
  return { x1: ac.x, y1: ac.y, x2, y2 };
}

/** Prediction-based alerts (60 s horizon, 10 s steps) + canvas track crossing markers */
function evaluateAirspaceDynamics() {
  trajectoryAlerts = [];
  const out = [];
  if (!aircraft.length) return out;

  const preds = aircraft.map((ac) => ({
    ac,
    samples: predictTrajectorySamples(ac),
  }));

  if (weather.storm_geo) {
    for (const { ac, samples } of preds) {
      const intr = projectedStormIntrusion(samples, weather.storm_geo);
      if (intr) {
        const conf = Math.min(1, 1 - intr.distance_nm / Math.max(weather.storm_geo.radius_nm, 0.1));
        out.push({
          rule: "storm_avoidance_predicted",
          flights: [ac.id],
          severity: severityFromConfidence(conf),
          distance: `${intr.distance_nm.toFixed(2)} NM`,
          evidence: { ...intr, storm: weather.storm_geo },
          suggested_action: rerouteForStorm(ac.id, intr.eta_sec),
        });
      }
    }
  }

  for (let i = 0; i < aircraft.length; i++) {
    for (let j = i + 1; j < aircraft.length; j++) {
      const a = aircraft[i];
      const b = aircraft[j];
      const nm = haversine_nm(a.lat, a.lon, b.lat, b.lon);
      const ad = Math.abs(a.altitude_ft - b.altitude_ft);
      if (minimumSeparationViolated(nm, ad)) {
        const conf = Math.max(0, Math.min(1, 1 - nm / RULES.MIN_HORIZONTAL_SEP_NM));
        out.push({
          rule: "minimum_separation",
          flights: [a.id, b.id],
          severity: severityFromConfidence(conf),
          distance: nm.toFixed(2),
          evidence: { distance_nm: nm, alt_diff_ft: ad, scope: "current" },
          suggested_action: rerouteForSeparation(
            [a.id, b.id],
            { distance_nm: nm, alt_diff_ft: ad },
            false,
          ),
        });
      }

      const pc = findPredictedSeparationConflict(preds[i].samples, preds[j].samples);
      const sa = projectedSegment(a);
      const sb = projectedSegment(b);
      const hit = segmentIntersection(sa.x1, sa.y1, sa.x2, sa.y2, sb.x1, sb.y1, sb.x2, sb.y2);

      if (pc) {
        const conf = Math.max(0, Math.min(1, 1 - pc.distance_nm / RULES.MIN_HORIZONTAL_SEP_NM));
        out.push({
          rule: "minimum_separation_predicted",
          flights: [a.id, b.id],
          severity: severityFromConfidence(conf),
          distance: pc.distance_nm.toFixed(2),
          evidence: { ...pc, scope: "predicted_60s" },
          suggested_action: rerouteForSeparation(
            [a.id, b.id],
            pc,
            !!hit,
          ),
          ix: hit?.x,
          iy: hit?.y,
        });
        if (hit) {
          trajectoryAlerts.push({
            rule: "path",
            flights: [a.id, b.id],
            severity: "red",
            distance: "X",
            ix: hit.x,
            iy: hit.y,
          });
        }
      } else if (hit) {
        const ia = Math.floor(hit.t * (preds[i].samples.length - 1));
        const ib = Math.floor(hit.u * (preds[j].samples.length - 1));
        const si = preds[i].samples[Math.max(0, Math.min(ia, preds[i].samples.length - 1))];
        const sj = preds[j].samples[Math.max(0, Math.min(ib, preds[j].samples.length - 1))];
        const adp = Math.abs(si.alt_ft - sj.alt_ft);
        const nmp = haversine_nm(si.lat, si.lon, sj.lat, sj.lon);
        if (adp < RULES.MIN_VERTICAL_SEP_FT && nmp < RULES.MIN_HORIZONTAL_SEP_NM * 1.5) {
          trajectoryAlerts.push({
            rule: "path",
            flights: [a.id, b.id],
            severity: "yellow",
            distance: "~",
            ix: hit.x,
            iy: hit.y,
          });
          out.push({
            rule: "track_crossing_predicted",
            flights: [a.id, b.id],
            severity: "yellow",
            distance: nmp.toFixed(2),
            evidence: { alt_diff_ft: adp, distance_nm: nmp, scope: "geometry" },
            suggested_action: rerouteForSeparation([a.id, b.id], { alt_diff_ft: adp, distance_nm: nmp }, true),
            ix: hit.x,
            iy: hit.y,
          });
        }
      }

      if (a.weight === "Heavy" && (b.weight === "Medium" || b.weight === "Light")) {
        const ev = wakeViolationEvidence(
          { lat: a.lat, lon: a.lon, altitude_ft: a.altitude_ft, heading_deg: a.heading_deg },
          { lat: b.lat, lon: b.lon, altitude_ft: b.altitude_ft, heading_deg: b.heading_deg },
        );
        if (ev) {
          out.push({
            rule: "wake_turbulence",
            flights: [a.id, b.id],
            severity: severityFromConfidence(ev.confidence),
            distance: ev.trail_nm.toFixed(2),
            evidence: ev,
            suggested_action: rerouteForWake(a.id, b.id, ev),
          });
        }
      }
      if (b.weight === "Heavy" && (a.weight === "Medium" || a.weight === "Light")) {
        const ev = wakeViolationEvidence(
          { lat: b.lat, lon: b.lon, altitude_ft: b.altitude_ft, heading_deg: b.heading_deg },
          { lat: a.lat, lon: a.lon, altitude_ft: a.altitude_ft, heading_deg: a.heading_deg },
        );
        if (ev) {
          out.push({
            rule: "wake_turbulence",
            flights: [b.id, a.id],
            severity: severityFromConfidence(ev.confidence),
            distance: ev.trail_nm.toFixed(2),
            evidence: ev,
            suggested_action: rerouteForWake(b.id, a.id, ev),
          });
        }
      }
    }
  }

  return out;
}

function checkCrashes() {
  const crashViolations = [];
  const removal = new Set();
  for (let i = 0; i < aircraft.length; i++) {
    for (let j = i + 1; j < aircraft.length; j++) {
      if (removal.has(i) || removal.has(j)) continue;
      const a = aircraft[i];
      const b = aircraft[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const d = Math.sqrt(dx * dx + dy * dy);
      const nm = haversine_nm(a.lat, a.lon, b.lat, b.lon);
      if (d < CONFIG.CRASH_DIST || nm < CONFIG.CRASH_NM) {
        explosions.push({
          x: (a.x + b.x) / 2,
          y: (a.y + b.y) / 2,
          t: 0,
          particles: Array.from({ length: 28 }, (_, k) => ({
            ang: (Math.PI * 2 * k) / 28 + Math.random() * 0.5,
            spd: 3 + Math.random() * 6,
            life: 40 + Math.floor(Math.random() * 20),
          })),
        });
        crashViolations.push({
          rule: "crash",
          flights: [a.id, b.id],
          distance: "0",
          severity: "red",
        });
        removal.add(i);
        removal.add(j);
      }
    }
  }
  if (removal.size) {
    aircraft = aircraft.filter((_, idx) => !removal.has(idx));
  }
  return crashViolations;
}

function checkConflicts(crashViolations) {
  const dyn = evaluateAirspaceDynamics();
  const base = currentMode === "live" ? [] : scenarioStaticViolations.slice();
  violations = [...base, ...crashViolations, ...dyn];
}

function drawProjectedPaths() {
  aircraft.forEach((ac) => {
    const L = CONFIG.PROJECT_PATH_LEN;
    const x2 = ac.x + Math.cos(ac.heading) * L;
    const y2 = ac.y + Math.sin(ac.heading) * L;
    const pathConflict = trajectoryAlerts.some(
      (t) => t.flights?.includes(ac.id) && t.rule === "path",
    );
    ctx.strokeStyle = pathConflict ? "rgba(255, 80, 80, 0.55)" : "rgba(120, 200, 255, 0.22)";
    ctx.lineWidth = pathConflict ? 3 : 2;
    ctx.setLineDash([10, 14]);
    ctx.beginPath();
    ctx.moveTo(ac.x, ac.y);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function drawExplosions() {
  explosions = explosions.filter((ex) => {
    ex.t++;
    const cx = ex.x;
    const cy = ex.y;
    ex.particles.forEach((p) => {
      const px = cx + Math.cos(p.ang) * p.spd * ex.t * 0.45;
      const py = cy + Math.sin(p.ang) * p.spd * ex.t * 0.45 - ex.t * 0.08;
      const alpha = Math.max(0, 1 - ex.t / p.life);
      ctx.beginPath();
      ctx.arc(px, py, 4 + alpha * 6, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, ${120 + ex.t}, 40, ${alpha * 0.9})`;
      ctx.fill();
    });
    ctx.beginPath();
    ctx.arc(cx, cy, 8 + ex.t * 0.8, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 200, 80, ${Math.max(0, 0.5 - ex.t / 50)})`;
    ctx.fill();
    return ex.t < 55;
  });
}

function drawAircraft(ac) {
  const isConflict = violations.some((v) => v.flights?.includes(ac.id));
  const isPath = trajectoryAlerts.some((v) => v.flights?.includes(ac.id) && v.rule === "path");

  ac.trail.forEach((t) => {
    const alpha = Math.max(0, 0.38 * (1 - t.age / 36));
    const r = Math.max(0, 3.5 * (1 - t.age / 36));
    if (r > 0) {
      ctx.beginPath();
      ctx.arc(t.x, t.y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(130, 200, 255, ${alpha})`;
      ctx.fill();
    }
  });

  ctx.save();
  ctx.translate(ac.x, ac.y);
  ctx.rotate(ac.heading);

  const s = ac.size;
  const color = isPath ? "#ff9966" : isConflict ? "#ff5555" : "#d8e4f0";

  ctx.beginPath();
  ctx.ellipse(5, 7, 32 * s, 11 * s, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.22)";
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(14 * s, -4 * s);
  ctx.lineTo(-7 * s, -38 * s);
  ctx.lineTo(-16 * s, -38 * s);
  ctx.lineTo(-4 * s, -4 * s);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(14 * s, 4 * s);
  ctx.lineTo(-7 * s, 38 * s);
  ctx.lineTo(-16 * s, 38 * s);
  ctx.lineTo(-4 * s, 4 * s);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = isConflict ? "#cc5555" : "#b8c8d8";
  ctx.beginPath();
  ctx.moveTo(-22 * s, -3 * s);
  ctx.lineTo(-32 * s, -18 * s);
  ctx.lineTo(-38 * s, -18 * s);
  ctx.lineTo(-28 * s, -3 * s);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.ellipse(0, 0, 40 * s, 7 * s, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "rgba(130, 210, 255, 0.75)";
  ctx.beginPath();
  ctx.ellipse(30 * s, 0, 7 * s, 4 * s, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();

  ctx.fillStyle = "rgba(0, 0, 0, 0.78)";
  roundRect(ctx, ac.x - 34, ac.y + 28, 72, 22, 4);
  ctx.fill();
  ctx.fillStyle = isPath ? "#ffb088" : "#ffffff";
  ctx.font = "bold 11px monospace";
  ctx.textAlign = "center";
  const phaseTag =
    ac.phase === "HOLD" ? "HOLD" : ac.phase === "VECTOR" ? "VEC" : ac.phase.slice(0, 3);
  ctx.fillText(`${ac.id} · ${phaseTag}`, ac.x, ac.y + 43);
}

function drawConflictLines() {
  violations.forEach((v) => {
    if (v.rule === "path" || v.rule === "crash") return;
    if (v.flights?.length >= 2) {
      const ac1 = aircraft.find((a) => a.id === v.flights[0]);
      const ac2 = aircraft.find((a) => a.id === v.flights[1]);
      if (ac1 && ac2) {
        const pulse = 0.5 + 0.5 * Math.sin(time * 0.2);
        ctx.strokeStyle =
          v.severity === "red" ? `rgba(255, 50, 50, ${pulse})` : `rgba(255, 180, 50, ${pulse})`;
        ctx.lineWidth = 4;
        ctx.setLineDash([12, 8]);
        ctx.beginPath();
        ctx.moveTo(ac1.x, ac1.y);
        ctx.lineTo(ac2.x, ac2.y);
        ctx.stroke();
        ctx.setLineDash([]);
        const mx = (ac1.x + ac2.x) / 2;
        const my = (ac1.y + ac2.y) / 2;
        ctx.fillStyle = "rgba(255, 80, 80, 0.95)";
        ctx.font = "bold 13px monospace";
        ctx.textAlign = "center";
        ctx.fillText(`${v.distance} NM`, mx, my - 10);
      }
    }
  });
}

function drawTrajectoryCrossMarkers() {
  trajectoryAlerts.forEach((t) => {
    if (t.ix == null) return;
    const pulse = 0.6 + 0.4 * Math.sin(time * 0.25);
    ctx.strokeStyle = `rgba(255, 60, 60, ${pulse})`;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(t.ix, t.iy, 16 + pulse * 6, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgba(255, 100, 100, 0.95)";
    ctx.font = "bold 12px monospace";
    ctx.textAlign = "center";
    ctx.fillText("PATH X", t.ix, t.iy - 22);
  });
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// ─── UI ─────────────────────────────────────────────────────────────────────

function updateUI() {
  const alertCount = violations.length;
  ui.aircraftCount.textContent = aircraft.length;
  ui.violationCount.textContent = String(alertCount);
  ui.violationCount.parentElement.classList.toggle("alert", alertCount > 0);
  ui.windValue.textContent = `${weather.wind_speed_kts}kt`;

  ui.headerStatus.classList.toggle("alert", alertCount > 0);
  const wxActive = !!(weather.storm && weather.zone);
  ui.stormBanner.classList.toggle("visible", wxActive);
  if (ui.stormBannerText) {
    ui.stormBannerText.textContent = wxActive
      ? `ACTIVE: ${weather.zone.label} — single mesoscale cell (~30% map)`
      : "";
  }
  ui.alertsPanel.classList.toggle("has-alerts", alertCount > 0);

  const allAlerts = [...violations];
  if (allAlerts.length === 0) {
    ui.alertsList.innerHTML = '<div class="no-alerts">All clear</div>';
  } else {
    ui.alertsList.innerHTML = allAlerts
      .map((v) => {
        const ruleLabel =
          v.rule === "wake_turbulence"
            ? "WAKE"
            : v.rule === "wake"
              ? "WAKE"
            : v.rule === "path"
              ? "PATH"
              : v.rule === "crash"
                ? "CRASH"
              : v.rule === "minimum_separation" || v.rule === "minimum_separation_predicted"
                ? "SEP"
              : v.rule === "storm_avoidance_predicted"
                ? "WX"
              : v.rule === "track_crossing_predicted"
                ? "XING"
              : v.rule === "separation"
                ? "SEP"
              : v.rule === "storm"
                ? "WX"
              : String(v.rule).slice(0, 8).toUpperCase();
        return `
      <div class="alert-item ${v.severity}">
        <span class="alert-rule">${ruleLabel}</span>
        <span class="alert-flights">${v.flights.join(" / ")}</span>
        <span class="alert-dist">${v.distance ?? "—"}</span>
      </div>
    `;
      })
      .join("");
  }

  if (violations.some((v) => v.rule === "crash")) {
    const c = violations.find((x) => x.rule === "crash");
    ui.aiContent.innerHTML = `
      <div class="ai-action">
        <div class="ai-target">${c.flights.join(" / ")}</div>
        <div class="ai-command">LOSS OF SEP</div>
        <div class="ai-reason">Collision — incident response</div>
      </div>
    `;
  } else {
    const top = violations.find((v) => v.suggested_action);
    if (top?.suggested_action) {
      ui.aiContent.innerHTML = `
      <div class="ai-action">
        <div class="ai-target">${top.flights.join(" / ")}</div>
        <div class="ai-command">${top.rule.replace(/_/g, " ")}</div>
        <div class="ai-reason" style="font-size:0.72rem;text-align:left;line-height:1.35">${top.suggested_action}</div>
      </div>
    `;
    } else if (trajectoryAlerts[0]) {
      const pathHit = trajectoryAlerts[0];
      ui.aiContent.innerHTML = `
      <div class="ai-action">
        <div class="ai-target">${pathHit.flights.join(" & ")}</div>
        <div class="ai-command">TRACK GEOMETRY</div>
        <div class="ai-reason">Projected paths converge — verify altitude crossing</div>
      </div>
    `;
    } else if (violations.length > 0) {
      const v = violations.filter((x) => x.rule !== "crash")[0];
      if (v) {
        ui.aiContent.innerHTML = `
      <div class="ai-action">
        <div class="ai-target">${v.flights.join(" / ")}</div>
        <div class="ai-command">ALERT</div>
        <div class="ai-reason">${v.rule}</div>
      </div>
    `;
      }
    } else {
      ui.aiContent.innerHTML = '<div class="ai-idle">Monitoring CYYZ…</div>';
    }
  }

  ui.flightsList.innerHTML =
    aircraft
      .map((ac) => {
        const isConflict = violations.some((v) => v.flights?.includes(ac.id));
        return `
      <div class="flight-row ${isConflict ? "conflict" : ""}">
        <span class="flight-id">${ac.id}</span>
        <span class="flight-type">${ac.type}</span>
        <span class="flight-phase">${ac.phase} · ${ac.sector}</span>
      </div>
    `;
      })
      .join("") || '<div class="no-flights">No aircraft</div>';
}

// ─── RENDER / TICK ──────────────────────────────────────────────────────────

function render() {
  time++;
  ctx.clearRect(0, 0, CONFIG.AIRPORT_WIDTH, CONFIG.AIRPORT_HEIGHT);

  drawGround();
  drawSectors();
  drawTaxiways();
  RUNWAYS.forEach(drawRunway);
  drawWeatherStorm();
  drawProjectedPaths();
  drawTrajectoryCrossMarkers();
  drawConflictLines();
  drawExplosions();
  aircraft.forEach(drawAircraft);

  requestAnimationFrame(render);
}

function update() {
  updateAircraft();
  const crashViolations = checkCrashes();
  checkConflicts(crashViolations);
  updateUI();
}

function startLiveMode() {
  currentMode = "live";
  weather.zone = rollRandomStorm();
  weather.storm = true;

  Object.keys(runwayBusyUntil).forEach((k) => delete runwayBusyUntil[k]);
  if (spawnIntervalId) clearInterval(spawnIntervalId);
  spawnIntervalId = setInterval(spawnAircraft, CONFIG.SPAWN_INTERVAL);
  for (let i = 0; i < 3; i++) setTimeout(spawnAircraft, i * 400);
}

function runScenario(key) {
  if (spawnIntervalId) {
    clearInterval(spawnIntervalId);
    spawnIntervalId = null;
  }
  aircraft = [];
  violations = [];
  trajectoryAlerts = [];
  explosions = [];
  scenarioStaticViolations = [];

  if (key === "live") {
    startLiveMode();
    return;
  }

  currentMode = "scenario";
  const scenario = getScenario(key);
  weather.zone = scenario.weather?.zone ?? rollRandomStorm();
  weather.storm = true;

  scenarioStaticViolations = scenario.violations || [];

  aircraft = (scenario.aircraft || []).map((ac) => {
    const dy = (ac.targetY ?? ac.y) - ac.y;
    const dx = (ac.targetX ?? ac.x) - ac.x;
    let heading = Math.atan2(dy, dx);
    if (!Number.isFinite(heading)) heading = 0;
    const m = {
      ...ac,
      trail: [],
      trackHistory: [],
      sector: sectorAtPoint(ac.x, ac.y),
      rerouted: ac.phase === "HOLD",
      waypointQueue: ac.waypointQueue || [],
      heading,
      altitude_ft:
        ac.altitude_ft ??
        (ac.phase === "DEPART"
          ? 500
          : ac.phase === "HOLD"
            ? 3000
            : ac.phase === "TAXI"
              ? 0
              : 3800),
      vertical_speed_fpm: ac.vertical_speed_fpm ?? 0,
      on_ground: ac.phase === "TAXI",
      size: ac.size ?? 1,
    };
    syncAircraftGeo(m);
    updateAltitudeAndVs(m);
    appendTrackSample(m);
    return m;
  });

  violations = scenarioStaticViolations.slice();
  updateUI();
}

// ─── EVENTS ─────────────────────────────────────────────────────────────────

document.getElementById("zoomIn").onclick = () => {
  const rect = container.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  const oldZoom = zoom;
  zoom = Math.min(CONFIG.MAX_ZOOM, zoom + CONFIG.ZOOM_STEP);
  panX = cx - (cx - panX) * (zoom / oldZoom);
  panY = cy - (cy - panY) * (zoom / oldZoom);
  updateCanvasTransform();
};

document.getElementById("zoomOut").onclick = () => {
  const rect = container.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  const oldZoom = zoom;
  zoom = Math.max(CONFIG.MIN_ZOOM, zoom - CONFIG.ZOOM_STEP);
  panX = cx - (cx - panX) * (zoom / oldZoom);
  panY = cy - (cy - panY) * (zoom / oldZoom);
  updateCanvasTransform();
};

document.getElementById("zoomReset").onclick = () => {
  zoom = 0.24;
  centerView();
};

container.addEventListener("mousedown", (e) => {
  isDragging = true;
  dragStart = { x: e.clientX - panX, y: e.clientY - panY };
  container.style.cursor = "grabbing";
});

document.addEventListener("mousemove", (e) => {
  if (!isDragging) return;
  panX = e.clientX - dragStart.x;
  panY = e.clientY - dragStart.y;
  updateCanvasTransform();
});

document.addEventListener("mouseup", () => {
  isDragging = false;
  container.style.cursor = "grab";
});

container.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = container.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;
  const oldZoom = zoom;
  const delta = e.deltaY > 0 ? -CONFIG.ZOOM_STEP : CONFIG.ZOOM_STEP;
  zoom = Math.max(CONFIG.MIN_ZOOM, Math.min(CONFIG.MAX_ZOOM, zoom + delta));
  panX = mouseX - (mouseX - panX) * (zoom / oldZoom);
  panY = mouseY - (mouseY - panY) * (zoom / oldZoom);
  updateCanvasTransform();
});

document.getElementById("runBtn").onclick = () => {
  runScenario(document.getElementById("scenarioSelect").value);
};

document.getElementById("scenarioSelect").onchange = (e) => {
  runScenario(e.target.value);
};

// ─── INIT ───────────────────────────────────────────────────────────────────

resizeCanvas();
render();
setInterval(update, CONFIG.UPDATE_INTERVAL);
startLiveMode();

/** Training / evaluation JSON (includes lat/lon track_history, weather envelope) */
window.__runwaiTrainingExport = () => JSON.stringify(getSimulationExport(), null, 2);
