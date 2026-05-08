"""
RunwAI — Layer 1 Demo
Shows all 4 live data sources working together.
Run: python3 demo.py
"""
import json
import os

W  = 70
SEP = "─" * W

def header(title):
    print(f"\n╔{'═'*W}╗")
    print(f"║  {title:<{W-2}}║")
    print(f"╚{'═'*W}╝")

def section(title):
    print(f"\n  {title}")
    print(f"  {SEP}")

# ── 1. Live Flights (OpenSky) ──────────────────────────────────────────────────
header("RunwAI — Layer 1 Demo  |  All 4 data sources")

section("① LIVE FLIGHTS  —  OpenSky Network (CYYZ bounding box)")
from layer1.opensky_client import fetch_flights
flights = fetch_flights()
print(f"  Fetched {len(flights)} aircraft around Toronto Pearson\n")
for f in flights[:6]:
    status = "ON GROUND" if f.on_ground else f"ALT {int(f.baro_altitude_m):,}m"
    print(f"  ✈  {f.callsign:<10}  {status:<18}  "
          f"{f.latitude:.4f}°N  {f.longitude:.4f}°W  "
          f"spd={int(f.velocity_ms*1.94):>3}kts  hdg={int(f.true_track_deg):>3}°")
if len(flights) > 6:
    print(f"  ... and {len(flights)-6} more")

# ── 2. Live Weather (METAR) ────────────────────────────────────────────────────
section("② LIVE WEATHER  —  METAR / aviationweather.gov")
from layer1.weather_client import fetch_weather
wx = fetch_weather()
print(f"  Station  : {wx['station']}  ({wx['report_time']})")
print(f"  METAR    : {wx['raw_metar']}")
print(f"  Wind     : {wx['wind_speed_kts']}kts @ {wx['wind_dir_deg']}°"
      + (f"  gusts {wx['wind_gust_kts']}kts" if wx.get('wind_gust_kts') else ""))
print(f"  Vis      : {wx['visibility_sm']} SM")
print(f"  Ceiling  : {wx['ceiling_ft']} ft" if wx['ceiling_ft'] else "  Ceiling  : Clear")
print(f"  Warnings : storm={wx['storm_warning']}  low_vis={wx['low_visibility']}")

# ── 3. Video Frames ────────────────────────────────────────────────────────────
section("③ VIDEO FRAMES  —  Scope ATC Tower Chatter (local MP4)")
frames_dir = "output/frames"
frame_files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".jpg"))
print(f"  {len(frame_files)} frames extracted  (1 frame every 10 seconds)")
print(f"  Video duration  : 02:03:46  (7426 seconds)")
print(f"  First frame     : {frame_files[0]}")
print(f"  Last frame      : {frame_files[-1]}")
print(f"  Sample path     : output/frames/{frame_files[len(frame_files)//2]}")

# ── 4. ATC Transcript ─────────────────────────────────────────────────────────
section("④ ATC TRANSCRIPT  —  Timestamped segments paired to frames")
with open("output/frames_with_transcript.json") as fh:
    paired = json.load(fh)

print(f"  {len(paired)} frames × transcript pairings  |  353 ATC segments\n")
samples = [paired[0], paired[30], paired[120], paired[300], paired[500]]
for entry in samples:
    ts  = entry["timestamp_fmt"]
    atc = entry["atc_transcript"][:65]
    seg = entry["segment_id"]
    wx_entry = entry.get("weather", {})
    storm = wx_entry.get("storm_warning", "–")
    print(f"  [{ts}]  seg#{seg:>3}  \"{atc}...\"")
    print(f"           weather attached: storm={storm}  "
          f"wind={wx_entry.get('wind_speed_kts','–')}kts")
    print()

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'═'*W}")
print(f"  LAYER 1 COMPLETE — All inputs ready for Layer 2 (JSON formatter)")
print(f"  ✓ {len(flights):>3} live flights    (OpenSky ADS-B)")
print(f"  ✓   1 weather snapshot  (METAR CYYZ)")
print(f"  ✓ {len(frame_files):>3} video frames    (output/frames/)")
print(f"  ✓ {len(paired):>3} paired entries  (output/frames_with_transcript.json)")
print(f"{'═'*W}\n")
