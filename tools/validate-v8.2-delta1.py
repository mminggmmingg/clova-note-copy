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
adapter = (ROOT / "asr" / "engines" / "batisay.py").read_text(encoding="utf-8")
controller = (ROOT / "clova_host_control_v8_2_delta.py").read_text(encoding="utf-8")

need('def _legacy_batisay_transcribe_impl(' in backend, "legacy BatiSay core missing")
need('def batisay_transcribe(' in backend, "registry bridge missing")
need('ASR_REGISTRY.get_engine(engine_id)' in backend, "committed engine is not resolved through registry")
need('BatiSayEngine(_legacy_batisay_transcribe_impl' in backend, "BatiSay adapter is not registered")
need('migration_phase": "delta_1_batisay"' in registry, "registry delta-1 phase missing")
need('"schema": "v8.2-delta-asr-profile-v1"' in json.dumps(profile), "delta profile schema missing")
need('class BatiSayEngine(ASREngine)' in adapter, "BatiSayEngine missing")
need('canonical_asr_result(' in adapter, "adapter does not emit canonical result")
need('"--channels", "2"' in controller, "frozen stereo capture setting missing")
need('native_audio_daemon_v8_2_beta.py' in controller, "frozen native daemon path changed/missing")
# Production worker must call the bridge, never the implementation directly.
need(backend.count('_legacy_batisay_transcribe_impl(') == 1, "unexpected legacy BatiSay implementation call/definition count")

if errors:
    for e in errors:
        print("FAIL:", e)
    raise SystemExit(1)
print("PASS: V8.2-delta-1 BatiSay adapter wiring + frozen stereo capture invariants")
