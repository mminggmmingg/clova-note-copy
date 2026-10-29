#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asr.engines.batisay import BatiSayEngine
from asr.engines.qwen3_asr import Qwen3ASREngine
from asr.engines.professor_lora import ProfessorLoRAEngine
from asr.registry import build_default_registry


class FakeState:
    text = ""


class FakeQwenRuntime:
    def init_streaming_state(self, **kwargs):
        return FakeState()
    def streaming_transcribe(self, audio, state):
        state.text = "미리보기"
    def finish_streaming_transcribe(self, state):
        state.text += " 완료"


def fake_batisay(audio, professor_id=""):
    return "커밋", False, "", [], {"name": "base", "version": "", "professor_id": professor_id}

calls = {"status": 0, "activate": 0, "capture": 0, "train": 0}

def status_fn(*, professor_id=""):
    calls["status"] += 1
    return {"professor_id": professor_id, "active_adapter": "v1", "training_busy": False}

def activate_fn(*, professor_id=""):
    calls["activate"] += 1
    return {"name": "prof_v1", "version": "v1", "professor_id": professor_id}

def capture_fn(*, session, segment, human_text):
    calls["capture"] += 1
    return {"status": "captured", "created": 1, "segment": segment, "text": human_text}

def train_fn(*, professor_id=""):
    calls["train"] += 1
    return {"ok": True, "status_code": 202, "accepted": True, "professor_id": professor_id}

prof = ProfessorLoRAEngine(
    status_fn=status_fn,
    activate_fn=activate_fn,
    capture_fn=capture_fn,
    train_fn=train_fn,
)
assert prof.adaptation_status(professor_id="prof-x")["professor_id"] == "prof-x"
assert prof.activate_adaptation(professor_id="prof-x")["version"] == "v1"
assert prof.capture_supervision(session=object(), segment=3, human_text="교정")["created"] == 1
assert prof.request_training(professor_id="prof-x")["accepted"] is True
assert calls == {"status": 1, "activate": 1, "capture": 1, "train": 1}

registry = build_default_registry(ROOT / "asr" / "profiles" / "default.yaml")
registry.register_engine(Qwen3ASREngine(FakeQwenRuntime(), sample_rate=16000))
registry.register_engine(BatiSayEngine(fake_batisay, sample_rate=16000))
registry.register_engine(prof)
snap = registry.snapshot()
assert snap["migration_phase"] == "delta_3_full_asr_adaptation", snap
assert snap["production_execution"] == "qwen_batisay_professor_adapters", snap
assert sorted(snap["loaded_plugin_engines"]) == ["batisay-ko-large", "professor-lora", "qwen3-asr-1.7b"], snap
adapt = [x for x in snap["engines"] if x["id"] == "professor-lora"][0]
assert adapt["execution_mode"] == "plugin", adapt
assert adapt["capabilities"]["trainer"] is True
assert adapt["capabilities"]["adaptation"] is True
print("PASS: Professor LoRA adapter actions + Delta-3 full registry self-test")
