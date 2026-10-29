from __future__ import annotations

from typing import Any, Callable, Dict, Iterable

from ..base import ASREngine, ASREngineCapabilities, ASREngineError
from ..schema import canonical_asr_result, validate_canonical_asr_result


class BatiSayEngine(ASREngine):
    """V8.2-delta adapter for the proven Local Clova BatiSay execution core.

    Delta-1 deliberately injects the already-validated backend callable instead
    of moving model ownership/Professor-LoRA switching at the same time. This
    makes the registry the production call boundary while preserving the exact
    BatiSay model, retry, repetition-rejection and adapter-switch semantics from
    the stable V8.2-gamma baseline.
    """

    id = "batisay-ko-large"
    display_name = "BatiSay ko-large"

    def __init__(self, transcribe_fn: Callable[..., Any], *, sample_rate: int = 16000):
        if not callable(transcribe_fn):
            raise TypeError("transcribe_fn must be callable")
        self._transcribe_fn = transcribe_fn
        self.sample_rate = int(sample_rate)

    def capabilities(self) -> ASREngineCapabilities:
        return ASREngineCapabilities(
            streaming=False,
            batch=True,
            word_timestamps=True,
            speaker_attribution=False,
            hotwords=False,
            adaptation=True,
            trainer=False,
            languages=("ko",),
        )

    @staticmethod
    def _canonical_words(chunks: Any) -> list[Dict[str, Any]]:
        words: list[Dict[str, Any]] = []
        if not isinstance(chunks, (list, tuple)):
            return words
        for item in chunks:
            if not isinstance(item, dict):
                continue
            ts = item.get("timestamp")
            if not isinstance(ts, (list, tuple)) or len(ts) != 2:
                continue
            try:
                start = max(0.0, float(ts[0] if ts[0] is not None else 0.0))
                end = max(start, float(ts[1] if ts[1] is not None else start))
            except Exception:
                continue
            words.append({
                "text": str(item.get("text") or ""),
                "start": start,
                "end": end,
                "confidence": item.get("confidence"),
            })
        return words

    def transcribe(self, audio: Any, **options: Any) -> Dict[str, Any]:
        professor_id = str(options.get("professor_id") or "")
        sample_rate = int(options.get("sample_rate") or self.sample_rate)
        if sample_rate <= 0:
            raise ASREngineError("sample_rate must be positive")

        try:
            text, rejected, reject_reason, chunks, adapter = self._transcribe_fn(
                audio,
                professor_id=professor_id,
            )
        except Exception as exc:
            raise ASREngineError(f"BatiSay backend failed: {exc!r}") from exc

        try:
            duration = len(audio) / float(sample_rate) if audio is not None else 0.0
        except Exception:
            duration = 0.0

        result = canonical_asr_result(
            text=text,
            start=0.0,
            end=max(0.0, duration),
            words=self._canonical_words(chunks),
            language="ko",
            engine=self.id,
            final=True,
            metadata={
                # Keep the exact legacy timestamp payload for Delta-1 so the
                # word_audio_map/training path receives byte-for-byte equivalent
                # semantic data at the bridge boundary.
                "chunks": list(chunks or []),
                "rejected": bool(rejected),
                "reject_reason": str(reject_reason or ""),
                "adapter": dict(adapter or {}),
                "professor_id": professor_id,
                "execution": "delta_adapter",
            },
        )
        errors = validate_canonical_asr_result(result)
        if errors:
            raise ASREngineError("invalid canonical BatiSay result: " + "; ".join(errors))
        return result
