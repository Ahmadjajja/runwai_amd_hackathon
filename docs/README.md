# RunwAI Frontend - ATC Conflict Detection Dashboard

Real-time airspace visualization and AI-powered conflict detection dashboard for air traffic control.

## Features

### Map View (Leaflet)
- **Aircraft Markers**: Color-coded by status (blue=normal, yellow=warning, red=conflict)
- **Projected Paths**: 60-second forward trajectory projection (dashed lines)
- **Storm Overlays**: Weather hazard zones with severity coloring
- **Sector Overlays**: A12, B07, C03 airspace sectors
- **Conflict Lines**: Visual connection between conflicting aircraft

### Weather Panel
- Wind speed & direction
- Visibility (SM)
- Ceiling (ft)
- Storm warning status
- Raw METAR display

### Violations Panel
Real-time display of rule violations:
- **Minimum Separation**: Aircraft too close (< 5 NM horizontal OR < 1000 ft vertical)
- **Storm Avoidance**: Aircraft projected into hazardous weather
- **Wake Turbulence**: Light/medium aircraft trailing heavy at insufficient distance

### AI Decision Panel
- Model reasoning explanation
- Recommended action (heading/altitude/speed change)
- Validation status
- Sector assignment
- Processing latency

### Flight List
- All airborne aircraft with weight class badges
- Real-time altitude, speed, heading
- Conflict highlighting

## Scenarios

1. **Separation Violation**: Two aircraft converging with insufficient separation
2. **Storm Avoidance**: Aircraft on collision course with severe weather
3. **Wake Turbulence**: Light aircraft trailing heavy without proper spacing
4. **Clean (No Violation)**: Normal operations

## Usage

1. Open `index.html` in a browser
2. Select a scenario from the dropdown
3. Click "Run Scenario" to visualize

## Backend Integration

The frontend is designed to connect to the RunwAI backend:

```javascript
// In main.js, update CONFIG.API_BASE
const CONFIG = {
  API_BASE: "http://localhost:8000",
  // ...
};
```

Expected backend endpoints:
- `GET /tick` - Current airspace state
- `POST /analyze` - Run rules engine + model

## Files

- `index.html` - Main HTML structure
- `main.js` - Map initialization, data rendering, scenario runner
- `mockScenarios.js` - Test scenarios with flights, weather, violations
- `styles.css` - Dark theme styling

## Dependencies

- [Leaflet 1.9.4](https://leafletjs.com/) - Map rendering
- [CARTO Dark Tiles](https://carto.com/) - Dark map tiles
