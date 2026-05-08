/**
 * RunwAI - Live Airport Surface Simulation
 * Full airport map with zoom/pan and live plane movement
 */

import { scenarios, getScenario } from "./mockScenarios.js";

// ─── CANVAS & CONFIG ────────────────────────────────────────────────────────

const canvas = document.getElementById("airportCanvas");
const ctx = canvas.getContext("2d");
const container = document.getElementById("mapContainer");

const CONFIG = {
  AIRPORT_WIDTH: 2400,
  AIRPORT_HEIGHT: 1400,
  MIN_ZOOM: 0.3,
  MAX_ZOOM: 2.0,
  ZOOM_STEP: 0.1,
  SPAWN_INTERVAL: 4000,
  UPDATE_INTERVAL: 50,
};

// ─── STATE ──────────────────────────────────────────────────────────────────

let zoom = 0.5;
let panX = 0;
let panY = 0;
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let time = 0;

let aircraft = [];
let violations = [];
let weather = { wind_dir: 270, wind_speed: 12, storm: false };
let currentMode = "live";
let spawnIntervalId = null;

// ─── UI ELEMENTS ────────────────────────────────────────────────────────────

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
  alertsPanel: document.getElementById("alertsPanel"),
};

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
  
  // If map is smaller than viewport, center it
  if (scaledW <= rect.width) {
    panX = (rect.width - scaledW) / 2;
  } else {
    // Otherwise, limit panning so map stays in view
    const minX = rect.width - scaledW - 50;
    const maxX = 50;
    panX = Math.max(minX, Math.min(maxX, panX));
  }
  
  if (scaledH <= rect.height) {
    panY = (rect.height - scaledH) / 2;
  } else {
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

// ─── AIRPORT RENDERING ──────────────────────────────────────────────────────

const RUNWAYS = [
  { id: "05/23", x: 300, y: 400, length: 1800, width: 60, angle: 0 },
  { id: "06L/24R", x: 300, y: 700, length: 1800, width: 60, angle: 0 },
  { id: "06R/24L", x: 300, y: 1000, length: 1600, width: 55, angle: 0 },
  { id: "15/33", x: 1600, y: 200, length: 1000, width: 50, angle: Math.PI / 2 },
];

const TAXIWAYS = [
  { points: [[200, 400], [200, 1000]], width: 28 },
  { points: [[200, 700], [300, 700]], width: 28 },
  { points: [[200, 550], [300, 550], [300, 400]], width: 24 },
  { points: [[200, 850], [300, 850], [300, 1000]], width: 24 },
  { points: [[500, 400], [500, 700]], width: 24 },
  { points: [[800, 400], [800, 1000]], width: 24 },
  { points: [[1100, 400], [1100, 700]], width: 24 },
  { points: [[1400, 400], [1400, 1000]], width: 24 },
  { points: [[1700, 700], [1700, 1000]], width: 24 },
  { points: [[2000, 400], [2000, 700], [2100, 700]], width: 24 },
  { points: [[1600, 200], [1600, 400]], width: 24 },
  { points: [[1600, 700], [1600, 1200], [1700, 1200]], width: 24 },
];

function drawGround() {
  // Grass base
  const grass = ctx.createLinearGradient(0, 0, CONFIG.AIRPORT_WIDTH, CONFIG.AIRPORT_HEIGHT);
  grass.addColorStop(0, "#2a3a24");
  grass.addColorStop(0.5, "#324530");
  grass.addColorStop(1, "#283a22");
  ctx.fillStyle = grass;
  ctx.fillRect(0, 0, CONFIG.AIRPORT_WIDTH, CONFIG.AIRPORT_HEIGHT);

  // Grass texture
  ctx.strokeStyle = "rgba(50, 70, 40, 0.3)";
  ctx.lineWidth = 1;
  for (let y = 0; y < CONFIG.AIRPORT_HEIGHT; y += 20) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(CONFIG.AIRPORT_WIDTH, y + Math.sin(y * 0.1) * 3);
    ctx.stroke();
  }

  // Apron/Terminal area
  ctx.fillStyle = "#4a4d52";
  ctx.fillRect(50, 500, 140, 400);
  
  // Terminal building
  ctx.fillStyle = "#3a3d42";
  ctx.fillRect(60, 550, 80, 300);
  ctx.strokeStyle = "rgba(150, 180, 220, 0.4)";
  ctx.lineWidth = 2;
  ctx.strokeRect(60, 550, 80, 300);
  
  // Terminal windows
  ctx.fillStyle = "rgba(180, 220, 255, 0.4)";
  for (let wy = 570; wy < 830; wy += 25) {
    for (let wx = 70; wx < 130; wx += 25) {
      ctx.fillRect(wx, wy, 15, 12);
    }
  }

  // Control tower
  ctx.fillStyle = "#3a3d42";
  ctx.fillRect(150, 680, 30, 60);
  ctx.fillStyle = "rgba(100, 200, 255, 0.6)";
  ctx.fillRect(152, 682, 26, 20);

  // Parking spots
  ctx.strokeStyle = "rgba(255, 220, 100, 0.3)";
  ctx.lineWidth = 2;
  for (let py = 520; py < 880; py += 50) {
    ctx.beginPath();
    ctx.moveTo(140, py);
    ctx.lineTo(185, py);
    ctx.stroke();
  }
}

