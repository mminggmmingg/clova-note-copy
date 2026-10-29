#!/usr/bin/env python3
import json, sys
from pathlib import Path

ROOT = Path.home() / "clova-note-copy" / "data" / "sessions"
SCHEMA = "v8.1-alpha.1-annotation-events-v2"
LEGACY_SCHEMA = "v8.1-alpha-annotation-events-v1"
ACCEPTED = {SCHEMA, LEGACY_SCHEMA}

def pick_session():
    if len(sys.argv) > 1: return ROOT / sys.argv[1]
    sessions=[p for p in ROOT.iterdir() if p.is_dir()] if ROOT.is_dir() else []
    sessions.sort(key=lambda p:p.stat().st_mtime, reverse=True)
    for p in sessions:
        if (p/'annotation_events.jsonl').is_file(): return p
    return sessions[0] if sessions else None

def read_events(path):
    out=[]
    if not path.is_file(): return out
    for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: item=json.loads(line)
        except Exception as e: raise SystemExit(f"FAIL : invalid JSON line {n}: {e}")
        out.append(item)
    return out

def finite_nonneg_or_none(value, label):
    if value is None: return None
    try: v=float(value)
    except Exception: raise SystemExit(f"FAIL : invalid {label}: {value!r}")
    if v < 0: raise SystemExit(f"FAIL : negative {label}: {v}")
    return v

def main():
    session=pick_session()
    if session is None: raise SystemExit('FAIL : no sessions')
    meta={}
    mp=session/'session.json'
    if mp.is_file():
        try: meta=json.loads(mp.read_text(encoding='utf-8'))
        except Exception: pass
    events=read_events(session/'annotation_events.jsonl')
    active={}; erased=set(); adds=erases=page_only=0; last_seq=0
    for i,e in enumerate(events,1):
        schema=e.get('annotation_schema')
        if schema not in ACCEPTED: raise SystemExit(f"FAIL : event {i} schema mismatch: {schema}")
        seq=int(e.get('seq') or 0)
        if seq <= last_seq: raise SystemExit(f"FAIL : non-increasing seq at event {i}")
        last_seq=seq
        kind=e.get('type')
        if kind=='annotation_add':
            adds+=1
            aid=str(e.get('annotation_id') or '')
            if not aid.startswith('ann_'): raise SystemExit(f"FAIL : bad annotation_id at event {i}")
            if e.get('tool') not in {'pen','highlighter'}: raise SystemExit(f"FAIL : bad tool at event {i}")
            pts=e.get('points')
            if not isinstance(pts,list) or not pts: raise SystemExit(f"FAIL : empty points at event {i}")
            for p in pts:
                x=float(p.get('x')); y=float(p.get('y'))
                if not (0<=x<=1 and 0<=y<=1): raise SystemExit(f"FAIL : non-normalized point at event {i}")
            if schema == SCHEMA:
                anchor=e.get('anchor_type')
                if anchor not in {'live_recording','playback','page_only'}: raise SystemExit(f"FAIL : bad anchor_type at event {i}: {anchor}")
                t=finite_nonneg_or_none(e.get('lecture_time'), f'lecture_time at event {i}')
                if anchor=='page_only':
                    page_only += 1
                    if t is not None: raise SystemExit(f"FAIL : page_only event {i} has lecture_time")
                    if e.get('created_during') != 'page_only': raise SystemExit(f"FAIL : page_only created_during mismatch at event {i}")
                else:
                    if t is None: raise SystemExit(f"FAIL : anchored event {i} missing lecture_time")
                    expected='live' if anchor=='live_recording' else 'review'
                    if e.get('created_during') != expected: raise SystemExit(f"FAIL : created_during mismatch at event {i}")
            else:
                finite_nonneg_or_none(e.get('lecture_time'), f'legacy lecture_time at event {i}')
            if not e.get('created_at'): raise SystemExit(f"FAIL : missing created_at at event {i}")
            active[aid]=e; erased.discard(aid)
        elif kind=='annotation_erase':
            erases+=1
            target=str(e.get('target_annotation_id') or '')
            if target not in active: raise SystemExit(f"FAIL : erase target not active at event {i}: {target}")
            active.pop(target,None); erased.add(target)
            if e.get('soft_erase') is not True: raise SystemExit(f"FAIL : erase is not soft at event {i}")
            if schema == SCHEMA:
                anchor=e.get('operation_anchor_type')
                if anchor not in {'live_recording','playback','page_only'}: raise SystemExit(f"FAIL : bad erase operation_anchor_type at event {i}: {anchor}")
                t=finite_nonneg_or_none(e.get('operation_lecture_time'), f'operation_lecture_time at event {i}')
                if anchor=='page_only' and t is not None: raise SystemExit(f"FAIL : page_only erase {i} has operation_lecture_time")
                if anchor!='page_only' and t is None: raise SystemExit(f"FAIL : anchored erase {i} missing operation_lecture_time")
        else:
            raise SystemExit(f"FAIL : unknown type at event {i}: {kind}")
    print(f"Session : {session.name}")
    print(f"Schema  : {SCHEMA} (legacy v1 accepted)")
    print(f"Events  : {len(events)} · add={adds} erase={erases}")
    print(f"Page-only adds : {page_only}")
    print(f"Active  : {len(active)}")
    print(f"Soft erased : {len(erased)}")
    if meta.get('annotation_schema') and meta.get('annotation_schema') not in ACCEPTED:
        raise SystemExit('FAIL : session meta annotation_schema mismatch')
    print('RESULT  : PASS')

if __name__=='__main__': main()
