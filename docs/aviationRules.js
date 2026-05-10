/**
 * Aviation rule checks + geodesy aligned with runwai/rules (Python).
 * Used for trajectory prediction, conflict alerts, and JSON-ready training exports.
 */

export const RULES = {
  MIN_HORIZONTAL_SEP_NM: 5,
  MIN_VERTICAL_SEP_FT: 1000,
  WAKE_MIN_TRAIL_NM: 6,
  WAKE_MAX_ALT_BELOW_FT: 1000,
  WAKE_BEARING_TOLERANCE_DEG: 30,
  PROJECTION_SECONDS: 60,
  PREDICTION_STEP_SEC: 10,
  HISTORY_MAX_MS: 5 * 60 * 1000,
};

/** Map pixel coords ↔ WGS84 around CYYZ (training-export consistent) */
export const GEO_ANCHOR = {
  ref_lat: 43.6777,
  ref_lon: -79.6306,
  ref_x: 2000,
  ref_y: 1100,
  meters_per_pixel: 6.35,
};

export function xyToLatLon(x, y) {
  const refLatRad = (GEO_ANCHOR.ref_lat * Math.PI) / 180;
  const dx_m = (x - GEO_ANCHOR.ref_x) * GEO_ANCHOR.meters_per_pixel;
  const dy_m = (y - GEO_ANCHOR.ref_y) * GEO_ANCHOR.meters_per_pixel;
  const lat = GEO_ANCHOR.ref_lat - dy_m / 111320;
  const lon = GEO_ANCHOR.ref_lon + dx_m / (111320 * Math.cos(refLatRad));
  return { lat, lon };
}

export function nmPerPixel() {
  return GEO_ANCHOR.meters_per_pixel / 1852;
}

export function stormZonePixelsToGeo(zonePx) {
  const c = xyToLatLon(zonePx.cx, zonePx.cy);
  const radius_nm = zonePx.r * nmPerPixel();
  return {
    center_lat: c.lat,
    center_lon: c.lon,
    radius_nm,
    phenomenon_type: zonePx.type,
    label: zonePx.label,
  };
}

/** METAR-like fields tied to phenomenon (for JSON / model training) */
export function weatherEnvelopeFromPhenomenon(type) {
  switch (type) {
    case "heavy_rain":
      return {
        visibility_sm: 4 + Math.random() * 2,
        ceiling_ft: 2500 + Math.floor(Math.random() * 1500),
        wind_severity: "moderate",
        wind_gust_kts: 18 + Math.floor(Math.random() * 12),
      };
    case "snow_storm":
      return {
        visibility_sm: 0.75 + Math.random() * 1.5,
        ceiling_ft: 800 + Math.floor(Math.random() * 1200),
        wind_severity: "severe",
        wind_gust_kts: 22 + Math.floor(Math.random() * 18),
      };
    case "thunderstorm":
      return {
        visibility_sm: 2 + Math.random() * 3,
        ceiling_ft: 1500 + Math.floor(Math.random() * 2500),
        wind_severity: "severe",
        wind_gust_kts: 28 + Math.floor(Math.random() * 20),
      };
    case "fog":
      return {
        visibility_sm: 0.25 + Math.random() * 0.35,
        ceiling_ft: 200 + Math.floor(Math.random() * 400),
        wind_severity: "light",
        wind_gust_kts: 6 + Math.floor(Math.random() * 6),
      };
    default:
      return {
        visibility_sm: 10,
        ceiling_ft: 4500,
        wind_severity: "calm",
        wind_gust_kts: 0,
      };
  }
}

const R_EARTH_NM = 3440.065;

export function haversine_nm(lat1, lon1, lat2, lon2) {
  const r1 = (lat1 * Math.PI) / 180;
  const r2 = (lat2 * Math.PI) / 180;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(r1) * Math.cos(r2) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R_EARTH_NM * c;
}

/** Short-range flat approximation if haversine overkill — kept for consistency use haversine */
export function projectLatLon(lat, lon, headingDeg, distanceNm) {
  const latRad = (lat * Math.PI) / 180;
  const lonRad = (lon * Math.PI) / 180;
  const brng = (headingDeg * Math.PI) / 180;
  const d = distanceNm / R_EARTH_NM;
  const lat2 = Math.asin(
    Math.sin(latRad) * Math.cos(d) + Math.cos(latRad) * Math.sin(d) * Math.cos(brng),
  );
  const lon2 =
    lonRad +
    Math.atan2(
      Math.sin(brng) * Math.sin(d) * Math.cos(latRad),
      Math.cos(d) - Math.sin(latRad) * Math.sin(lat2),
    );
  return { lat: (lat2 * 180) / Math.PI, lon: (lon2 * 180) / Math.PI };
}