function drawTaxiways() {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  TAXIWAYS.forEach(tw => {
    // Taxiway surface
    ctx.strokeStyle = "#4a4d52";
    ctx.lineWidth = tw.width;
    ctx.beginPath();
    ctx.moveTo(tw.points[0][0], tw.points[0][1]);
    tw.points.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
    ctx.stroke();

    // Yellow centerline
    ctx.strokeStyle = "rgba(255, 210, 0, 0.7)";
    ctx.lineWidth = 2;
    ctx.setLineDash([15, 10]);
    ctx.beginPath();
    ctx.moveTo(tw.points[0][0], tw.points[0][1]);
    tw.points.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function drawRunway(rwy) {
  const { x, y, length, width, angle, id } = rwy;
  const isBlocked = weather.storm && id === "05/23";
  const hasConflict = violations.some(v => v.runway === id);

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);

  // Surface
  const surf = ctx.createLinearGradient(0, -width/2, 0, width/2);
  if (isBlocked || hasConflict) {
    surf.addColorStop(0, "#5a2020");
    surf.addColorStop(0.5, "#3d1515");
    surf.addColorStop(1, "#4a1a1a");
  } else {
    surf.addColorStop(0, "#4a4d52");
    surf.addColorStop(0.5, "#3d4045");
    surf.addColorStop(1, "#454850");
  }
  ctx.fillStyle = surf;
  ctx.fillRect(0, -width/2, length, width);

  // Edge lines
  ctx.strokeStyle = hasConflict ? "rgba(255, 100, 80, 0.8)" : "rgba(255, 255, 255, 0.6)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, -width/2);
  ctx.lineTo(length, -width/2);
  ctx.moveTo(0, width/2);
  ctx.lineTo(length, width/2);
  ctx.stroke();

  // Threshold stripes
  ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
  for (let i = 0; i < 6; i++) {
    const sy = -width/2 + 8 + i * (width - 16) / 5;
    ctx.fillRect(15, sy, 30, 8);
    ctx.fillRect(length - 45, sy, 30, 8);
  }

  // Centerline
  ctx.strokeStyle = "rgba(255, 255, 255, 0.8)";
  ctx.lineWidth = 4;
  ctx.setLineDash([40, 30]);
  ctx.beginPath();
  ctx.moveTo(80, 0);
  ctx.lineTo(length - 80, 0);
  ctx.stroke();
  ctx.setLineDash([]);

  // Aiming points
  ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
  ctx.fillRect(250, -width/2 + 10, 60, 10);
  ctx.fillRect(250, width/2 - 20, 60, 10);
  ctx.fillRect(length - 310, -width/2 + 10, 60, 10);
  ctx.fillRect(length - 310, width/2 - 20, 60, 10);

  // Runway lights
  const pulse = 0.7 + 0.3 * Math.sin(time * 0.08);
  const lightColor = hasConflict ? `rgba(255, 60, 60, ${pulse})` : `rgba(255, 250, 200, ${pulse * 0.8})`;
  for (let lx = 50; lx < length - 30; lx += 60) {
    ctx.beginPath();
    ctx.arc(lx, -width/2 - 5, 3, 0, Math.PI * 2);
    ctx.arc(lx, width/2 + 5, 3, 0, Math.PI * 2);
    ctx.fillStyle = lightColor;
    ctx.fill();
  }

  // Runway number
  ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
  ctx.font = "bold 24px monospace";
  ctx.textAlign = "center";
  const nums = id.split("/");
  ctx.fillText(nums[0], 60, 8);
  ctx.save();
  ctx.translate(length - 60, 0);
  ctx.rotate(Math.PI);
  ctx.fillText(nums[1], 0, 8);
  ctx.restore();

  ctx.restore();
}

function drawStormOverlay() {
  if (!weather.storm) return;

  const alpha = 0.12 + 0.05 * Math.sin(time * 0.05);
  ctx.fillStyle = `rgba(80, 60, 100, ${alpha})`;
  ctx.fillRect(0, 0, CONFIG.AIRPORT_WIDTH, 600);

  // Rain
  ctx.strokeStyle = "rgba(150, 170, 200, 0.25)";
  ctx.lineWidth = 1;
  for (let i = 0; i < 100; i++) {
    const rx = (time * 4 + i * 47) % CONFIG.AIRPORT_WIDTH;
    const ry = (time * 12 + i * 31) % 600;
    ctx.beginPath();
    ctx.moveTo(rx, ry);
    ctx.lineTo(rx - 4, ry + 20);
    ctx.stroke();
  }

  // Storm label
  ctx.fillStyle = "rgba(255, 80, 80, 0.9)";
  ctx.font = "bold 28px monospace";
  ctx.textAlign = "center";
  ctx.fillText("⛈ STORM ZONE", CONFIG.AIRPORT_WIDTH / 2, 300);
}

// ─── AIRCRAFT ───────────────────────────────────────────────────────────────

const AIRCRAFT_TYPES = [
  { code: "B77W", weight: "Heavy", size: 1.3 },
  { code: "A320", weight: "Medium", size: 1.0 },
  { code: "B738", weight: "Medium", size: 1.0 },
  { code: "E190", weight: "Medium", size: 0.85 },
  { code: "C172", weight: "Light", size: 0.6 },
];

const CALLSIGNS = ["ACA", "WJA", "UAL", "DAL", "AAL", "SWA", "JBU"];

function spawnAircraft() {
  if (aircraft.length >= 8) return;

  const type = AIRCRAFT_TYPES[Math.floor(Math.random() * AIRCRAFT_TYPES.length)];
  const prefix = CALLSIGNS[Math.floor(Math.random() * CALLSIGNS.length)];
  const num = Math.floor(Math.random() * 900) + 100;

  const routes = [
    { start: { x: 50, y: 700 }, end: { x: 2100, y: 400 }, runway: "05/23" },
    { start: { x: 2100, y: 400 }, end: { x: 50, y: 700 }, runway: "05/23" },
    { start: { x: 50, y: 850 }, end: { x: 2100, y: 700 }, runway: "06L/24R" },
    { start: { x: 2100, y: 1000 }, end: { x: 50, y: 850 }, runway: "06R/24L" },
    { start: { x: 1600, y: 50 }, end: { x: 1600, y: 1200 }, runway: "15/33" },
  ];

  const route = routes[Math.floor(Math.random() * routes.length)];
  
  aircraft.push({
    id: `${prefix}${num}`,
    type: type.code,
    weight: type.weight,
    size: type.size,
    x: route.start.x,
    y: route.start.y,
    targetX: route.end.x,
    targetY: route.end.y,
    heading: Math.atan2(route.end.y - route.start.y, route.end.x - route.start.x),
    speed: 1.5 + Math.random() * 2,
    runway: route.runway,
    phase: Math.random() > 0.5 ? "DEPART" : "ARRIVE",
    trail: [],
  });
}

function updateAircraft() {
  aircraft = aircraft.filter(ac => {
    const dx = ac.targetX - ac.x;
    const dy = ac.targetY - ac.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist < 30) return false;

    ac.heading = Math.atan2(dy, dx);
    ac.x += Math.cos(ac.heading) * ac.speed;
    ac.y += Math.sin(ac.heading) * ac.speed;

    ac.trail.push({ x: ac.x, y: ac.y, age: 0 });
    ac.trail.forEach(t => t.age++);
    ac.trail = ac.trail.filter(t => t.age < 40);

    return true;
  });
}

function drawAircraft(ac) {
  const isConflict = violations.some(v => v.flights?.includes(ac.id));
  const isWarning = violations.some(v => v.flights?.includes(ac.id) && v.severity === "yellow");
  
  // Trail
  ac.trail.forEach(t => {
    const alpha = Math.max(0, 0.4 * (1 - t.age / 40));
    const r = Math.max(0, 4 * (1 - t.age / 40));
    if (r > 0) {
      ctx.beginPath();
      ctx.arc(t.x, t.y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(150, 200, 255, ${alpha})`;
      ctx.fill();
    }
  });

  ctx.save();
  ctx.translate(ac.x, ac.y);
  ctx.rotate(ac.heading);

  const s = ac.size;
  const color = isConflict ? "#ff5555" : isWarning ? "#ffaa33" : "#d8e4f0";
  const glow = isConflict ? "rgba(255, 80, 80, 0.6)" : isWarning ? "rgba(255, 170, 50, 0.5)" : "rgba(100, 180, 255, 0.3)";

  // Glow
  if (isConflict || isWarning) {
    ctx.beginPath();
    ctx.ellipse(0, 0, 50 * s, 25 * s, 0, 0, Math.PI * 2);
    const pulse = 0.3 + 0.3 * Math.sin(time * 0.15);
    ctx.fillStyle = glow.replace("0.6", pulse.toFixed(2)).replace("0.5", pulse.toFixed(2));
    ctx.fill();
  }

  // Shadow
  ctx.beginPath();
  ctx.ellipse(6, 8, 35 * s, 12 * s, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.25)";
  ctx.fill();

  // Wings
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(15 * s, -5 * s);
  ctx.lineTo(-8 * s, -42 * s);
  ctx.lineTo(-18 * s, -42 * s);
  ctx.lineTo(-5 * s, -5 * s);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(15 * s, 5 * s);
  ctx.lineTo(-8 * s, 42 * s);
  ctx.lineTo(-18 * s, 42 * s);
  ctx.lineTo(-5 * s, 5 * s);
  ctx.closePath();
  ctx.fill();

  // Tail
  ctx.fillStyle = isConflict ? "#cc4444" : isWarning ? "#cc8833" : "#b8c8d8";
  ctx.beginPath();
  ctx.moveTo(-25 * s, -4 * s);
  ctx.lineTo(-35 * s, -20 * s);
  ctx.lineTo(-40 * s, -20 * s);
  ctx.lineTo(-30 * s, -4 * s);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(-25 * s, 4 * s);
  ctx.lineTo(-35 * s, 20 * s);
  ctx.lineTo(-40 * s, 20 * s);
  ctx.lineTo(-30 * s, 4 * s);
  ctx.closePath();
  ctx.fill();

  // Fuselage
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.ellipse(0, 0, 42 * s, 8 * s, 0, 0, Math.PI * 2);
  ctx.fill();

  // Cockpit
  ctx.fillStyle = "rgba(120, 200, 255, 0.7)";
  ctx.beginPath();
  ctx.ellipse(32 * s, 0, 8 * s, 5 * s, 0, 0, Math.PI * 2);
  ctx.fill();

  // Nav lights
  const navPulse = 0.6 + 0.4 * Math.abs(Math.sin(time * 0.12));
  ctx.beginPath();
  ctx.arc(-12 * s, -42 * s, 4 * s, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(255, 50, 50, ${navPulse})`;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(-12 * s, 42 * s, 4 * s, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(50, 220, 100, ${navPulse})`;
  ctx.fill();

  ctx.restore();

  // Label
  ctx.fillStyle = "rgba(0, 0, 0, 0.75)";
  roundRect(ctx, ac.x - 32, ac.y + 30, 64, 22, 4);
  ctx.fill();
  ctx.fillStyle = isConflict ? "#ff8888" : "#ffffff";
  ctx.font = "bold 12px monospace";
  ctx.textAlign = "center";
  ctx.fillText(ac.id, ac.x, ac.y + 45);
  
  // Weight badge
  const badge = ac.weight === "Heavy" ? "H" : ac.weight === "Light" ? "L" : "M";
  ctx.fillStyle = ac.weight === "Heavy" ? "#ff6666" : ac.weight === "Light" ? "#66ff88" : "#ffcc66";
  ctx.font = "bold 10px monospace";
  ctx.fillText(badge, ac.x + 25, ac.y + 45);
}

function drawConflictLines() {
  violations.forEach(v => {
    if (v.flights?.length >= 2) {
      const ac1 = aircraft.find(a => a.id === v.flights[0]);
      const ac2 = aircraft.find(a => a.id === v.flights[1]);
      if (ac1 && ac2) {
        const pulse = 0.5 + 0.5 * Math.sin(time * 0.2);
        ctx.strokeStyle = v.severity === "red" 
          ? `rgba(255, 50, 50, ${pulse})`
          : `rgba(255, 180, 50, ${pulse})`;
        ctx.lineWidth = 4;
        ctx.setLineDash([12, 8]);
        ctx.beginPath();
        ctx.moveTo(ac1.x, ac1.y);
        ctx.lineTo(ac2.x, ac2.y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Distance label
        const mx = (ac1.x + ac2.x) / 2;
        const my = (ac1.y + ac2.y) / 2;
        ctx.fillStyle = "rgba(255, 60, 60, 0.9)";
        ctx.font = "bold 14px monospace";
        ctx.textAlign = "center";
        ctx.fillText(`${v.distance || "!"} NM`, mx, my - 10);
      }
    }
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

// ─── CONFLICT DETECTION (Simplified) ────────────────────────────────────────

function checkConflicts() {
  violations = [];
  
  for (let i = 0; i < aircraft.length; i++) {
    for (let j = i + 1; j < aircraft.length; j++) {
      const a = aircraft[i];
      const b = aircraft[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < 120) {
        violations.push({
          rule: "separation",
          flights: [a.id, b.id],
          distance: (dist / 50).toFixed(1),
          severity: dist < 80 ? "red" : "yellow",
          runway: a.runway,
        });
      }
    }

    // Wake turbulence check
    if (aircraft[i].weight === "Heavy") {
      aircraft.forEach(other => {
        if (other.id !== aircraft[i].id && other.weight === "Light") {
          const dx = aircraft[i].x - other.x;
          const dy = aircraft[i].y - other.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const behind = Math.cos(aircraft[i].heading) * dx + Math.sin(aircraft[i].heading) * dy;
          
          if (behind > 0 && behind < 200 && Math.abs(dy) < 50) {
            violations.push({
              rule: "wake",
              flights: [aircraft[i].id, other.id],
              distance: (dist / 50).toFixed(1),
              severity: "red",
            });
          }
        }
      });
    }
  }
}

// ─── UI UPDATES ─────────────────────────────────────────────────────────────

function updateUI() {
  ui.aircraftCount.textContent = aircraft.length;
  ui.violationCount.textContent = violations.length;
  ui.violationCount.parentElement.classList.toggle("alert", violations.length > 0);
  ui.windValue.textContent = `${weather.wind_speed}kt`;
  
  ui.headerStatus.classList.toggle("alert", violations.length > 0);
  ui.stormBanner.classList.toggle("visible", weather.storm);
  ui.alertsPanel.classList.toggle("has-alerts", violations.length > 0);

  // Alerts
  if (violations.length === 0) {
    ui.alertsList.innerHTML = '<div class="no-alerts">All clear</div>';
  } else {
    ui.alertsList.innerHTML = violations.map(v => `
      <div class="alert-item ${v.severity}">
        <span class="alert-rule">${v.rule === "wake" ? "WAKE" : "SEP"}</span>
        <span class="alert-flights">${v.flights.join(" / ")}</span>
        <span class="alert-dist">${v.distance} NM</span>
      </div>
    `).join("");
  }

  // AI Action
  if (violations.length > 0) {
    const v = violations[0];
    ui.aiContent.innerHTML = `
      <div class="ai-action">
        <div class="ai-target">${v.flights[1]}</div>
        <div class="ai-command">${v.rule === "wake" ? "HOLD 3 MIN" : "STOP"}</div>
        <div class="ai-reason">${v.rule === "wake" ? "Wake turbulence" : "Separation conflict"}</div>
      </div>
    `;
  } else {
    ui.aiContent.innerHTML = '<div class="ai-idle">Monitoring...</div>';
  }

  // Flights list
  ui.flightsList.innerHTML = aircraft.map(ac => {
    const isConflict = violations.some(v => v.flights?.includes(ac.id));
    return `
      <div class="flight-row ${isConflict ? 'conflict' : ''}">
        <span class="flight-id">${ac.id}</span>
        <span class="flight-type">${ac.type}</span>
        <span class="flight-phase">${ac.phase}</span>
      </div>
    `;
  }).join("") || '<div class="no-flights">No aircraft</div>';
}

// ─── RENDER LOOP ────────────────────────────────────────────────────────────

function render() {
  time++;
  ctx.clearRect(0, 0, CONFIG.AIRPORT_WIDTH, CONFIG.AIRPORT_HEIGHT);

  drawGround();
  drawTaxiways();
  RUNWAYS.forEach(drawRunway);
  drawStormOverlay();
  drawConflictLines();
  aircraft.forEach(drawAircraft);

  requestAnimationFrame(render);
}

function update() {
  updateAircraft();
  if (currentMode === "live") {
    checkConflicts();
  }
  updateUI();
}

// ─── SCENARIOS ──────────────────────────────────────────────────────────────

function startLiveMode() {
  currentMode = "live";
  weather.storm = false;
  
  // Start spawning aircraft
  if (spawnIntervalId) clearInterval(spawnIntervalId);
  spawnIntervalId = setInterval(spawnAircraft, CONFIG.SPAWN_INTERVAL);
  
  // Spawn initial aircraft
  for (let i = 0; i < 4; i++) {
    setTimeout(spawnAircraft, i * 300);
  }
}

function runScenario(key) {
  // Stop live spawning
  if (spawnIntervalId) {
    clearInterval(spawnIntervalId);
    spawnIntervalId = null;
  }
  
  // Clear existing aircraft
  aircraft = [];
  violations = [];
  
  if (key === "live") {
    startLiveMode();
    return;
  }

  currentMode = "scenario";
  const scenario = getScenario(key);
  
  // Set up scenario aircraft with proper movement
  aircraft = (scenario.aircraft || []).map(ac => ({
    ...ac,
    trail: [],
    heading: Math.atan2(ac.targetY - ac.y, ac.targetX - ac.x),
  }));
  
  violations = scenario.violations || [];
  weather.storm = scenario.weather?.storm_warning || false;
  
  updateUI();
}

// ─── EVENT HANDLERS ─────────────────────────────────────────────────────────

document.getElementById("zoomIn").onclick = () => {
  const rect = container.getBoundingClientRect();
  const centerX = rect.width / 2;
  const centerY = rect.height / 2;
  
  const oldZoom = zoom;
  zoom = Math.min(CONFIG.MAX_ZOOM, zoom + CONFIG.ZOOM_STEP);
  
  // Zoom toward center
  panX = centerX - (centerX - panX) * (zoom / oldZoom);
  panY = centerY - (centerY - panY) * (zoom / oldZoom);
  
  updateCanvasTransform();
};

document.getElementById("zoomOut").onclick = () => {
  const rect = container.getBoundingClientRect();
  const centerX = rect.width / 2;
  const centerY = rect.height / 2;
  
  const oldZoom = zoom;
  zoom = Math.max(CONFIG.MIN_ZOOM, zoom - CONFIG.ZOOM_STEP);
  
  // Zoom toward center
  panX = centerX - (centerX - panX) * (zoom / oldZoom);
  panY = centerY - (centerY - panY) * (zoom / oldZoom);
  
  updateCanvasTransform();
};

document.getElementById("zoomReset").onclick = () => {
  zoom = 0.5;
  centerView();
};

container.addEventListener("mousedown", e => {
  isDragging = true;
  dragStart = { x: e.clientX - panX, y: e.clientY - panY };
  container.style.cursor = "grabbing";
});

document.addEventListener("mousemove", e => {
  if (!isDragging) return;
  panX = e.clientX - dragStart.x;
  panY = e.clientY - dragStart.y;
  updateCanvasTransform();
});

document.addEventListener("mouseup", () => {
  isDragging = false;
  container.style.cursor = "grab";
});

container.addEventListener("wheel", e => {
  e.preventDefault();
  const rect = container.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;
  
  const oldZoom = zoom;
  const delta = e.deltaY > 0 ? -CONFIG.ZOOM_STEP : CONFIG.ZOOM_STEP;
  zoom = Math.max(CONFIG.MIN_ZOOM, Math.min(CONFIG.MAX_ZOOM, zoom + delta));
  
  // Zoom toward mouse position
  panX = mouseX - (mouseX - panX) * (zoom / oldZoom);
  panY = mouseY - (mouseY - panY) * (zoom / oldZoom);
  
  updateCanvasTransform();
});

document.getElementById("runBtn").onclick = () => {
  const key = document.getElementById("scenarioSelect").value;
  runScenario(key);
};

document.getElementById("scenarioSelect").onchange = (e) => {
  runScenario(e.target.value);
};

// ─── INIT ───────────────────────────────────────────────────────────────────

resizeCanvas();
render();
setInterval(update, CONFIG.UPDATE_INTERVAL);

// Start in live mode
startLiveMode();
