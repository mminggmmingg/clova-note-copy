#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asr.engines.batisay import BatiSayEngine
from asr.registry import build_default_registry
from asr.schema import validate_canonical_asr_result


def fake_backend(audio, professor_id=""):
    return (
        "델타 어댑터 테스트",
        False,
        "",
        [
            {"text": "델타", "timestamp": [0.0, 0.25]},
            {"text": "어댑터", "timestamp": [0.25, 0.55]},
            {"text": "테스트", "timestamp": [0.55, 0.80]},
        ],
        {"name": "base", "version": "", "professor_id": professor_id},
    )

engine = BatiSayEngine(fake_backend, sample_rate=16000)
result = engine.transcribe([0] * 16000, professor_id="prof-test", sample_rate=16000)
assert not validate_canonical_asr_result(result), result
assert result["text"] == "델타 어댑터 테스트"
assert result["metadata"]["adapter"]["professor_id"] == "prof-test"
assert result["metadata"]["chunks"][1]["timestamp"] == [0.25, 0.55]
assert len(result["words"]) == 3

registry = build_default_registry(ROOT / "asr" / "profiles" / "default.yaml")
registry.register_engine(engine)
snap = registry.snapshot()
assert snap["migration_phase"] == "delta_1_batisay", snap
assert snap["production_execution"] == "batisay_adapter_qwen_legacy", snap
assert "batisay-ko-large" in snap["loaded_plugin_engines"], snap
committed = [x for x in snap["engines"] if x["id"] == "batisay-ko-large"][0]
assert committed["execution_mode"] == "plugin", committed
print("PASS: BatiSay adapter canonical-result and registry self-test")