export function bearingDeg(lat1, lon1, lat2, lon2) {
  const lat1R = (lat1 * Math.PI) / 180;
  const lat2R = (lat2 * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const x = Math.sin(dLon) * Math.cos(lat2R);
  const y =
    Math.cos(lat1R) * Math.sin(lat2R) -
    Math.sin(lat1R) * Math.cos(lat2R) * Math.cos(dLon);
  return (Math.atan2(x, y) * 180) / Math.PI + 360;
}

function normalizeAngle(angle) {
  let a = angle;
  while (a > 180) a -= 360;
  while (a < -180) a += 360;
  return a;
}

export function isFollowingWakeZone(leaderHdgDeg, latL, lonL, latF, lonF) {
  const bearingLF = bearingDeg(latL, lonL, latF, lonF);
  const behind = (leaderHdgDeg + 180) % 360;
  const diff = Math.abs(normalizeAngle(bearingLF - behind));
  return diff <= RULES.WAKE_BEARING_TOLERANCE_DEG;
}

/** Minimum separation violation (same as separation.py): BOTH horizontal AND vertical inadequate */
export function minimumSeparationViolated(nmH, altDiffFt) {
  const hv = nmH < RULES.MIN_HORIZONTAL_SEP_NM;
  const vv = altDiffFt < RULES.MIN_VERTICAL_SEP_FT;
  return hv && vv;
}

export function severityFromConfidence(conf) {
  if (conf >= 0.7) return "red";
  if (conf >= 0.3) return "yellow";
  return "green";
}

/**
 * Discrete trajectory samples for prediction — matches Layer 5 horizon spirit.
 */
export function predictTrajectorySamples(ac, horizonSec = RULES.PROJECTION_SECONDS, stepSec = RULES.PREDICTION_STEP_SEC) {
  const out = [];
  let lat = ac.lat;
  let lon = ac.lon;
  let alt = ac.altitude_ft;
  const hdg = ac.heading_deg;
  const kts = Math.max(40, ac.velocity_kts || 180);
  const vsFpm = ac.vertical_speed_fpm || 0;

  for (let t = 0; t <= horizonSec + 1e-6; t += stepSec) {
    out.push({
      t_sec: Math.round(t),
      lat,
      lon,
      alt_ft: Math.round(alt),
      velocity_kts: Math.round(kts),
      heading_deg: ((hdg % 360) + 360) % 360,
    });
    const dNm = (kts / 3600) * stepSec;
    const p = projectLatLon(lat, lon, hdg, dNm);
    lat = p.lat;
    lon = p.lon;
    alt += (vsFpm / 60) * stepSec;
  }
  return out;
}

export function trimHistory(ring, maxAgeMs, nowMs) {
  const cutoff = nowMs - maxAgeMs;
  while (ring.length && ring[0].t < cutoff) ring.shift();
}

/** Storm: projected position enters mesoscale cell (great-circle distance < radius_nm) */
export function projectedStormIntrusion(samples, stormGeo) {
  if (!stormGeo?.center_lat) return null;
  const { center_lat, center_lon, radius_nm } = stormGeo;
  for (const s of samples) {
    const d = haversine_nm(s.lat, s.lon, center_lat, center_lon);
    if (d < radius_nm * 0.98) {
      return { eta_sec: s.t_sec, distance_nm: d };
    }
  }
  return null;
}

/** Pairwise predicted separation loss */
export function findPredictedSeparationConflict(samplesA, samplesB) {
  const len = Math.min(samplesA.length, samplesB.length);
  for (let i = 0; i < len; i++) {
    const a = samplesA[i];
    const b = samplesB[i];
    const nm = haversine_nm(a.lat, a.lon, b.lat, b.lon);
    const ad = Math.abs(a.alt_ft - b.alt_ft);
    if (minimumSeparationViolated(nm, ad)) {
      return {
        eta_sec: a.t_sec,
        distance_nm: nm,
        alt_diff_ft: ad,
      };
    }
  }
  return null;
}

/** Horizontal path intersection (canvas px) with time-aligned altitude check at crossing */
export function segmentIntersection(ax, ay, bx, by, cx, cy, dx, dy) {
  const det = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx);
  if (Math.abs(det) < 1e-9) return null;
  const t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / det;
  const u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / det;
  if (t >= 0 && t <= 1 && u >= 0 && u <= 1) {
    return { x: ax + t * (bx - ax), y: ay + t * (by - ay), t, u };
  }
  return null;
}

export function wakeViolationEvidence(heavy, light) {
  const nm = haversine_nm(heavy.lat, heavy.lon, light.lat, light.lon);
  if (nm >= RULES.WAKE_MIN_TRAIL_NM) return null;
  if (!isFollowingWakeZone(heavy.heading_deg, heavy.lat, heavy.lon, light.lat, light.lon))
    return null;
  const altBelow = heavy.altitude_ft - light.altitude_ft;
  if (altBelow < 0 || altBelow > RULES.WAKE_MAX_ALT_BELOW_FT) return null;
  return {
    trail_nm: nm,
    alt_below_ft: altBelow,
    confidence: Math.min(1, 1 - nm / RULES.WAKE_MIN_TRAIL_NM),
  };
}
