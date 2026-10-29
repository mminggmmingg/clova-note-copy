#!/usr/bin/env python3
import json
import sys
import wave
from pathlib import Path

ROOT = Path.home() / "clova-note-copy" / "data" / "sessions"
sessions = [p for p in ROOT.glob('*') if p.is_dir() and (p/'session.json').is_file()]
if not sessions:
    raise SystemExit(f'No sessions under {ROOT}')
session = max(sessions, key=lambda p: (p/'session.json').stat().st_mtime)
meta = json.loads((session/'session.json').read_text(encoding='utf-8'))
raw = session / str(meta.get('continuous_raw_audio') or 'lecture_raw.wav')
errors=[]
warnings=[]
print('Session       :', session.name)
print('Capture       :', meta.get('capture_backend'))
print('Native schema :', meta.get('native_capture_schema'))
print('Clock basis   :', meta.get('recording_time_basis'))
print('Recording     :', meta.get('recording_samples'), 'samples')
print('Dropped ASR   :', meta.get('native_capture_dropped_chunks', 0), 'chunks')
if meta.get('capture_backend') != 'native_pipewire_pw_record':
    errors.append('capture_backend is not native_pipewire_pw_record')
if meta.get('recording_time_basis') != 'native_pipewire_samples':
    errors.append('recording_time_basis is not native_pipewire_samples')
if not raw.is_file():
    errors.append(f'missing {raw}')
    frames=0
else:
    with wave.open(str(raw),'rb') as w:
        frames=w.getnframes(); rate=w.getframerate(); ch=w.getnchannels(); width=w.getsampwidth()
    print(f'RAW WAV       : {frames} frames · {rate} Hz · {ch}ch · {width*8}bit')
    if rate != 16000: errors.append(f'RAW rate != 16000 ({rate})')
    if ch != 1: errors.append(f'RAW channels != 1 ({ch})')
    if width != 2: errors.append(f'RAW sample width != 16 bit ({width*8})')
expected=int(meta.get('recording_samples') or 0)
meta_frames=int(meta.get('continuous_raw_samples') or 0)
start=int(meta.get('continuous_raw_start_sample') or 0)
if meta_frames and frames != meta_frames:
    errors.append(f'continuous_raw_samples={meta_frames}, WAV frames={frames}')
if expected and start + frames != expected:
    errors.append(f'RAW coverage end {start+frames} != recording_samples {expected}')
dropped=int(meta.get('native_capture_dropped_chunks') or 0)
if dropped:
    warnings.append(f'{dropped} ASR inference chunks were dropped; RAW audio is still authoritative')
for x in warnings: print('WARN          :',x)
for x in errors: print('ERROR         :',x)
print('RESULT        :', 'FAIL' if errors else 'PASS')
sys.exit(1 if errors else 0)
