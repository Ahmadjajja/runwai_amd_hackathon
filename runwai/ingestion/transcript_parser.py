"""
Layer 1 — Transcript Parser
Reads timestamped transcript.txt (format: HH:MM:SS on one line, text on the next),
pairs each extracted video frame with its nearest transcript segment,
and attaches weather data.
"""
import os
import re
import json
from typing import List, Dict, Any

TRANSCRIPT_PATH = "transcript.txt"
OUTPUT_PATH     = "output/transcript_segments.json"

_TS_RE = re.compile(r'^(\d{2}):(\d{2}):(\d{2})$')


def _ts_to_s(ts: str) -> int:
    h, m, s = int(ts[:2]), int(ts[3:5]), int(ts[6:8])
    return h * 3600 + m * 60 + s


def parse_transcript(path: str = TRANSCRIPT_PATH) -> List[Dict]:
    """
    Parse timestamped ATC transcript into segments.
    Format expected:
        HH:MM:SS
        <text line(s)>

        HH:MM:SS
        ...
    Returns list of {segment_id, start_s, timestamp_fmt, text}.
    """
    segments = []
    current_ts = None
    current_lines = []

    with open(path, "r") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if _TS_RE.match(stripped):
                # Flush previous segment
                if current_ts is not None and current_lines:
                    text = " ".join(current_lines).strip()
                    if text:
                        segments.append({
                            "segment_id":    len(segments),
                            "start_s":       current_ts,
                            "timestamp_fmt": _fmt(current_ts),
                            "text":          text,
                        })
                current_ts    = _ts_to_s(stripped)
                current_lines = []
            elif stripped:
                current_lines.append(stripped)
            # blank lines are separators — ignore

    # Flush last segment
    if current_ts is not None and current_lines:
        text = " ".join(current_lines).strip()
        if text:
            segments.append({
                "segment_id":    len(segments),
                "start_s":       current_ts,
                "timestamp_fmt": _fmt(current_ts),
                "text":          text,
            })

    # Compute end_s for each segment (start of next, or start + 30 for last)
    for i, seg in enumerate(segments):
        if i + 1 < len(segments):
            seg["end_s"] = segments[i + 1]["start_s"]
        else:
            seg["end_s"] = seg["start_s"] + 30

    return segments


def _fmt(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def pair_with_frames(frames: List[Dict], segments: List[Dict]) -> List[Dict]:
    """
    For each frame, find the nearest transcript segment by timestamp.
    Also builds a context window (prev + current + next segment text).
    """
    if not segments:
        return [{**f, "atc_transcript": "", "atc_context": "", "segment_id": -1}
                for f in frames]

    paired = []
    for frame in frames:
        ts = frame["timestamp_s"]

        closest = min(segments, key=lambda s: abs((s["start_s"] + s["end_s"]) / 2 - ts))
        idx     = closest["segment_id"]

        context = " ".join(
            segments[i]["text"]
            for i in (idx - 1, idx, idx + 1)
            if 0 <= i < len(segments)
        )

        paired.append({
            "timestamp_s":   frame["timestamp_s"],
            "timestamp_fmt": frame["timestamp_fmt"],
            "frame_path":    frame["frame_path"],
            "atc_transcript": closest["text"],
            "atc_context":   context,
            "segment_id":    idx,
        })

    return paired


def parse_and_pair(
    transcript_path: str = TRANSCRIPT_PATH,
    frames: List[Dict] = None,
    weather: Dict = None,
) -> Dict[str, Any]:
    """
    Full pipeline:
    1. Parse timestamped transcript
    2. Pair with frames
    3. Attach weather snapshot
    4. Save JSONs
    """
    os.makedirs("output", exist_ok=True)

    segments = parse_transcript(transcript_path)
    print(f"[Transcript] {len(segments)} timestamped segments parsed from {transcript_path}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(segments, f, indent=2)
    print(f"[Transcript] Segments saved → {OUTPUT_PATH}")

    paired = []
    if frames:
        paired = pair_with_frames(frames, segments)

        if weather:
            weather_snap = {k: weather.get(k) for k in (
                "wind_dir_deg", "wind_speed_kts", "wind_gust_kts",
                "visibility_sm", "ceiling_ft", "conditions",
                "storm_warning", "raw_metar",
            )}
            for entry in paired:
                entry["weather"] = weather_snap

        paired_path = "output/frames_with_transcript.json"
        with open(paired_path, "w") as f:
            json.dump(paired, f, indent=2)
        print(f"[Transcript] {len(paired)} paired entries saved → {paired_path}")

    return {
        "segments":    segments,
        "paired":      paired,
        "chunk_count": len(segments),
        "frame_count": len(frames) if frames else 0,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from layer1.video_processor import extract_frames, VIDEOS
    from layer1.weather_client  import fetch_weather

    print("\nRunwAI — Transcript Parser\n")

    print("[Step 1] Extracting frames...")
    frames = extract_frames(VIDEOS[0], every_n_sec=10)

    print("\n[Step 2] Fetching live weather...")
    weather = fetch_weather()
    print(f"         {weather.get('raw_metar', 'N/A')}")

    print("\n[Step 3] Parsing transcript and pairing with frames...")
    result = parse_and_pair(TRANSCRIPT_PATH, frames, weather)

    print("\n--- Sample paired entries ---")
    for entry in result["paired"][:3]:
        print(f"\n  [{entry['timestamp_fmt']}]  frame: {os.path.basename(entry['frame_path'])}")
        print(f"  ATC: {entry['atc_transcript'][:120]}")
        if "weather" in entry:
            w = entry["weather"]
            print(f"  Weather: wind {w['wind_speed_kts']}kts @ {w['wind_dir_deg']}°  "
                  f"vis {w['visibility_sm']}SM  storm:{w['storm_warning']}")

    print(f"\nDone. {result['frame_count']} frames paired with {result['chunk_count']} transcript segments.")
