from __future__ import annotations

from typing import Any, Callable, Dict

from ..base import ASREngine, ASREngineCapabilities, ASREngineError


class ProfessorLoRAEngine(ASREngine):
    """V8.2-delta adapter for professor-specific BatiSay LoRA adaptation.

    Delta-3 keeps the proven V7.9.3 training-data, trainer-process and PEFT
    implementation intact, but moves every production adaptation action behind
    the ASR registry boundary: adapter activation, Human-LOCK supervision capture,
    status introspection and training requests.

    The injected callbacks intentionally keep model/trainer ownership in the
    stable backend for V8.2. Delta changes dispatch boundaries, not learned-data
    semantics or the Human LOCK precedence rules.
    """

    id = "professor-lora"
    display_name = "Professor LoRA"

    def __init__(
        self,
        *,
        status_fn: Callable[..., Dict[str, Any]],
        activate_fn: Callable[..., Dict[str, Any]],
        capture_fn: Callable[..., Dict[str, Any]],
        train_fn: Callable[..., Dict[str, Any]],
    ):
        for name, fn in {
            "status_fn": status_fn,
            "activate_fn": activate_fn,
            "capture_fn": capture_fn,
            "train_fn": train_fn,
        }.items():
            if not callable(fn):
                raise TypeError(f"{name} must be callable")
        self._status_fn = status_fn
        self._activate_fn = activate_fn
        self._capture_fn = capture_fn
        self._train_fn = train_fn

    def capabilities(self) -> ASREngineCapabilities:
        return ASREngineCapabilities(
            streaming=False,
            batch=False,
            word_timestamps=False,
            speaker_attribution=False,
            hotwords=False,
            adaptation=True,
            trainer=True,
            languages=("ko",),
        )

    def adaptation_status(self, **options: Any) -> Dict[str, Any]:
        professor_id = str(options.get("professor_id") or "").strip()
        try:
            out = self._status_fn(professor_id=professor_id)
        except Exception as exc:
            raise ASREngineError(f"Professor LoRA status failed: {exc!r}") from exc
        return dict(out or {})

    def activate_adaptation(self, **options: Any) -> Dict[str, Any]:
        professor_id = str(options.get("professor_id") or "").strip()
        try:
            out = self._activate_fn(professor_id=professor_id)
        except Exception as exc:
            raise ASREngineError(f"Professor LoRA activation failed: {exc!r}") from exc
        return dict(out or {})

    def capture_supervision(self, **options: Any) -> Dict[str, Any]:
        session = options.get("session")
        segment = int(options.get("segment") or 0)
        human_text = str(options.get("human_text") or "")
        if session is None or segment <= 0 or not human_text.strip():
            raise ASREngineError("session, positive segment and human_text are required")
        try:
            out = self._capture_fn(session=session, segment=segment, human_text=human_text)
        except Exception as exc:
            raise ASREngineError(f"Professor LoRA supervision capture failed: {exc!r}") from exc
        return dict(out or {})

    def request_training(self, **options: Any) -> Dict[str, Any]:
        professor_id = str(options.get("professor_id") or "").strip()
        if not professor_id:
            raise ASREngineError("professor_id is required")
        try:
            out = self._train_fn(professor_id=professor_id)
        except Exception as exc:
            raise ASREngineError(f"Professor LoRA training request failed: {exc!r}") from exc
        return dict(out or {})
