#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asr.base import ASREngine, ASREngineCapabilities, ASREngineError
from asr.registry import REGISTRY_SCHEMA, build_default_registry
from asr.schema import CANONICAL_ASR_SCHEMA, canonical_asr_result, validate_canonical_asr_result

registry = build_default_registry(ROOT / "asr" / "profiles" / "default.yaml")
snap = registry.snapshot()
assert snap["schema"] == REGISTRY_SCHEMA
assert snap["canonical_result_schema"] == CANONICAL_ASR_SCHEMA
assert snap["migration_phase"] == "interface_only"
assert snap["production_execution"] == "legacy_direct_until_v8.2-delta"

slots = snap["profile"]["slots"]
assert slots["preview"]["engine"] == "qwen3-asr-1.7b"
assert slots["committed"]["engine"] == "batisay-ko-large"
assert slots["adaptation"]["engine"] == "professor-lora"

engines = {x["id"]: x for x in snap["engines"]}
assert engines["qwen3-asr-1.7b"]["capabilities"]["streaming"] is True
assert engines["batisay-ko-large"]["capabilities"]["batch"] is True
assert engines["batisay-ko-large"]["capabilities"]["word_timestamps"] is True
assert engines["professor-lora"]["base_engine"] == "batisay-ko-large"

result = canonical_asr_result(
    text=" 테스트 ", start=1.25, end=2.75,
    words=[{"text": "테스트", "start": 1.25, "end": 2.7}],
    language="ko", engine="fake-engine", final=True,
)
assert result["text"] == "테스트"
assert result["schema"] == CANONICAL_ASR_SCHEMA
assert validate_canonical_asr_result(result) == []

class FakeEngine(ASREngine):
    id = "fake-engine"
    display_name = "Fake Engine"
    def capabilities(self):
        return ASREngineCapabilities(batch=True, languages=("ko",))
    def transcribe(self, audio, **options):
        return canonical_asr_result(text="ok", engine=self.id)

fake = FakeEngine()
registry.register_engine(fake)
assert registry.get_engine("fake-engine") is fake
assert registry.get_engine("fake-engine").transcribe(None)["text"] == "ok"
assert "fake-engine" in registry.snapshot()["loaded_plugin_engines"]

backend = (ROOT / "run_clova_v8_2_gamma.py").read_text(encoding="utf-8")
assert "build_default_registry" in backend
assert '"/api/asr/registry"' in backend
assert "qwen_asr.streaming_transcribe" in backend, "Gamma must preserve Qwen direct path"
assert "batisay_transcribe(primary_audio" in backend, "Gamma must preserve BatiSay direct path"

print("V8.2-gamma ASR plugin interface: PASS")
