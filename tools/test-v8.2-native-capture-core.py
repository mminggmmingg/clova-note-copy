#!/usr/bin/env python3
import importlib.util
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "native_audio_daemon_v8_2_beta.py"
BACKEND = ROOT / "run_clova_v8_2_gamma.py"
JS = ROOT / "web" / "app_v6.js"

spec = importlib.util.spec_from_file_location("clova_native_capture", DAEMON)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "test.wav"
    w = mod.CrashSafePcm16WavWriter(p, 16000)
    w.append((b"\x00\x00\x01\x00") * 1000)
    w.append((b"\xff\x7f\x00\x80") * 500)
    w.close()
    with wave.open(str(p), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getframerate() == 16000
        assert f.getsampwidth() == 2
        assert f.getnframes() == 3000

backend = BACKEND.read_text(encoding="utf-8")
js = JS.read_text(encoding="utf-8")
assert 'def api_native_clock()' in backend
assert 'def api_recording_status()' in backend
assert 'native_pipewire_samples' in backend
assert 'X-Clova-Native-Capture' in backend
assert '/capture/start' in backend and '/capture/stop' in backend
for forbidden in ('getUserMedia', 'createScriptProcessor', 'onaudioprocess'):
    assert forbidden not in js, forbidden
assert '/api/recording/status' in js
assert 'beginNativeCaptureMonitoring' in js
print('V8.2-beta native capture core: PASS')
