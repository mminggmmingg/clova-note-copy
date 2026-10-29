from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

CANONICAL_ASR_SCHEMA = "local-clova-asr-result-v1"


def _finite_number(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return float(default)
    if value != value or value in (float("inf"), float("-inf")):
        return float(default)
    return value


def _normalize_words(words: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(words, (list, tuple)):
        return out
    for item in words:
        if not isinstance(item, dict):
            continue
        start = max(0.0, _finite_number(item.get("start"), 0.0))
        end = max(start, _finite_number(item.get("end"), start))
        out.append({
            "text": str(item.get("text") or ""),
            "start": round(start, 6),
            "end": round(end, 6),
            "confidence": item.get("confidence"),
        })
    return out


def canonical_asr_result(
    *,
    text: Any = "",
    start: Any = 0.0,
    end: Any = 0.0,
    words: Any = None,
    speaker: Any = "",
    language: Any = "",
    confidence: Any = None,
    engine: Any = "",
    final: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start_f = max(0.0, _finite_number(start, 0.0))
    end_f = max(start_f, _finite_number(end, start_f))
    return {
        "schema": CANONICAL_ASR_SCHEMA,
        "text": str(text or "").strip(),
        "start": round(start_f, 6),
        "end": round(end_f, 6),
        "words": _normalize_words(words),
        "speaker": str(speaker or ""),
        "language": str(language or ""),
        "confidence": confidence,
        "engine": str(engine or ""),
        "final": bool(final),
        "metadata": dict(metadata or {}),
    }


def validate_canonical_asr_result(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["result is not an object"]
    if value.get("schema") != CANONICAL_ASR_SCHEMA:
        errors.append("schema mismatch")
    if not isinstance(value.get("text"), str):
        errors.append("text must be a string")
    if not isinstance(value.get("engine"), str) or not value.get("engine"):
        errors.append("engine must be a non-empty string")
    try:
        start = float(value.get("start"))
        end = float(value.get("end"))
        if start < 0 or end < start:
            errors.append("invalid start/end")
    except Exception:
        errors.append("start/end must be numeric")
    if not isinstance(value.get("words"), list):
        errors.append("words must be a list")
    if not isinstance(value.get("metadata"), dict):
        errors.append("metadata must be an object")
    return errors
