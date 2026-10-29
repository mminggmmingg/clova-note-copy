#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
errors = []

def need(cond, msg):
    if not cond:
        errors.append(msg)

backend = (ROOT / "run_clova_v8_2_delta.py").read_text(encoding="utf-8")
registry = (ROOT / "asr" / "registry.py").read_text(encoding="utf-8")
profile = json.loads((ROOT / "asr" / "profiles" / "default.yaml").read_text(encoding="utf-8"))
batisay = (ROOT / "asr" / "engines" / "batisay.py").read_text(encoding="utf-8")
qwen = (ROOT / "asr" / "engines" / "qwen3_asr.py").read_text(encoding="utf-8")
controller = (ROOT / "clova_host_control_v8_2_delta.py").read_text(encoding="utf-8")

# Delta-1 committed path remains adapter-backed.
need('def _legacy_batisay_transcribe_impl(' in backend, "legacy BatiSay core missing")
need('ASR_REGISTRY.get_engine(engine_id)' in backend, "committed engine registry bridge missing")
need('BatiSayEngine(_legacy_batisay_transcribe_impl' in backend, "BatiSay adapter is not registered")
need('class BatiSayEngine(ASREngine)' in batisay, "BatiSayEngine missing")

# Delta-2 realtime Qwen path must be adapter-backed end-to-end.
need('class Qwen3ASREngine(ASREngine)' in qwen, "Qwen3ASREngine missing")
need('from asr.engines.qwen3_asr import Qwen3ASREngine' in backend, "Qwen adapter import missing")
need('Qwen3ASREngine(qwen_asr, sample_rate=SR)' in backend, "Qwen adapter is not registered")
need('def _qwen_preview_engine()' in backend, "Qwen registry resolver missing")
need('_qwen_preview_engine().start_stream(' in backend, "Qwen stream start is not adapter-backed")
need('_qwen_preview_engine().push_audio(' in backend, "Qwen streaming push is not adapter-backed")
need('_qwen_preview_engine().finish_stream(' in backend, "Qwen finish is not adapter-backed")
need('qwen_asr.init_streaming_state(' not in backend, "legacy direct Qwen init call remains")
need('qwen_asr.streaming_transcribe(' not in backend, "legacy direct Qwen streaming call remains")
need('qwen_asr.finish_streaming_transcribe(' not in backend, "legacy direct Qwen finish call remains")
need('delta_2_qwen_batisay' in registry, "registry Delta-2 phase missing")
need('qwen_batisay_adapters_professor_legacy_overlay' in registry, "registry Delta-2 production mode missing")
need('"schema": "v8.2-delta-asr-profile-v1"' in json.dumps(profile), "delta profile schema missing")

# Stable gamma audio/capture invariants remain frozen.
need('"--channels", "2"' in controller, "frozen stereo capture setting missing")
need('native_audio_daemon_v8_2_beta.py' in controller, "frozen native daemon path changed/missing")
need('AUDIO_FRONTEND_SCHEMA = "v8.2-gamma-pywebrtc-stereo-frontend-v1"' in backend, "stable pywebrtc frontend changed")
need('NATIVE_CAPTURE_SCHEMA = "v8.2-gamma-stereo-raw-backed-inference-v1"' in backend, "stable native capture schema changed")
need(backend.count('_legacy_batisay_transcribe_impl(') == 1, "unexpected legacy BatiSay implementation call/definition count")

if errors:
    for e in errors:
        print("FAIL:", e)
    raise SystemExit(1)
print("PASS: V8.2-delta-2 Qwen+BatiSay adapters + frozen gamma audio/VAD invariants")
