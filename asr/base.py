from __future__ import annotations

from abc import ABC
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional


class ASREngineError(RuntimeError):
    """Base error for replaceable Local Clova ASR engines."""


@dataclass(frozen=True)
class ASREngineCapabilities:
    streaming: bool = False
    batch: bool = False
    word_timestamps: bool = False
    speaker_attribution: bool = False
    hotwords: bool = False
    adaptation: bool = False
    trainer: bool = False
    languages: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["languages"] = list(self.languages)
        return out


class ASREngine(ABC):
    """Stable ASR contract for Local Clova.

    Engines may implement only the methods their capability manifest advertises.
    V8.2-gamma establishes this interface without rerouting the production path;
    V8.2-delta supplies adapters for the current Qwen/BatiSay stack.
    """

    id: str = ""
    display_name: str = ""

    def capabilities(self) -> ASREngineCapabilities:
        raise NotImplementedError

    def load(self) -> None:
        """Load model/runtime resources. Must be idempotent when practical."""
        return None

    def unload(self) -> None:
        """Release model/runtime resources."""
        return None

    def transcribe(self, audio: Any, **options: Any) -> Dict[str, Any]:
        raise ASREngineError(f"engine {self.id!r} does not implement batch transcription")

    def start_stream(self, **options: Any) -> Any:
        raise ASREngineError(f"engine {self.id!r} does not implement streaming")

    def push_audio(self, stream: Any, audio: Any) -> Optional[Dict[str, Any]]:
        raise ASREngineError(f"engine {self.id!r} does not implement streaming")

    def finish_stream(self, stream: Any) -> Dict[str, Any]:
        raise ASREngineError(f"engine {self.id!r} does not implement streaming")

    def adaptation_status(self, **options: Any) -> Dict[str, Any]:
        raise ASREngineError(f"engine {self.id!r} does not implement adaptation status")

    def activate_adaptation(self, **options: Any) -> Dict[str, Any]:
        raise ASREngineError(f"engine {self.id!r} does not implement adaptation activation")

    def capture_supervision(self, **options: Any) -> Dict[str, Any]:
        raise ASREngineError(f"engine {self.id!r} does not implement supervision capture")

    def request_training(self, **options: Any) -> Dict[str, Any]:
        raise ASREngineError(f"engine {self.id!r} does not implement training")
