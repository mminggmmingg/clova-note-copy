"""Local Clova replaceable ASR layer for V8.2-delta.

Delta-2 routes Qwen realtime preview and committed BatiSay production execution
through registry/engine adapters while keeping stable gamma audio/VAD/segmentation frozen.
"""

from .base import ASREngine, ASREngineCapabilities, ASREngineError
from .registry import ASRRegistry, build_default_registry
from .schema import CANONICAL_ASR_SCHEMA, canonical_asr_result, validate_canonical_asr_result

__all__ = [
    "ASREngine",
    "ASREngineCapabilities",
    "ASREngineError",
    "ASRRegistry",
    "build_default_registry",
    "CANONICAL_ASR_SCHEMA",
    "canonical_asr_result",
    "validate_canonical_asr_result",
]
