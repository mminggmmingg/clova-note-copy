from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .base import ASREngine, ASREngineCapabilities
from .schema import CANONICAL_ASR_SCHEMA

REGISTRY_SCHEMA = "v8.2-delta-asr-registry-v1"
PROFILE_SCHEMA = "v8.2-delta-asr-profile-v1"


@dataclass(frozen=True)
class EngineDescriptor:
    id: str
    display_name: str
    kind: str
    capabilities: ASREngineCapabilities
    execution_mode: str = "plugin"
    implementation: str = ""
    base_engine: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "kind": self.kind,
            "capabilities": self.capabilities.to_dict(),
            "execution_mode": self.execution_mode,
            "implementation": self.implementation,
            "base_engine": self.base_engine,
            "notes": self.notes,
        }


class ASRRegistry:
    def __init__(self, *, profile: Dict[str, Any]):
        self._lock = threading.RLock()
        self._descriptors: Dict[str, EngineDescriptor] = {}
        self._engines: Dict[str, ASREngine] = {}
        self._profile = dict(profile)

    def register_descriptor(self, descriptor: EngineDescriptor) -> None:
        if not descriptor.id:
            raise ValueError("engine descriptor id is required")
        with self._lock:
            if descriptor.id in self._descriptors:
                raise ValueError(f"duplicate ASR engine id: {descriptor.id}")
            self._descriptors[descriptor.id] = descriptor

    def register_engine(self, engine: ASREngine) -> None:
        if not engine.id:
            raise ValueError("ASR engine id is required")
        with self._lock:
            existing = self._descriptors.get(engine.id)
            if existing is None:
                self._descriptors[engine.id] = EngineDescriptor(
                    id=engine.id,
                    display_name=engine.display_name or engine.id,
                    kind="transcriber",
                    capabilities=engine.capabilities(),
                    execution_mode="plugin",
                    implementation=f"{engine.__class__.__module__}.{engine.__class__.__name__}",
                )
            else:
                # Delta keeps the stable descriptor identity/role but marks the
                # concrete registered implementation as the production boundary.
                self._descriptors[engine.id] = EngineDescriptor(
                    id=existing.id,
                    display_name=engine.display_name or existing.display_name,
                    kind=existing.kind,
                    capabilities=engine.capabilities(),
                    execution_mode="plugin",
                    implementation=f"{engine.__class__.__module__}.{engine.__class__.__name__}",
                    base_engine=existing.base_engine,
                    notes=existing.notes,
                )
            self._engines[engine.id] = engine

    def get_engine(self, engine_id: str) -> Optional[ASREngine]:
        with self._lock:
            return self._engines.get(str(engine_id or ""))

    def descriptor(self, engine_id: str) -> Optional[EngineDescriptor]:
        with self._lock:
            return self._descriptors.get(str(engine_id or ""))

    def slot(self, slot_name: str) -> Dict[str, Any]:
        slots = self._profile.get("slots") or {}
        value = slots.get(str(slot_name or ""))
        return dict(value) if isinstance(value, dict) else {}

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            loaded = sorted(self._engines)
            batisay_live = "batisay-ko-large" in self._engines
            qwen_live = "qwen3-asr-1.7b" in self._engines
            professor_live = "professor-lora" in self._engines
            if qwen_live and batisay_live and professor_live:
                migration_phase = "delta_3_full_asr_adaptation"
                production_execution = "qwen_batisay_professor_adapters"
            elif qwen_live and batisay_live:
                migration_phase = "delta_2_qwen_batisay"
                production_execution = "qwen_batisay_adapters_professor_legacy_overlay"
            elif batisay_live:
                migration_phase = "delta_1_batisay"
                production_execution = "batisay_adapter_qwen_legacy"
            elif qwen_live:
                migration_phase = "delta_2_qwen_preview_only"
                production_execution = "qwen_adapter_only"
            else:
                migration_phase = "delta_registry_bootstrap"
                production_execution = "no_production_adapter_loaded"
            return {
                "schema": REGISTRY_SCHEMA,
                "canonical_result_schema": CANONICAL_ASR_SCHEMA,
                "profile": dict(self._profile),
                "engines": [
                    self._descriptors[key].to_dict()
                    for key in sorted(self._descriptors)
                ],
                "loaded_plugin_engines": loaded,
                "migration_phase": migration_phase,
                "production_execution": production_execution,
            }


def load_profile(path: Path) -> Dict[str, Any]:
    # The .yaml profile is intentionally JSON-compatible YAML so V8.2-delta
    # adds no PyYAML dependency to the stable runtime image.
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"unexpected ASR profile schema: {data.get('schema')!r}")
    slots = data.get("slots")
    if not isinstance(slots, dict):
        raise ValueError("ASR profile slots must be an object")
    for required in ("preview", "committed", "adaptation"):
        if not isinstance(slots.get(required), dict) or not slots[required].get("engine"):
            raise ValueError(f"missing ASR profile slot: {required}")
    return data


def build_default_registry(profile_path: Optional[Path] = None) -> ASRRegistry:
    if profile_path is None:
        profile_path = Path(__file__).resolve().parent / "profiles" / "default.yaml"
    profile = load_profile(Path(profile_path))
    registry = ASRRegistry(profile=profile)

    # Delta preserves the proven engine roles and registers concrete adapters
    # after their model/runtime resources are loaded by the backend.
    registry.register_descriptor(EngineDescriptor(
        id="qwen3-asr-1.7b",
        display_name="Qwen3-ASR 1.7B",
        kind="transcriber",
        execution_mode="legacy_direct",
        implementation="run_clova_v8_2_delta.py:qwen_asr",
        capabilities=ASREngineCapabilities(
            streaming=True,
            batch=False,
            word_timestamps=False,
            speaker_attribution=False,
            hotwords=False,
            adaptation=False,
            languages=("ko",),
        ),
        notes="Realtime preview slot; Delta-2 routes production streaming calls through Qwen3ASREngine.",
    ))
    registry.register_descriptor(EngineDescriptor(
        id="batisay-ko-large",
        display_name="BatiSay ko-large",
        kind="transcriber",
        execution_mode="legacy_direct",
        implementation="run_clova_v8_2_delta.py:_legacy_batisay_transcribe_impl",
        capabilities=ASREngineCapabilities(
            streaming=False,
            batch=True,
            word_timestamps=True,
            speaker_attribution=False,
            hotwords=False,
            adaptation=True,
            languages=("ko",),
        ),
        notes="Committed segment recognizer; Delta-1 routes production calls through BatiSayEngine.",
    ))
    registry.register_descriptor(EngineDescriptor(
        id="professor-lora",
        display_name="Professor LoRA",
        kind="adaptation",
        execution_mode="legacy_overlay",
        implementation="run_clova_v8_2_delta.py:ProfessorLoRA legacy core",
        base_engine="batisay-ko-large",
        capabilities=ASREngineCapabilities(
            streaming=False,
            batch=False,
            word_timestamps=False,
            speaker_attribution=False,
            hotwords=False,
            adaptation=True,
            trainer=True,
            languages=("ko",),
        ),
        notes="Human-correction adaptation slot; Delta-3 routes activation, supervision capture, status and training requests through ProfessorLoRAEngine; Human LOCK precedence unchanged.",
    ))

    known = {x["id"] for x in registry.snapshot()["engines"]}
    for slot_name, slot in (profile.get("slots") or {}).items():
        engine_id = str((slot or {}).get("engine") or "")
        if engine_id not in known:
            raise ValueError(f"profile slot {slot_name!r} references unknown engine {engine_id!r}")
    return registry
