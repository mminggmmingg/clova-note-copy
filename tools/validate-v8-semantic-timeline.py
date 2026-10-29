#!/usr/bin/env python3
import json
import math
import sys
from pathlib import Path
from pdf_semantic_timeline_v8 import build_payload, classify_dwell, SCHEMA

ROOT = Path.home() / "clova-note-copy" / "data" / "sessions"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_events(path):
    out=[]
    if path.is_file():
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
            if not raw.strip(): continue
            try: item=json.loads(raw)
            except Exception as e: raise AssertionError(f"invalid JSON at line {lineno}: {e}")
            if isinstance(item,dict): out.append(item)
    return out


def choose_session():
    if len(sys.argv) > 1:
        p=ROOT/sys.argv[1]
        if not (p/"session.json").is_file(): raise SystemExit(f"Session not found: {p}")
        return p
    sessions=[p for p in ROOT.iterdir() if p.is_dir() and (p/"session.json").is_file()] if ROOT.is_dir() else []
    if not sessions: raise SystemExit(f"No sessions under {ROOT}")
    return max(sessions,key=lambda p:p.stat().st_mtime)


def main():
    sdir=choose_session(); meta=load_json(sdir/"session.json",{}); events=load_events(sdir/"pdf_events.jsonl")
    path=sdir/"pdf_semantic_timeline.json"
    if not path.is_file():
        raise SystemExit(f"Missing {path}. Stop the session once or run build-v8-semantic-timeline.py")
    actual=load_json(path,{})
    expected=build_payload(meta,events,generated_at=actual.get("generated_at"))
    errors=[]
    if actual.get("schema") != SCHEMA: errors.append(f"schema={actual.get('schema')!r}")
    if actual.get("source",{}).get("llm_used") is not False: errors.append("llm_used must be false")
    ae=actual.get("entries") or []; ee=expected.get("entries") or []
    if len(ae)!=len(ee): errors.append(f"entry count {len(ae)} != expected {len(ee)}")
    for i,(a,e) in enumerate(zip(ae,ee),1):
        for key in ("pdf_id","page","source_seq","semantic_weight"):
            if a.get(key)!=e.get(key): errors.append(f"#{i} {key}: {a.get(key)!r} != {e.get(key)!r}")
        for key in ("start","end","dwell"):
            try:
                if not math.isclose(float(a.get(key)),float(e.get(key)),abs_tol=1e-6): errors.append(f"#{i} {key}: {a.get(key)} != {e.get(key)}")
            except Exception: errors.append(f"#{i} invalid {key}")
        try:
            if a.get("semantic_weight") != classify_dwell(a.get("dwell")): errors.append(f"#{i} classification mismatch")
        except Exception: pass
    print(f"Session : {sdir.name}")
    print(f"Schema  : {actual.get('schema') or '(none)'}")
    print(f"Clock   : {float(actual.get('recording_time_sec') or 0):.3f}s")
    print(f"Entries : {len(ae)}")
    print(f"Counts  : {actual.get('summary',{}).get('counts',{})}")
    for x in ae[-12:]:
        print(f"  #{int(x.get('source_seq') or 0):03d} {float(x.get('start') or 0):8.3f}-{float(x.get('end') or 0):8.3f}s  dwell={float(x.get('dwell') or 0):6.3f}s  {str(x.get('semantic_weight') or ''):7s}  {x.get('ref','')}")
    print("LLM     : NOT USED")
    if errors:
        print("RESULT  : FAIL")
        for e in errors: print(" -",e)
        raise SystemExit(1)
    print("RESULT  : PASS")

if __name__=="__main__": main()
