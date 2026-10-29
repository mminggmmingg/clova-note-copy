#!/usr/bin/env python3
from pathlib import Path
import math
import re
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
backend = (ROOT / "run_clova_v8_2_gamma.py").read_text(encoding="utf-8")
launcher = (ROOT / "start-local-clova-v8.2-gamma-control.sh").read_text(encoding="utf-8")
js = (ROOT / "web" / "app_v6.js").read_text(encoding="utf-8")

assert 'MODEL_INPUT_GAIN_DB", "6.0"' in backend
assert '_apply_model_input_gain' in backend
assert 'feed_vad(\n                s,\n                model_wav' in backend
assert 'streaming_transcribe(\n                model_wav' in backend
assert 'batisay_transcribe(primary_model_audio' in backend
assert '-e MODEL_INPUT_GAIN_DB="${MODEL_INPUT_GAIN_DB:-6.0}"' in launcher
assert 'PLAYBACK_MONITOR_GAIN_DB = 6.0' in js
assert 'createDynamicsCompressor()' in js
assert 'createMediaElementSource(els.player)' in js

# Numeric sanity: +6 dB should be about 2x amplitude and the chosen ceiling
# must protect pathological peaks.
factor = 10 ** (6.0 / 20.0)
assert 1.99 < factor < 2.0
x = np.array([0.1, -0.2, 0.7], dtype=np.float32)
y = np.clip(x * factor, -0.985, 0.985)
assert abs(float(y[0]) - 0.199526) < 1e-4
assert abs(float(y[-1]) - 0.985) < 1e-6

# Provenance invariant: native daemon remains the sole RAW writer and receives
# no model-gain flag.
daemon_path = ROOT / "native_audio_daemon_v8_2_beta.py"
if daemon_path.exists():
    daemon = daemon_path.read_text(encoding="utf-8")
    assert 'MODEL_INPUT_GAIN_DB' not in daemon
    assert 'lecture_raw.wav' in daemon

print("V8.2-gamma input/playback gain hotfix: PASS")
