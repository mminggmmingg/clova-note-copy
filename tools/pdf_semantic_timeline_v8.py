#!/usr/bin/env python3
"""Pure V8.0-eta PDF dwell/semantic timeline derivation. No LLM usage."""
from __future__ import annotations

from datetime import datetime

SCHEMA = "v8.0-eta-pdf-semantic-timeline-v1"
SOURCE_SCHEMA = "v8.0-gamma-pdf-events-v1"
IGNORE_LT = 1.5
WEAK_LT = 4.0
INCLUDE_LT = 10.0
VALID = {"pdf_open", "pdf_page", "pdf_close"}


def classify_dwell(dwell):
    d = max(0.0, float(dwell or 0.0))
    if d < IGNORE_LT:
        return "ignore"
    if d < WEAK_LT:
        return "weak"
    if d < INCLUDE_LT:
        return "include"
    return "strong"


def build_payload(meta, raw_events, *, generated_at=None):
    meta = meta if isinstance(meta, dict) else {}
    ordered = []
    for pos, item in enumerate(raw_events or []):
        if not isinstance(item, dict) or str(item.get("type") or "") not in VALID:
            continue
        try:
            t = max(0.0, float(item.get("time") or 0.0))
        except Exception:
            t = 0.0
        try:
            seq = int(item.get("seq") or (pos + 1))
        except Exception:
            seq = pos + 1
        ordered.append((t, seq, pos, item))
    ordered.sort(key=lambda x: (x[0], x[1], x[2]))

    try:
        recording_end = max(0.0, float(meta.get("recording_time_sec") or 0.0))
    except Exception:
        recording_end = 0.0
    if ordered:
        recording_end = max(recording_end, ordered[-1][0])

    entries = []
    for idx, (start, seq, _pos, item) in enumerate(ordered):
        kind = str(item.get("type") or "")
        if kind not in {"pdf_open", "pdf_page"}:
            continue
        pdf_id = str(item.get("pdf_id") or "").strip()
        if not pdf_id:
            continue
        try:
            page = max(1, int(item.get("page") or 1))
        except Exception:
            page = 1
        end = recording_end
        if idx + 1 < len(ordered):
            end = max(start, float(ordered[idx + 1][0]))
        dwell = max(0.0, end - start)
        entries.append({
            "pdf_id": pdf_id,
            "page": page,
            "ref": f"clova://pdf/{pdf_id}/page/{page}",
            "start": round(start, 6),
            "end": round(end, 6),
            "dwell": round(dwell, 6),
            "semantic_weight": classify_dwell(dwell),
            "source_seq": seq,
        })

    counts = {"ignore": 0, "weak": 0, "include": 0, "strong": 0}
    for entry in entries:
        counts[entry["semantic_weight"]] += 1

    return {
        "schema": SCHEMA,
        "generated_at": generated_at or datetime.now().astimezone().isoformat(),
        "source": {
            "pdf_timeline_schema": str(meta.get("pdf_timeline_schema") or SOURCE_SCHEMA),
            "pdf_events_file": "pdf_events.jsonl",
            "event_count": len([x for x in (raw_events or []) if isinstance(x, dict) and str(x.get("type") or "") in VALID]),
            "llm_used": False,
        },
        "recording_time_sec": round(recording_end, 6),
        "recording_time_exact": bool(meta.get("recording_time_exact", False)),
        "recording_time_basis": str(meta.get("recording_time_basis") or "legacy-cumulative-duration"),
        "thresholds_sec": {
            "ignore_lt": IGNORE_LT,
            "weak_range": [IGNORE_LT, WEAK_LT],
            "include_range": [WEAK_LT, INCLUDE_LT],
            "strong_gte": INCLUDE_LT,
        },
        "classification_rule": "[0,1.5)=ignore; [1.5,4)=weak; [4,10)=include; [10,+inf)=strong",
        "entries": entries,
        "summary": {
            "entry_count": len(entries),
            "counts": counts,
            "semantic_entry_count": counts["weak"] + counts["include"] + counts["strong"],
            "included_or_strong_count": counts["include"] + counts["strong"],
        },
    }
