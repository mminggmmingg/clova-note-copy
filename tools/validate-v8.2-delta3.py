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
prof = (ROOT / "asr" / "engines" / "professor_lora.py").read_text(encoding="utf-8")
controller = (ROOT / "clova_host_control_v8_2_delta.py").read_text(encoding="utf-8")

# Delta-1/2 production adapters remain intact.
need('class BatiSayEngine(ASREngine)' in batisay, "BatiSayEngine missing")
need('class Qwen3ASREngine(ASREngine)' in qwen, "Qwen3ASREngine missing")
need('BatiSayEngine(_legacy_batisay_transcribe_impl' in backend, "BatiSay adapter registration missing")
need('Qwen3ASREngine(qwen_asr, sample_rate=SR)' in backend, "Qwen adapter registration missing")
need('qwen_asr.init_streaming_state(' not in backend, "legacy direct Qwen init call remains")
need('qwen_asr.streaming_transcribe(' not in backend, "legacy direct Qwen streaming call remains")
need('qwen_asr.finish_streaming_transcribe(' not in backend, "legacy direct Qwen finish call remains")

# Delta-3 adaptation boundary.
need('class ProfessorLoRAEngine(ASREngine)' in prof, "ProfessorLoRAEngine missing")
need('from asr.engines.professor_lora import ProfessorLoRAEngine' in backend, "Professor adapter import missing")
need('ProfessorLoRAEngine(' in backend, "Professor adapter registration missing")
need('def _professor_adaptation_engine()' in backend, "adaptation slot resolver missing")
need('_professor_adaptation_engine().activate_adaptation(professor_id=professor_id)' in backend,
     "BatiSay professor activation does not route through adaptation engine")
need('_professor_adaptation_engine().capture_supervision(session=s, segment=segment, human_text=text)' in backend,
     "Human LOCK supervision capture does not route through adaptation engine")
need('_professor_adaptation_engine().adaptation_status(professor_id=professor_id)' in backend,
     "Professor status API does not route through adaptation engine")
need('_professor_adaptation_engine().request_training(professor_id=professor_id)' in backend,
     "Professor training API does not route through adaptation engine")
need('delta_3_full_asr_adaptation' in registry, "registry Delta-3 phase missing")
need('qwen_batisay_professor_adapters' in registry, "registry Delta-3 production mode missing")
need(profile.get('slots', {}).get('adaptation', {}).get('engine') == 'professor-lora', "adaptation profile slot changed")

# Proven adaptation invariants remain present.
need('capture_training_samples_from_manual_edit' in backend, "Human correction capture core missing")
need('recover_historical_phrase_samples' in backend, "historical phrase recovery missing")
need('set_training_samples_disabled_for_subject' in backend, "subject reassignment training guard missing")
need('LORA_TRAIN_SCRIPT = Path("/workspace/professor_lora_v7_9.py")' in backend, "proven trainer path changed")
need('Human LOCK' in backend, "Human LOCK precedence marker missing")

# Stable gamma audio/VAD invariants remain frozen.
need('"--channels", "2"' in controller, "frozen stereo capture setting missing")
need('native_audio_daemon_v8_2_beta.py' in controller, "frozen native daemon path changed/missing")
need('AUDIO_FRONTEND_SCHEMA = "v8.2-gamma-pywebrtc-stereo-frontend-v1"' in backend, "stable pywebrtc frontend changed")
need('NATIVE_CAPTURE_SCHEMA = "v8.2-gamma-stereo-raw-backed-inference-v1"' in backend, "stable native capture schema changed")
need('VAD_THRESHOLD = 0.50' in backend, "Silero threshold changed")
need('MAX_SENTENCE_SEC = 28.0' in backend, "Adaptive Segmenter max duration changed")

if errors:
    for e in errors:
        print("FAIL:", e)
    raise SystemExit(1)
print("PASS: V8.2-delta-3 full ASR/adaptation adapters + frozen gamma audio/VAD invariants")
