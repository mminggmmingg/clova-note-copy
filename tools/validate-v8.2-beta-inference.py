#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
import wave
from pathlib import Path

PROJECT = Path.home() / "clova-note-copy"
SESSIONS = PROJECT / "data" / "sessions"
RUNTIME = PROJECT / ".runtime-v8.2-gamma"

sid = sys.argv[1] if len(sys.argv) > 1 else ""
if not sid:
    dirs = sorted((p for p in SESSIONS.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dirs:
        raise SystemExit("No sessions found")
    sid = dirs[0].name
root = SESSIONS / sid
meta_path = root / "session.json"
raw_path = root / "lecture_raw.wav"
status_path = RUNTIME / f"capture-{sid}.json"

meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}

errors = []
if not raw_path.is_file():
    errors.append("lecture_raw.wav missing")
    frames = 0
    rate = 0
    channels = 0
    width = 0
else:
    with wave.open(str(raw_path), "rb") as f:
        frames = f.getnframes(); rate = f.getframerate(); channels = f.getnchannels(); width = f.getsampwidth()
    if rate != 16000 or channels != 1 or width != 2:
        errors.append(f"unexpected RAW format: {rate}Hz {channels}ch {width*8}bit")

schema = str(meta.get("native_capture_schema") or "")
if schema and schema != "v8.2-beta-raw-backed-inference-v1":
    errors.append(f"unexpected native_capture_schema: {schema}")

dropped = int(status.get("dropped_chunks") or meta.get("native_capture_dropped_chunks") or 0)
if dropped != 0:
    errors.append(f"dropped ASR chunks: {dropped}")

cursor = int(status.get("inference_cursor_sample") or meta.get("native_inference_cursor_sample") or 0)
backlog_samples = int(status.get("inference_backlog_samples") or meta.get("native_inference_backlog_samples") or 0)
backlog_sec = float(status.get("inference_backlog_sec") or meta.get("native_inference_backlog_sec") or 0.0)
if status and not bool(status.get("active", False)) and backlog_samples > 0:
    errors.append(f"stopped session has unprocessed inference backlog: {backlog_samples} samples")

print(f"Session        : {sid}")
print(f"Capture        : {meta.get('capture_backend','native_pipewire_pw_record')}")
print(f"Schema         : {schema or 'unknown'}")
print(f"RAW WAV        : {frames} frames · {rate} Hz · {channels}ch · {width*8}bit")
print(f"Inference cur. : {cursor} samples")
print(f"Backlog        : {backlog_samples} samples · {backlog_sec:.3f}s")
print(f"Dropped ASR    : {dropped} chunks")
print(f"RESULT         : {'FAIL' if errors else 'PASS'}")
if errors:
    for e in errors: print(f"  - {e}")
    raise SystemExit(1)
