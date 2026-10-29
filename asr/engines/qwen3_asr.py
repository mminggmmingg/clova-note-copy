from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ..base import ASREngine, ASREngineCapabilities, ASREngineError
from ..schema import canonical_asr_result, validate_canonical_asr_result


@dataclass
class QwenStreamingHandle:
    """Adapter-owned wrapper around Qwen3-ASR's native streaming state."""

    state: Any
    sample_rate: int = 16000
    processed_samples: int = 0

    @property
    def text(self) -> str:
        return str(getattr(self.state, "text", "") or "")


class Qwen3ASREngine(ASREngine):
    """V8.2-delta adapter for the proven Qwen3-ASR streaming runtime.

    Delta-2 intentionally keeps the already-loaded Qwen model object and its
    exact streaming-state parameters. The adapter becomes the production call
    boundary only; sanitization, Qwen-only state splitting, segmentation and
    all audio timing semantics remain in the frozen Local Clova backend.
    """

    id = "qwen3-asr-1.7b"
    display_name = "Qwen3-ASR 1.7B"

    def __init__(self, model: Any, *, sample_rate: int = 16000):
        required = (
            "init_streaming_state",
            "streaming_transcribe",
            "finish_streaming_transcribe",
        )
        missing = [name for name in required if not callable(getattr(model, name, None))]
        if missing:
            raise TypeError("Qwen3-ASR runtime missing methods: " + ", ".join(missing))
        self.model = model
        self.sample_rate = int(sample_rate)
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

    def capabilities(self) -> ASREngineCapabilities:
        return ASREngineCapabilities(
            streaming=True,
            batch=False,
            word_timestamps=False,
            speaker_attribution=False,
            hotwords=False,
            adaptation=False,
            trainer=False,
            languages=("ko",),
        )

    def start_stream(self, **options: Any) -> QwenStreamingHandle:
        try:
            state = self.model.init_streaming_state(
                context=str(options.get("context") or ""),
                language=str(options.get("language") or "Korean"),
                unfixed_chunk_num=int(options.get("unfixed_chunk_num", 4)),
                unfixed_token_num=int(options.get("unfixed_token_num", 5)),
                chunk_size_sec=float(options.get("chunk_size_sec", 1.0)),
            )
        except Exception as exc:
            raise ASREngineError(f"Qwen3-ASR start_stream failed: {exc!r}") from exc
        return QwenStreamingHandle(state=state, sample_rate=self.sample_rate)

    def _result(self, stream: QwenStreamingHandle, *, final: bool) -> Dict[str, Any]:
        duration = max(0.0, stream.processed_samples / float(stream.sample_rate))
        result = canonical_asr_result(
            text=stream.text,
            start=0.0,
            end=duration,
            words=[],
            language="ko",
            engine=self.id,
            final=final,
            metadata={
                "execution": "delta_adapter",
                "streaming": True,
                "processed_samples": int(stream.processed_samples),
            },
        )
        errors = validate_canonical_asr_result(result)
        if errors:
            raise ASREngineError("invalid canonical Qwen3-ASR result: " + "; ".join(errors))
        return result

    def push_audio(self, stream: Any, audio: Any) -> Dict[str, Any]:
        if not isinstance(stream, QwenStreamingHandle):
            raise ASREngineError("invalid Qwen3-ASR stream handle")
        try:
            self.model.streaming_transcribe(audio, stream.state)
            stream.processed_samples += max(0, int(len(audio)))
        except Exception as exc:
            raise ASREngineError(f"Qwen3-ASR push_audio failed: {exc!r}") from exc
        return self._result(stream, final=False)

    def finish_stream(self, stream: Any) -> Dict[str, Any]:
        if not isinstance(stream, QwenStreamingHandle):
            raise ASREngineError("invalid Qwen3-ASR stream handle")
        try:
            self.model.finish_streaming_transcribe(stream.state)
        except Exception as exc:
            raise ASREngineError(f"Qwen3-ASR finish_stream failed: {exc!r}") from exc
        return self._result(stream, final=True)
