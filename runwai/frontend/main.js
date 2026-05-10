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
  SPAWN_INTERVAL: 7800,
  UPDATE_INTERVAL: 50,
  MAX_AIRCRAFT: 3,
  PROJECT_PATH_LEN: 480,
  /** Loss of separation on map (pixels) — also checked via NM */
  CRASH_DIST: 22,
  CRASH_NM: 0.04,
  /** FastAPI bridge (runwai/server.py). Empty string disables POST. */
  API_BASE_URL: typeof window !== "undefined" ? window.__RUNWAI_API__ || "http://127.0.0.1:8000" : "",
  /** Send full simulation JSON to Python every N ms (flight packages + weather + alerts). */
  API_PUSH_INTERVAL_MS: 2000,
  /** If true, POST adds ?full_pipeline=true (rules + LLM + decision — requires model env on server). */
  API_FULL_PIPELINE: false,
  /** If true, POST adds ?ml_advisory=true — Qwen writes conflict/reroute text into alert cards. */
  API_ML_ADVISORY: true,
};

/** Canvas typography tuned for periodic screenshots (ML / GPU inference). */
const MAP_FONT = {
  FLIGHT_TAG: "bold 30px monospace",
  SECTOR_ID: "bold 27px monospace",
  SECTOR_SUB: "17px monospace",
  STORM_TITLE: "bold 38px monospace",
  STORM_SUB: "22px monospace",
  CONFLICT_NM: "bold 32px monospace",
  PATH_MARKER: "bold 26px monospace",
  ARPT_TITLE: "bold 28px sans-serif",
  LAKE: "italic 22px sans-serif",
};

/** AI sidebar latch — avoids flicker when advisory text updates every tick. */
const AI_PANEL_LATCH_MS = 2600;
let aiPanelLatch = { key: "", html: "", lockUntil: 0 };

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

/** Five discrete sectors used for deterministic reroute / hold advice (screenshot-stable labels). */
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
/** Qwen / API: natural-language advisories (reroute lines) from POST /api/simulation/tick?ml_advisory=true */
let mlAdvisoriesFromApi = [];
/** Qwen-only forward-looking pair risks (telemetry), distinct from rule engine */
let mlPredictionsFromApi = [];
let multimodalContextFromApi = "";
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

/** Stable reroute sector per flight — screenshot-friendly (no random flicker). */
function pickDeterministicRerouteSector(callsign, currentSectorId) {
  const pool = HOLD_SECTOR_IDS.filter((id) => id !== currentSectorId && id !== "—");
  if (!pool.length) return "A12";
  let h = 2166136261;
  const seed = `${callsign}|${currentSectorId ?? ""}`;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  return pool[Math.abs(h) % pool.length];
}

const RULE_SORT_PRIORITY = {
  crash: 0,
  minimum_separation: 1,
  minimum_separation_predicted: 2,
  separation: 1,
  wake_turbulence: 3,
  wake: 3,
  storm_avoidance_predicted: 4,
  storm: 4,
  track_crossing_predicted: 5,
  runway_hold_reroute: 12,
};

/** Shown above alert cards — matches simulator behavior (hold sectors when runway saturated / wx). */
const REROUTE_POLICY_TEXT =
  "If parallel runways are busy or weather threatens the approach, vector aircraft to a safer hold sector (A12, C03, E05, B07, D14) and keep them clear of hazards until landing capacity or METAR improves.";

function violationSortKey(v) {
  return RULE_SORT_PRIORITY[v.rule] ?? 48;
}

