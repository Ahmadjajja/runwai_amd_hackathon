/**
 * Airport Simulation Scenarios
 * Aircraft move in real-time to create conflict situations
 */

export const scenarios = {
  // Runway Incursion - aircraft crossing runway during takeoff
  separation: {
    aircraft: [
      {
        id: "ACA456",
        type: "B77W",
        weight: "Heavy",
        size: 1.3,
        phase: "DEPART",
        x: 300,
        y: 400,
        targetX: 2200,
        targetY: 400,
        speed: 4.0,  // Fast takeoff roll
      },
      {
        id: "WJA123",
        type: "A320",
        weight: "Medium",
        size: 1.0,
        phase: "CROSS",
        x: 800,
        y: 600,
        targetX: 800,
        targetY: 200,
        speed: 1.8,  // Crossing the runway
      },
    ],
    violations: [
      {
        rule: "separation",
        flights: ["ACA456", "WJA123"],
        distance: "0.5",
        severity: "red",
        runway: "05/23",
      },
    ],
    weather: { storm_warning: false },
  },

  // Storm on approach path
  storm: {
    aircraft: [
      {
        id: "ACA789",
        type: "A320",
        weight: "Medium",
        size: 1.0,
        phase: "ARRIVE",
        x: 2200,
        y: 250,
        targetX: 300,
        targetY: 400,
        speed: 3.5,
      },
      {
        id: "WJA555",
        type: "B738",
        weight: "Medium",
        size: 1.0,
        phase: "ARRIVE",
        x: 2200,
        y: 500,
        targetX: 300,
        targetY: 700,
        speed: 3.0,
      },
      {
        id: "UAL100",
        type: "B738",
        weight: "Medium",
        size: 1.0,
        phase: "HOLD",
        x: 200,
        y: 850,
        targetX: 200,
        targetY: 850,
        speed: 0,  // Holding
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

  // Wake turbulence - light following heavy
  wake: {
    aircraft: [
      {
        id: "ACA001",
        type: "B77W",
        weight: "Heavy",
        size: 1.3,
        phase: "DEPART",
        x: 500,
        y: 400,
        targetX: 2200,
        targetY: 380,
        speed: 4.5,
      },
      {
        id: "CGG999",
        type: "C172",
        weight: "Light",
        size: 0.6,
        phase: "DEPART",
        x: 320,
        y: 400,
        targetX: 2200,
        targetY: 400,
        speed: 3.0,  // Following too close
      },
      {
        id: "WJA200",
        type: "A320",
        weight: "Medium",
        size: 1.0,
        phase: "TAXI",
        x: 200,
        y: 550,
        targetX: 200,
        targetY: 400,
        speed: 1.0,
      },
    ],
    violations: [
      {
        rule: "wake",
        flights: ["ACA001", "CGG999"],
        distance: "0.8",
        severity: "red",
      },
    ],
    weather: { storm_warning: false },
  },

  live: {
    aircraft: [],
    violations: [],
    weather: { storm_warning: false },
  },
};

export function getScenario(key) {
  return scenarios[key] || scenarios.live;
}

export const mockData = scenarios.separation;
