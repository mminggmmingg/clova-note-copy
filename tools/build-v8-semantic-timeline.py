#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from pdf_semantic_timeline_v8 import build_payload

ROOT = Path.home() / "clova-note-copy" / "data" / "sessions"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_events(path):
    out = []
    if not path.is_file():
        return out
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except Exception as e:
            raise SystemExit(f"invalid JSON at {path}:{lineno}: {e}")
        if isinstance(item, dict):
            out.append(item)
    return out


def choose_session():
    if len(sys.argv) > 1:
        p = ROOT / sys.argv[1]
        if not (p / "session.json").is_file():
            raise SystemExit(f"Session not found: {p}")
        return p
    sessions = [p for p in ROOT.iterdir() if p.is_dir() and (p / "session.json").is_file()] if ROOT.is_dir() else []
    if not sessions:
        raise SystemExit(f"No sessions under {ROOT}")
    return max(sessions, key=lambda p: p.stat().st_mtime)


def main():
    sdir = choose_session()
    meta_path = sdir / "session.json"
    meta = load_json(meta_path, {})
    events = load_events(sdir / "pdf_events.jsonl")
    payload = build_payload(meta, events)
    out = sdir / "pdf_semantic_timeline.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta["pdf_semantic_timeline_schema"] = payload["schema"]
    meta["pdf_semantic_timeline_file"] = out.name
    meta["pdf_semantic_timeline_dirty"] = False
    meta["pdf_semantic_timeline_summary"] = payload["summary"]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Session : {sdir.name}")
    print(f"Output  : {out}")
    print(f"Entries : {len(payload['entries'])}")
    print(f"Counts  : {payload['summary']['counts']}")
    print("LLM     : NOT USED")
    print("RESULT  : PASS")

if __name__ == "__main__":
    main()
