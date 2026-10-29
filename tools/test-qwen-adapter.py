#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asr.engines.batisay import BatiSayEngine
from asr.engines.qwen3_asr import Qwen3ASREngine, QwenStreamingHandle
from asr.registry import build_default_registry
from asr.schema import validate_canonical_asr_result


class FakeState:
    def __init__(self):
        self.text = ""


class FakeQwenRuntime:
    def __init__(self):
        self.started = []
        self.pushes = 0
        self.finishes = 0

    def init_streaming_state(self, **kwargs):
        self.started.append(dict(kwargs))
        return FakeState()

    def streaming_transcribe(self, audio, state):
        self.pushes += 1
        state.text = f"미리보기 {self.pushes}"

    def finish_streaming_transcribe(self, state):
        self.finishes += 1
        state.text = state.text + " 완료"


def fake_batisay(audio, professor_id=""):
    return "커밋", False, "", [], {"name": "base", "version": "", "professor_id": professor_id}


runtime = FakeQwenRuntime()
engine = Qwen3ASREngine(runtime, sample_rate=16000)
stream = engine.start_stream(
    context="",
    language="Korean",
    unfixed_chunk_num=4,
    unfixed_token_num=5,
    chunk_size_sec=1.0,
)
assert isinstance(stream, QwenStreamingHandle)
assert runtime.started[0]["language"] == "Korean"

partial = engine.push_audio(stream, [0.0] * 1600)
assert not validate_canonical_asr_result(partial), partial
assert partial["final"] is False
assert partial["text"] == "미리보기 1"
assert partial["metadata"]["processed_samples"] == 1600
assert stream.text == "미리보기 1"

final = engine.finish_stream(stream)
assert not validate_canonical_asr_result(final), final
assert final["final"] is True
assert final["text"] == "미리보기 1 완료"
assert runtime.finishes == 1

registry = build_default_registry(ROOT / "asr" / "profiles" / "default.yaml")
registry.register_engine(engine)
registry.register_engine(BatiSayEngine(fake_batisay, sample_rate=16000))
snap = registry.snapshot()
assert snap["migration_phase"] == "delta_2_qwen_batisay", snap
assert snap["production_execution"] == "qwen_batisay_adapters_professor_legacy_overlay", snap
assert "qwen3-asr-1.7b" in snap["loaded_plugin_engines"], snap
assert "batisay-ko-large" in snap["loaded_plugin_engines"], snap
preview = [x for x in snap["engines"] if x["id"] == "qwen3-asr-1.7b"][0]
assert preview["execution_mode"] == "plugin", preview
print("PASS: Qwen3-ASR streaming adapter + Delta-2 combined registry self-test")
