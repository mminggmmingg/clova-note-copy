#!/usr/bin/env python3
import json
from pathlib import Path

SR = 16000
ROOT = Path.home() / "clova-note-copy" / "data" / "sessions"
VALID = {"pdf_open", "pdf_page", "pdf_close"}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_events(path):
    events = []
    if not path.is_file():
        return events
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except Exception as e:
            raise AssertionError(f"invalid JSON at line {lineno}: {e}")
        events.append(item)
    return events


def main():
    if not ROOT.is_dir():
        raise SystemExit(f"No sessions under {ROOT}")
    sessions = [p for p in ROOT.iterdir() if p.is_dir() and (p / "session.json").is_file()]
    if not sessions:
        raise SystemExit(f"No sessions under {ROOT}")
    sdir = max(sessions, key=lambda p: p.stat().st_mtime)
    meta = load_json(sdir / "session.json", {})
    events = load_events(sdir / "pdf_events.jsonl")
    rec_sec = float(meta.get("recording_time_sec") or 0.0)
    pdf_ids = {str(x) for x in (meta.get("pdf_ids") or [])}

    errors = []
    last_seq = 0
    last_time = -1.0
    state = {"state": "no_pdf", "pdf_id": "", "page": 1}

    for i, ev in enumerate(events, 1):
        kind = str(ev.get("type") or "")
        if kind not in VALID:
            errors.append(f"#{i}: invalid type {kind!r}")
            continue
        try:
            seq = int(ev.get("seq"))
        except Exception:
            seq = -1
        if seq != last_seq + 1:
            errors.append(f"#{i}: seq {seq} after {last_seq}")
        last_seq = max(last_seq, seq)
        try:
            t = float(ev.get("time"))
        except Exception:
            t = -1.0
        if t + 1e-9 < last_time:
            errors.append(f"#{i}: time moved backwards {t:.6f} < {last_time:.6f}")
        if t < -1e-9 or t > rec_sec + 0.30:
            errors.append(f"#{i}: time {t:.3f}s outside recording 0..{rec_sec:.3f}s")
        last_time = max(last_time, t)
        sample = ev.get("recording_sample")
        if sample is not None:
            try:
                sample = int(sample)
                if abs(sample / SR - t) > 1.0 / SR + 1e-6:
                    errors.append(f"#{i}: sample/time mismatch {sample} vs {t:.6f}s")
            except Exception:
                errors.append(f"#{i}: invalid recording_sample")
        if str(ev.get("source") or "") not in {"manual_recording_event", "recording_resume_snapshot"}:
            errors.append(f"#{i}: unexpected source")

        if kind == "pdf_close":
            if state["state"] != "pdf":
                errors.append(f"#{i}: pdf_close while already NO_PDF")
            state = {"state": "no_pdf", "pdf_id": "", "page": 1}
            continue

        pid = str(ev.get("pdf_id") or "")
        try:
            page = max(1, int(ev.get("page") or 1))
        except Exception:
            errors.append(f"#{i}: invalid page")
            page = 1
        if pid not in pdf_ids:
            errors.append(f"#{i}: pdf_id not attached to session: {pid}")
        if kind == "pdf_page":
            if state["state"] != "pdf" or state["pdf_id"] != pid:
                errors.append(f"#{i}: pdf_page without same active PDF")
        state = {"state": "pdf", "pdf_id": pid, "page": page}

    print(f"Session : {sdir.name}")
    print(f"Schema  : {meta.get('pdf_timeline_schema') or '(none)'}")
    print(f"Clock   : {rec_sec:.3f}s")
    print(f"Events  : {len(events)}")
    for ev in events[-12:]:
        ref = ev.get("ref") or ""
        print(f"  #{int(ev.get('seq') or 0):03d} {float(ev.get('time') or 0):8.3f}s  {str(ev.get('type') or ''):9s} {ref}")
    print(f"State   : {state}")
    if errors:
        print("RESULT  : FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print("RESULT  : PASS")


if __name__ == "__main__":
    main()
