"""
Layer 1 — Video Processor
Extracts frames (every N seconds) + transcript from local ATC runway videos.
Pairs each frame with its transcript segment by timestamp.

Output per video:
  {
    "video_file": "...",
    "duration_s": 3600,
    "frames": [
      {
        "timestamp_s":      10,
        "timestamp_fmt":    "00:00:10",
        "frame_path":       "output/frames/video1_t0010.jpg",
        "transcript_text":  "Air Canada 42, runway 23L, cleared to land...",
        "weather_snapshot": { ...from weather_client... }
      }, ...
    ],
    "full_transcript": "..."
  }
"""
import os
import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

import cv2

VIDEO_DIR   = "/Users/ahmadjajja/D Drive/Programming/YT Airport Videos"
OUTPUT_DIR  = "output"
FRAMES_DIR  = os.path.join(OUTPUT_DIR, "frames")
FRAME_EVERY = 10   # extract one frame every N seconds

VIDEOS = [
    os.path.join(VIDEO_DIR, "YTDown_YouTube_Scope-ATC-Real-Tower-Chatter-_-Radar-fro_Media_PYuAXxHXvgk_001_1080p.mp4"),
]

VIDEO_LABELS = {
    VIDEOS[0]: "scope_atc_tower_chatter",
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _ensure_dirs():
    os.makedirs(FRAMES_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frames(video_path: str, every_n_sec: int = FRAME_EVERY) -> List[Dict]:
    """
    Extract one frame every `every_n_sec` seconds from the video.
    Returns list of { timestamp_s, timestamp_fmt, frame_path }.
    """
    _ensure_dirs()
    label  = VIDEO_LABELS.get(video_path, Path(video_path).stem)
    cap    = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"[Video] Cannot open: {video_path}")
        return []

    fps      = cap.get(cv2.CAP_PROP_FPS) or 30
    total_f  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_f / fps
    step     = int(fps * every_n_sec)

    print(f"[Video] {label}")
    print(f"        Duration : {_fmt(duration)}  ({duration:.0f}s)")
    print(f"        FPS      : {fps:.1f}")
    print(f"        Frames   : {total_f}  →  extracting 1 every {every_n_sec}s = ~{math.ceil(duration/every_n_sec)} frames")

    frames = []
    frame_idx = 0

    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        ts_s    = frame_idx / fps
        ts_fmt  = _fmt(ts_s)
        fname   = f"{label}_t{int(ts_s):05d}.jpg"
        fpath   = os.path.join(FRAMES_DIR, fname)

        cv2.imwrite(fpath, frame)
        frames.append({
            "timestamp_s":   round(ts_s, 2),
            "timestamp_fmt": ts_fmt,
            "frame_path":    fpath,
        })

        frame_idx += step
        if frame_idx >= total_f:
            break

    cap.release()
    print(f"        Extracted: {len(frames)} frames → {FRAMES_DIR}/")
    return frames


# ── Transcript extraction ─────────────────────────────────────────────────────

def extract_transcript(video_path: str, model_size: str = "base") -> List[Dict]:
    """
    Transcribe the video audio using Whisper.
    Returns list of { start, end, text } segments with timestamps.
    model_size options: tiny | base | small | medium | large
    'base' is the best balance of speed vs accuracy for ATC audio.
    """
    try:
        import whisper
    except ImportError:
        print("[Transcript] whisper not installed. Run: pip install openai-whisper")
        return []

    label = VIDEO_LABELS.get(video_path, Path(video_path).stem)
    print(f"\n[Transcript] Transcribing {label} with Whisper ({model_size})...")
    print(f"             This takes a few minutes for long videos. Please wait.")

    model  = whisper.load_model(model_size)
    result = model.transcribe(video_path, language="en", verbose=False)

    segments = [
        {
            "start": round(seg["start"], 2),
            "end":   round(seg["end"], 2),
            "text":  seg["text"].strip(),
        }
        for seg in result.get("segments", [])
    ]

    print(f"[Transcript] Done — {len(segments)} segments transcribed.")
    return segments


# ── Pair frames with transcript ───────────────────────────────────────────────

def pair_frames_with_transcript(
    frames: List[Dict],
    segments: List[Dict],
    weather: Optional[Dict] = None,
) -> List[Dict]:
    """
    For each frame, find all transcript segments within a ±15s window
    and attach them as the spoken ATC text for that moment.
    Also attaches weather snapshot if provided.
    """
    paired = []
    for f in frames:
        ts = f["timestamp_s"]
        window_start = ts - 15
        window_end   = ts + 15

        nearby = [
            s["text"] for s in segments
            if s["start"] <= window_end and s["end"] >= window_start
        ]
        atc_text = " ".join(nearby).strip()

        entry = {
            "timestamp_s":      f["timestamp_s"],
            "timestamp_fmt":    f["timestamp_fmt"],
            "frame_path":       f["frame_path"],
            "transcript_text":  atc_text or "[no speech detected]",
        }
        if weather:
            entry["weather_snapshot"] = {
                "wind_dir_deg":   weather.get("wind_dir_deg"),
                "wind_speed_kts": weather.get("wind_speed_kts"),
                "wind_gust_kts":  weather.get("wind_gust_kts"),
                "visibility_sm":  weather.get("visibility_sm"),
                "ceiling_ft":     weather.get("ceiling_ft"),
                "conditions":     weather.get("conditions", ""),
                "storm_warning":  weather.get("storm_warning", False),
                "raw_metar":      weather.get("raw_metar", ""),
            }
        paired.append(entry)

    return paired


# ── Process one video end-to-end ──────────────────────────────────────────────

def process_video(
    video_path: str,
    every_n_sec: int = FRAME_EVERY,
    weather: Optional[Dict] = None,
    transcribe: bool = True,
    model_size: str = "base",
) -> Dict[str, Any]:
    """
    Full pipeline for one video:
    frames + transcript + weather → paired output dict.
    """
    label   = VIDEO_LABELS.get(video_path, Path(video_path).stem)
    frames  = extract_frames(video_path, every_n_sec)
    segments = extract_transcript(video_path, model_size) if transcribe else []

    paired = pair_frames_with_transcript(frames, segments, weather)

    full_text = " ".join(s["text"] for s in segments)

    result = {
        "label":            label,
        "video_file":       video_path,
        "frame_count":      len(frames),
        "segment_count":    len(segments),
        "paired_entries":   len(paired),
        "full_transcript":  full_text,
        "data":             paired,
    }

    # Save to JSON
    out_path = os.path.join(OUTPUT_DIR, f"{label}_processed.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[Video] Saved → {out_path}")

    return result


# ── Process all videos ────────────────────────────────────────────────────────

def process_all_videos(
    every_n_sec: int = FRAME_EVERY,
    transcribe: bool = True,
    model_size: str = "base",
) -> List[Dict]:
    """Process all videos in VIDEOS list. Fetches live weather once and reuses it."""
    from layer1.weather_client import fetch_weather
    print("\n[Weather] Fetching live METAR for CYYZ...")
    weather = fetch_weather()
    print(f"[Weather] {weather.get('raw_metar', 'N/A')}\n")

    results = []
    for vpath in VIDEOS:
        if not os.path.exists(vpath):
            print(f"[Video] File not found: {vpath}")
            continue
        print(f"\n{'='*60}")
        result = process_video(vpath, every_n_sec, weather, transcribe, model_size)
        results.append(result)

    return results


# ── Quick preview (no transcription) ─────────────────────────────────────────

def preview_frames_only(every_n_sec: int = 30) -> None:
    """Fast run — extract frames only, skip transcription. Good for testing."""
    _ensure_dirs()
    for vpath in VIDEOS:
        if not os.path.exists(vpath):
            print(f"[Video] Not found: {vpath}")
            continue
        frames = extract_frames(vpath, every_n_sec)
        print(f"  → {len(frames)} frames extracted\n")
        # Print first 3 as sample
        for f in frames[:3]:
            print(f"    [{f['timestamp_fmt']}] {f['frame_path']}")


# ── YouTube download via yt-dlp ───────────────────────────────────────────────

def download_youtube(url: str, output_path: Optional[str] = None) -> str:
    """
    Download a YouTube video (or live stream segment) using yt-dlp.
    Returns path to the downloaded file, or "" on failure.

    Set YT_STREAM_URL env var to auto-download on startup.
    """
    import subprocess

    if output_path is None:
        _ensure_dirs()
        output_path = os.path.join(OUTPUT_DIR, "yt_stream.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "best[height<=720]/best",
        "--no-playlist",
        "-o", output_path,
        url,
    ]
    print(f"[yt-dlp] Downloading: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[yt-dlp] Error: {result.stderr[:300]}")
        return ""

    # Resolve the actual filename (yt-dlp replaces %(ext)s)
    for ext in ("mp4", "webm", "mkv"):
        candidate = output_path.replace("%(ext)s", ext)
        if os.path.exists(candidate):
            print(f"[yt-dlp] Downloaded → {candidate}")
            return candidate
    return output_path


def ingest_youtube_stream(url: str) -> Optional[str]:
    """
    Download a YouTube video, extract frames + transcript, return processed JSON path.
    Skips download if the file already exists.
    """
    _ensure_dirs()
    dest = os.path.join(OUTPUT_DIR, "yt_stream.mp4")

    if not os.path.exists(dest):
        dest = download_youtube(url, os.path.join(OUTPUT_DIR, "yt_stream.%(ext)s"))
        if not dest:
            return None

    # Temporarily register this video so process_video picks it up
    VIDEO_LABELS[dest] = "yt_stream"
    result = process_video(dest, every_n_sec=FRAME_EVERY, transcribe=True)
    out_path = os.path.join(OUTPUT_DIR, "yt_stream_processed.json")
    return out_path if os.path.exists(out_path) else None


# ── Latest frame helper ───────────────────────────────────────────────────────

def get_latest_frame() -> Optional[str]:
    """
    Return the path of the best available frame from already-processed video.

    Reads output/frames_with_transcript.json (or any *_processed.json).
    Returns a frame from the middle of the video for maximum visual context.
    Returns None if no processed frames exist.
    """
    _ensure_dirs()

    # Try the primary output files in order of preference
    candidates = [
        Path(OUTPUT_DIR) / "frames_with_transcript.json",
        *sorted(Path(OUTPUT_DIR).glob("*_processed.json")),
    ]

    for json_path in candidates:
        if not json_path.exists():
            continue
        try:
            with open(json_path) as f:
                data = json.load(f)

            # Handle both flat array and nested {"data": [...]} formats
            frames = data if isinstance(data, list) else data.get("data", [])
            if not frames:
                continue

            # Pick the middle frame for best runway context
            entry = frames[len(frames) // 2]
            frame_path = entry.get("frame_path")
            if frame_path and Path(frame_path).exists():
                return frame_path
        except Exception:
            continue

    # Last resort: pick any .jpg directly from frames dir
    frame_files = sorted(Path(FRAMES_DIR).glob("*.jpg"))
    if frame_files:
        return str(frame_files[len(frame_files) // 2])

    return None


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if mode == "preview":
        # Fast: frames only, 1 every 30s — good for quick test
        print("\nRunwAI Video Processor — PREVIEW MODE (frames only, no transcription)")
        print("Run with 'full' argument for frames + transcript\n")
        preview_frames_only(every_n_sec=30)

    elif mode == "full":
        # Full pipeline: frames + whisper transcript + weather
        print("\nRunwAI Video Processor — FULL MODE (frames + transcript + weather)")
        results = process_all_videos(every_n_sec=10, transcribe=True, model_size="base")
        print(f"\nDone. Processed {len(results)} videos.")
        for r in results:
            print(f"  {r['label']}: {r['frame_count']} frames, {r['segment_count']} transcript segments")

    else:
        print(f"Unknown mode: {mode}. Use 'preview' or 'full'.")