function sortViolationsStable(list) {
  return [...list].sort((a, b) => {
    const pa = violationSortKey(a);
    const pb = violationSortKey(b);
    if (pa !== pb) return pa - pb;
    const fa = (a.flights || []).join(",");
    const fb = (b.flights || []).join(",");
    if (fa !== fb) return fa < fb ? -1 : 1;
    return String(a.rule).localeCompare(String(b.rule));
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function ruleExplanationFor(rule) {
  const R = {
    minimum_separation:
      "Minimum separation: keep ≥5 NM horizontally and ≥1000 ft vertically between IFR aircraft unless otherwise cleared.",
    minimum_separation_predicted:
      "Forecast separation: within ~60 s, predicted tracks drop below horizontal and/or vertical minima unless vectored.",
    storm_avoidance_predicted:
      "Weather avoidance: do not penetrate hazardous convection; vector around the cell or hold outside the hazard.",
    wake_turbulence:
      "Wake turbulence: lighter aircraft trailing a heavy must stay ≥6 NM in trail with adequate vertical offset.",
    track_crossing_predicted:
      "Crossing tracks: projected paths intersect with insufficient vertical spacing at the crossing region.",
    crash: "Loss of separation on the surface — collision.",
    separation:
      "Minimum separation: aircraft closer than rule minima for parallel runway / terminal operations.",
    storm: "Hazardous weather: turbulence, icing, windshear, or visibility limits near the cell.",
    wake: "Wake turbulence spacing from heavy aircraft — follower needs trail distance or altitude.",
    path: "Geometry alert: projected paths converge — verify altitude crossing.",
    runway_hold_reroute:
      "Runway saturation: arrival was assigned a published hold in an alternate sector until the assigned runway is available.",
  };
  return R[rule] || "Flagged by the RunwAI rules engine.";
}

function ruleTitleForUi(rule) {
  const T = {
    storm_avoidance_predicted: "Storm avoidance (forecast)",
    minimum_separation_predicted: "Separation (forecast)",
    minimum_separation: "Minimum separation",
    wake_turbulence: "Wake turbulence",
    track_crossing_predicted: "Crossing tracks",
    crash: "Loss of separation",
    separation: "Minimum separation",
    storm: "Weather hazard",
    wake: "Wake turbulence",
    runway_hold_reroute: "Runway busy — sector hold",
  };
  return T[rule] || String(rule).replace(/_/g, " ");
}

function enrichViolationForUi(v) {
  const rule_explanation = v.rule_explanation || ruleExplanationFor(v.rule);
  let suggested_action = v.suggested_action;
  if (!suggested_action) {
    if (v.rule === "storm") {
      const id = v.flights?.[0];
      const ac = id ? aircraft.find((a) => a.id === id) : null;
      const alt = pickDeterministicRerouteSector(id || "UNK", ac?.sector || "E05");
      suggested_action = `Reroute ${id} to sector ${alt} holding; remain ≥${RULES.MIN_HORIZONTAL_SEP_NM} NM from the hazard until conditions improve.`;
    } else if (v.rule === "separation") {
      suggested_action = `Resolve spacing: heading offset or altitude crossing until ≥${RULES.MIN_HORIZONTAL_SEP_NM} NM horizontal and ≥${RULES.MIN_VERTICAL_SEP_FT} ft vertical between flights.`;
    } else if (v.rule === "wake") {
      suggested_action = `Wake spacing: extend trail to ≥6 NM or climb follower +1000 ft above heavy wake path before re-joining route.`;
    }
  }
  return { ...v, rule_explanation, suggested_action };
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
  const alt = pickDeterministicRerouteSector(acId, ac?.sector || "E05");
  const eta = Math.round(Number(etaSec) || 0);
  return `Weather reroute: vector ${acId} to safer sector ${alt} (hold or orbit) until the cell is clear — same policy as busy-runway holds. Forecast penetration ~${eta}s if unchanged — stay ≥${RULES.MIN_HORIZONTAL_SEP_NM} NM from hazard. METAR: ${weather.visibility_sm} SM / ceiling ${weather.ceiling_ft} ft.`;
}

function rerouteForSeparation(ids, evidence, crossedTracks) {
  const [a, b] = ids;
  const cross = crossedTracks ? " Crossing projected tracks." : "";
  return `Separation reroute: turn or climb/descend until ≥${RULES.MIN_HORIZONTAL_SEP_NM} NM and ≥${RULES.MIN_VERTICAL_SEP_FT} ft.${cross} Vector ${b} to restore spacing vs ${a}; if finals are saturated, extend vectors in a clear sector until spacing allows.`;
}

function rerouteForWake(leader, follower, ev) {
  return `Wake turbulence: increase trail to ≥6 NM or assign ${follower} +1000 ft above ${leader} wake path. Trail ${ev.trail_nm.toFixed(2)} NM, alt below leader ${ev.alt_below_ft.toFixed(0)} ft.`;
}

function suggestedHoldReroute(ac) {
  const hs = ac.holdSector || ac.sector || "E05";
  return `Busy runway / saturation: hold in sector ${hs} until runway ${ac.runway} is released, then continue approach. If weather or queues persist, extend vectors in a clear sector until METAR and spacing allow (same policy as storm reroutes).`;
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
  ctx.font = MAP_FONT.LAKE;
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
  });
}

/** Drawn after taxiways/runways so IDs stay visible; stroked text reads over roads. */
function drawSectorLabels() {
  ctx.save();
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  ctx.textBaseline = "middle";
  SECTORS.forEach((s) => {
    const cx = s.poly.reduce((a, p) => a + p[0], 0) / s.poly.length;
    const cy = s.poly.reduce((a, p) => a + p[1], 0) / s.poly.length;
    const sub = s.label.replace(/^.*? /, "");
    ctx.textAlign = "center";
    ctx.font = MAP_FONT.SECTOR_ID;
    ctx.lineWidth = 6;
    ctx.strokeStyle = "rgba(8, 10, 18, 0.92)";
    ctx.fillStyle = "rgba(245, 250, 255, 0.98)";
    ctx.strokeText(s.id, cx, cy);
    ctx.fillText(s.id, cx, cy);
    ctx.font = MAP_FONT.SECTOR_SUB;
    const subY = cy + 26;
    ctx.lineWidth = 5;
    ctx.strokeStyle = "rgba(8, 10, 18, 0.88)";
    ctx.fillStyle = "rgba(200, 218, 240, 0.96)";
    ctx.strokeText(sub, cx, subY);
    ctx.fillText(sub, cx, subY);
  });
  ctx.restore();
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
  ctx.font = "17px monospace";
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
  ctx.font = MAP_FONT.ARPT_TITLE;
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
    ctx.font = "17px monospace";
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
  ctx.font = `bold ${active ? 30 : 22}px monospace`;
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

  ctx.textAlign = "center";
  ctx.lineJoin = "round";
  ctx.font = MAP_FONT.STORM_TITLE;
  ctx.lineWidth = 7;
  ctx.strokeStyle = "rgba(6, 10, 18, 0.92)";
  ctx.fillStyle = "rgba(255, 255, 255, 0.97)";
  ctx.strokeText(z.label, cx, cy + 8);
  ctx.fillText(z.label, cx, cy + 8);
  ctx.font = MAP_FONT.STORM_SUB;
  ctx.lineWidth = 5;
  const subY = cy + 38;
  ctx.strokeStyle = "rgba(6, 10, 18, 0.88)";
  ctx.fillStyle = "rgba(220, 230, 245, 0.88)";
  ctx.strokeText("Mesoscale cell (~30% area)", cx, subY);
  ctx.fillText("Mesoscale cell (~30% area)", cx, subY);

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
  const id = `${prefix}${num}`;
  const rwy = pickRunwaySlot();
  const thr = runwayThreshold(rwy);
  const depart = Math.random() > 0.48;

  if (depart) {
    const startX = thr.x - 80;
    const startY = thr.y + (Math.random() * 10 - 5);
    const ac = {
      id,
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
    const startSector = sectorAtPoint(startX, startY);
    const holdSector = pickDeterministicRerouteSector(id, startSector || "C03");
    const busy = isRunwayBusy(rwy.id, time);

    const ac = {
      id,
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
          distance: intr.distance_nm.toFixed(2),
          rule_explanation: ruleExplanationFor("storm_avoidance_predicted"),
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
          rule_explanation: ruleExplanationFor("minimum_separation"),
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
          rule_explanation: ruleExplanationFor("minimum_separation_predicted"),
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
            rule_explanation: ruleExplanationFor("track_crossing_predicted"),
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
            rule_explanation: ruleExplanationFor("wake_turbulence"),
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
            rule_explanation: ruleExplanationFor("wake_turbulence"),
            evidence: ev,
            suggested_action: rerouteForWake(b.id, a.id, ev),
          });
        }
      }
    }
  }

  for (const ac of aircraft) {
    if (ac.phase === "HOLD" && ac.rerouted && ac.holdSector) {
      out.push({
        rule: "runway_hold_reroute",
        flights: [ac.id],
        severity: "yellow",
        distance: "—",
        rule_explanation: ruleExplanationFor("runway_hold_reroute"),
        suggested_action: suggestedHoldReroute(ac),
      });
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
  violations = sortViolationsStable([...base, ...crashViolations, ...dyn]);
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
  roundRect(ctx, ac.x - 62, ac.y + 30, 132, 38, 6);
  ctx.fill();
  ctx.fillStyle = isPath ? "#ffb088" : "#ffffff";
  ctx.font = MAP_FONT.FLIGHT_TAG;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const phaseTag =
    ac.phase === "HOLD" ? "HOLD" : ac.phase === "VECTOR" ? "VEC" : ac.phase.slice(0, 3);
  ctx.fillText(`${ac.id} · ${phaseTag}`, ac.x, ac.y + 49);
  ctx.textBaseline = "alphabetic";
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
        ctx.font = MAP_FONT.CONFLICT_NM;
        ctx.textAlign = "center";
        ctx.lineJoin = "round";
        const distRaw = String(v.distance ?? "—");
        const distLabel = distRaw.includes("NM") ? distRaw : `${distRaw} NM`;
        ctx.lineWidth = 6;
        ctx.strokeStyle = "rgba(10, 8, 12, 0.92)";
        ctx.strokeText(distLabel, mx, my - 14);
        ctx.fillStyle = "rgba(255, 80, 80, 0.98)";
        ctx.fillText(distLabel, mx, my - 14);
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
    ctx.font = MAP_FONT.PATH_MARKER;
    ctx.textAlign = "center";
    ctx.lineJoin = "round";
    ctx.lineWidth = 5;
    ctx.strokeStyle = "rgba(10, 8, 12, 0.9)";
    ctx.strokeText("PATH X", t.ix, t.iy - 28);
    ctx.fillStyle = "rgba(255, 100, 100, 0.96)";
    ctx.fillText("PATH X", t.ix, t.iy - 28);
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
  const alertCount =
    violations.length + mlAdvisoriesFromApi.length + mlPredictionsFromApi.length;
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

  const mlRows = mlAdvisoriesFromApi.map((a) => {
    const fl = Array.isArray(a.flights) ? a.flights : [];
    const sec = Array.isArray(a.sectors_involved) && a.sectors_involved.length;
    const sectorNote = sec ? ` Sectors: ${a.sectors_involved.join(", ")}.` : "";
    return {
      rule: "ml_advisory",
      severity: a.severity === "red" ? "red" : "yellow",
      flights: fl,
      distance: "—",
      rule_explanation: (a.summary || "Model advisory") + sectorNote,
      suggested_action: a.recommendation || "—",
    };
  });
  const predRows = mlPredictionsFromApi.map((p) => {
    const fl = Array.isArray(p.flights) ? p.flights : [];
    return {
      rule: "ml_prediction",
      severity: p.risk === "red" ? "red" : "yellow",
      flights: fl,
      distance: "—",
      rule_explanation: `[Model-predicted risk] ${p.rationale || "Monitor spacing and paths."}`,
      suggested_action: p.reroute_hint || "Review vectors vs METAR and wake.",
    };
  });
  const ruleRows = violations.map(enrichViolationForUi);
  const allAlerts = [...mlRows, ...predRows, ...ruleRows];

  if (allAlerts.length === 0) {
    ui.alertsList.innerHTML = '<div class="no-alerts">All clear</div>';
  } else {
    const policyNarrative = [
      REROUTE_POLICY_TEXT,
      multimodalContextFromApi ? ` ${multimodalContextFromApi}` : "",
      " JSON telemetry is fused with the live map view for multimodal reasoning (Qwen).",
    ].join("");
    const cardsHtml = allAlerts
      .map((v) => {
        const ruleLabel =
          v.rule === "ml_advisory"
            ? "QWEN"
            : v.rule === "ml_prediction"
              ? "QWEN-PRED"
            : v.rule === "wake_turbulence"
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
                              : v.rule === "runway_hold_reroute"
                                ? "HLD"
                                : String(v.rule).slice(0, 8).toUpperCase();
        const distRaw = String(v.distance ?? "—");
        const distUi =
          distRaw === "—" || distRaw === "-"
            ? "—"
            : distRaw.includes("NM")
              ? distRaw
              : `${distRaw} NM`;
        const flightStr = v.flights?.length ? v.flights.join(" / ") : "—";
        const extraClass =
          v.rule === "ml_advisory" || v.rule === "ml_prediction" ? " alert-item-ml" : "";
        return `
      <div class="alert-item ${v.severity}${extraClass}">
        <div class="alert-row">
          <span class="alert-rule">${ruleLabel}</span>
          <span class="alert-flights">${escapeHtml(flightStr)}</span>
          <span class="alert-dist">${escapeHtml(distUi)}</span>
        </div>
        <div class="alert-explain">${escapeHtml(v.rule_explanation)}</div>
        <div class="alert-advice"><span class="alert-advice-label">Reroute / advice:</span> ${escapeHtml(v.suggested_action || "Review routing and altitude.")}</div>
      </div>
    `;
      })
      .join("");
    ui.alertsList.innerHTML = `
      <div class="alerts-policy-bar">${escapeHtml(policyNarrative)}</div>
      <div class="alerts-cards">${cardsHtml}</div>`;
  }

  const crash = violations.find((x) => x.rule === "crash");
  const sorted = sortViolationsStable(violations);
  const now = Date.now();

  if (crash) {
    aiPanelLatch = { key: "", html: "", lockUntil: 0 };
    ui.aiContent.innerHTML = `
      <div class="ai-action ai-action--crash">
        <div class="ai-target">${escapeHtml(crash.flights.join(" / "))}</div>
        <div class="ai-command">${escapeHtml(ruleTitleForUi("crash"))}</div>
        <div class="ai-explain">${escapeHtml(ruleExplanationFor("crash"))}</div>
        <div class="ai-advice"><span class="ai-advice-label">Advice:</span> Emergency / incident response per ops — all conflicting traffic stop.</div>
      </div>
    `;
  } else {
    const top = sorted.find((v) => v.suggested_action && v.rule !== "crash");
    const pathHit = trajectoryAlerts[0];

    let key = "";
    let nextHtml = "";

    if (top) {
      key = `v:${top.rule}:${(top.flights || []).slice().sort().join("/")}`;
      const exp = top.rule_explanation || ruleExplanationFor(top.rule);
      nextHtml = `
      <div class="ai-action">
        <div class="ai-target">${escapeHtml(top.flights.join(" / "))}</div>
        <div class="ai-command">${escapeHtml(ruleTitleForUi(top.rule))}</div>
        <div class="ai-explain">${escapeHtml(exp)}</div>
        <div class="ai-advice"><span class="ai-advice-label">Advice:</span> ${escapeHtml(top.suggested_action)}</div>
      </div>`;
    } else if (pathHit) {
      key = `path:${(pathHit.flights || []).slice().sort().join("&")}`;
      nextHtml = `
      <div class="ai-action">
        <div class="ai-target">${escapeHtml(pathHit.flights.join(" & "))}</div>
        <div class="ai-command">Track geometry</div>
        <div class="ai-explain">${escapeHtml(ruleExplanationFor("path"))}</div>
        <div class="ai-advice"><span class="ai-advice-label">Advice:</span> Verify altitude crossing or assign offset vectors before paths merge.</div>
      </div>`;
    } else {
      const rest = sorted.filter((x) => x.rule !== "crash");
      const v = rest[0];
      if (v) {
        const ev = enrichViolationForUi(v);
        key = `fallback:${v.rule}:${(v.flights || []).slice().sort().join("/")}`;
        nextHtml = `
      <div class="ai-action">
        <div class="ai-target">${escapeHtml(v.flights.join(" / "))}</div>
        <div class="ai-command">${escapeHtml(ruleTitleForUi(v.rule))}</div>
        <div class="ai-explain">${escapeHtml(ev.rule_explanation)}</div>
        <div class="ai-advice"><span class="ai-advice-label">Advice:</span> ${escapeHtml(ev.suggested_action || "Review aircraft tracks.")}</div>
      </div>`;
      } else {
        key = "idle";
        nextHtml = '<div class="ai-idle">Monitoring CYYZ…</div>';
      }
    }

    if (key === "idle") {
      aiPanelLatch = { key: "", html: "", lockUntil: 0 };
      ui.aiContent.innerHTML = nextHtml;
    } else if (key === aiPanelLatch.key && now < aiPanelLatch.lockUntil && aiPanelLatch.html) {
      ui.aiContent.innerHTML = aiPanelLatch.html;
    } else {
      aiPanelLatch = { key, html: nextHtml, lockUntil: now + AI_PANEL_LATCH_MS };
      ui.aiContent.innerHTML = nextHtml;
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
  drawSectorLabels();
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
  aiPanelLatch = { key: "", html: "", lockUntil: 0 };
  mlAdvisoriesFromApi = [];
  mlPredictionsFromApi = [];
  multimodalContextFromApi = "";

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

// ─── PYTHON API (Layer 7 → FastAPI bridge) ──────────────────────────────────

function pushSimulationToBackend() {
  const raw = CONFIG.API_BASE_URL;
  if (!raw) return;
  const base = String(raw).replace(/\/$/, "");
  const payload = getSimulationExport();
  const params = new URLSearchParams();
  if (CONFIG.API_FULL_PIPELINE) params.set("full_pipeline", "true");
  if (CONFIG.API_ML_ADVISORY) params.set("ml_advisory", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  fetch(`${base}/api/simulation/tick${qs}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then((data) => {
      if (Array.isArray(data.ml_advisories)) {
        mlAdvisoriesFromApi = data.ml_advisories;
      } else {
        mlAdvisoriesFromApi = [];
      }
      if (Array.isArray(data.model_conflict_predictions)) {
        mlPredictionsFromApi = data.model_conflict_predictions;
      } else {
        mlPredictionsFromApi = [];
      }
      multimodalContextFromApi =
        typeof data.multimodal_context === "string" ? data.multimodal_context.trim() : "";
      updateUI();
    })
    .catch((err) => {
      mlAdvisoriesFromApi = [];
      mlPredictionsFromApi = [];
      multimodalContextFromApi = "";
      if (!window.__runwaiApiWarnedOnce) {
        window.__runwaiApiWarnedOnce = true;
        console.warn(
          "[RunwAI] API unreachable — run: uvicorn runwai.server:app --reload --host 127.0.0.1 --port 8000",
          err.message || err,
        );
      }
    });
}

// ─── INIT ───────────────────────────────────────────────────────────────────

resizeCanvas();
render();
setInterval(update, CONFIG.UPDATE_INTERVAL);
startLiveMode();
setInterval(pushSimulationToBackend, CONFIG.API_PUSH_INTERVAL_MS);
pushSimulationToBackend();

/** Training / evaluation JSON (includes lat/lon track_history, weather envelope) */
window.__runwaiTrainingExport = () => JSON.stringify(getSimulationExport(), null, 2);
