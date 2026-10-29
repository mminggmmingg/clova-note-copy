#!/usr/bin/env python3
import json
import sys
import wave
from pathlib import Path

ROOT = Path.home() / "clova-note-copy" / "data" / "sessions"

if not ROOT.exists():
    raise SystemExit(f"No sessions directory: {ROOT}")

sessions = [p for p in ROOT.iterdir() if p.is_dir() and (p / "session.json").exists()]
if not sessions:
    raise SystemExit(f"No sessions under {ROOT}")

session = max(sessions, key=lambda p: (p / "session.json").stat().st_mtime)
meta = json.loads((session / "session.json").read_text(encoding="utf-8"))
raw_path = session / str(meta.get("continuous_raw_audio") or "lecture_raw.wav")
expected = int(meta.get("recording_samples") or 0)
start = int(meta.get("continuous_raw_start_sample") or 0)
meta_frames = int(meta.get("continuous_raw_samples") or 0)
errors = []
warnings = []

print(f"Session      : {session.name}")
print(f"Timeline     : {meta.get('timeline_schema')}")
print(f"Audio schema : {meta.get('audio_provenance_schema')}")
print(f"STT source   : {meta.get('stt_audio_source', 'legacy')}")
print(f"Recording    : {expected} samples ({expected / 16000:.3f}s)")
print(f"RAW offset   : {start} samples ({start / 16000:.3f}s)")

if not raw_path.exists():
    errors.append(f"continuous raw WAV missing: {raw_path}")
    frames = 0
else:
    try:
        with wave.open(str(raw_path), "rb") as w:
            channels = w.getnchannels()
            rate = w.getframerate()
            width = w.getsampwidth()
            frames = w.getnframes()
        print(f"RAW WAV      : {frames} frames · {rate} Hz · {channels}ch · {width * 8}bit")
        if channels != 1: errors.append(f"RAW channels != 1 ({channels})")
        if rate != 16000: errors.append(f"RAW sample rate != 16000 ({rate})")
        if width != 2: errors.append(f"RAW sample width != 16-bit ({width * 8})")
    except Exception as exc:
        frames = 0
        errors.append(f"cannot read RAW WAV: {exc}")

if meta_frames and frames != meta_frames:
    errors.append(f"session.json continuous_raw_samples={meta_frames}, WAV frames={frames}")

if start + frames != expected:
    errors.append(
        f"continuous raw coverage end {start + frames} != recording_samples {expected}"
    )

settings = meta.get("capture_settings") if isinstance(meta.get("capture_settings"), dict) else {}
if settings:
    print("Capture DSP  :", json.dumps({
        "echoCancellation": settings.get("echoCancellation"),
        "noiseSuppression": settings.get("noiseSuppression"),
        "autoGainControl": settings.get("autoGainControl"),
        "sampleRate": settings.get("sampleRate"),
        "channelCount": settings.get("channelCount"),
    }, ensure_ascii=False))
    for key in ("echoCancellation", "noiseSuppression", "autoGainControl"):
        if settings.get(key) is True:
            warnings.append(f"browser/device reports {key}=true despite raw request")
else:
    warnings.append("capture_settings not recorded (old session or browser did not report settings)")

segments = session / "segments"
clean = session / "segments_clean"
raw_seg_count = len(list(segments.glob("*.wav"))) if segments.exists() else 0
clean_seg_count = len(list(clean.glob("*.wav"))) if clean.exists() else 0
print(f"SEG WAVs     : raw={raw_seg_count} clean={clean_seg_count}")

for msg in warnings:
    print("WARN         :", msg)

if errors:
    for msg in errors:
        print("ERROR        :", msg)
    print("RESULT       : FAIL")
    sys.exit(1)

print("RESULT       : PASS")
