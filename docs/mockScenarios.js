/**
 * Airport simulation scenarios — coordinates match expanded CYYZ layout in main.js
 */

export const scenarios = {
  separation: {
    aircraft: [
      {
        id: "ACA456",
        type: "B77W",
        weight: "Heavy",
        size: 1.25,
        phase: "ARRIVE",
        x: 420,
        y: 700,
        targetX: 2940,
        targetY: 700,
        speed: 3.8,
        runway: "05/23",
      },
      {
        id: "WJA123",
        type: "A321",
        weight: "Medium",
        size: 1.0,
        phase: "ARRIVE",
        x: 1500,
        y: 718,
        targetX: 2940,
        targetY: 700,
        speed: 3.2,
        runway: "05/23",
      },
    ],
    violations: [
      {
        rule: "separation",
        flights: ["ACA456", "WJA123"],
        distance: "0.6",
        severity: "red",
        runway: "05/23",
      },
    ],
    weather: { storm_warning: true },
  },

  storm: {
    aircraft: [
      {
        id: "ACA789",
        type: "A321",
        weight: "Medium",
        size: 1.0,
        phase: "ARRIVE",
        x: 3480,
        y: 720,
        targetX: 2940,
        targetY: 700,
        speed: 2.6,
        runway: "05/23",
      },
      {
        id: "WJA555",
        type: "B738",
        weight: "Medium",
        size: 1.0,
        phase: "ARRIVE",
        x: 3480,
        y: 1040,
        targetX: 2940,
        targetY: 1020,
        speed: 2.8,
        runway: "06L/24R",
      },
      {
        id: "UAL100",
        type: "B738",
        weight: "Medium",
        size: 1.0,
        phase: "HOLD",
        x: 2000,
        y: 230,
        targetX: 2000,
        targetY: 230,
        speed: 0,
        runway: "06L/24R",
      },
    ],
    violations: [
      {
        rule: "storm",
        flights: ["ACA789"],
        distance: "-",
        severity: "red",
      },
    ],
    weather: { storm_warning: true },
  },

  wake: {
    aircraft: [
      {
        id: "ACA001",
        type: "B77W",
        weight: "Heavy",
        size: 1.25,
        phase: "DEPART",
        x: 1180,
        y: 698,
        targetX: 3600,
        targetY: 695,
        speed: 4.2,
        runway: "05/23",
      },
      {
        id: "CGG999",
        type: "E175",
        weight: "Light",
        size: 0.88,
        phase: "DEPART",
        x: 980,
        y: 705,
        targetX: 3600,
        targetY: 708,
        speed: 3.4,
        runway: "05/23",
      },
      {
        id: "WJA200",
        type: "A321",
        weight: "Medium",
        size: 1.0,
        phase: "TAXI",
        x: 420,
        y: 1100,
        targetX: 420,
        targetY: 1100,
        speed: 0,
        runway: "06L/24R",
      },
    ],
    violations: [
      {
        rule: "wake",
        flights: ["ACA001", "CGG999"],
        distance: "0.9",
        severity: "red",
      },
    ],
    weather: { storm_warning: true },
  },

  live: {
    aircraft: [],
    violations: [],
    weather: { storm_warning: true },
  },
};

export function getScenario(key) {
  return scenarios[key] || scenarios.live;
}

export const mockData = scenarios.separation;
