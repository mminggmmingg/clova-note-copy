#!/usr/bin/env python3
from pathlib import Path
import tempfile
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from audio_capture_v8 import append_float32_mono_wav, normalize_stt_audio_source, wav_frame_count

assert normalize_stt_audio_source("RAW") == "raw"
assert normalize_stt_audio_source("clean") == "clean"
assert normalize_stt_audio_source("garbage") == "raw"

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "lecture_raw.wav"
    a = np.linspace(-0.5, 0.5, 4000, dtype=np.float32)
    b = np.zeros(6000, dtype=np.float32)
    assert append_float32_mono_wav(path, a, sample_rate=16000) == 4000
    assert append_float32_mono_wav(path, b, sample_rate=16000) == 6000
    assert wav_frame_count(path) == 10000
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000
        assert w.getsampwidth() == 2
        assert w.getnframes() == 10000

print("PASS: V8.0-alpha.1 audio provenance core")
