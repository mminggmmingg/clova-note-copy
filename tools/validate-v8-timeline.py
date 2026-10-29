#!/usr/bin/env python3
import json, sys
from pathlib import Path

def read_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default

def records(path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            obj=json.loads(line)
            if isinstance(obj,dict): out.append(obj)
        except Exception: pass
    return out

def choose_root(arg=None):
    if arg:
        p=Path(arg).expanduser().resolve()
        if (p/'session.json').exists(): return p
        raise SystemExit(f'Not a session directory: {p}')
    data=Path.home()/'clova-note-copy'/'data'/'sessions'
    roots=[p for p in data.iterdir() if p.is_dir() and (p/'session.json').exists()]
    if not roots: raise SystemExit(f'No sessions under {data}')
    return max(roots,key=lambda p:p.stat().st_mtime)

def main():
    root=choose_root(sys.argv[1] if len(sys.argv)>1 else None)
    meta=read_json(root/'session.json',{})
    recs=records(root/'transcript.jsonl')
    schema=str(meta.get('timeline_schema') or '')
    exact=bool(meta.get('recording_time_exact',False))
    clock=float(meta.get('recording_time_sec') or 0.0)
    errors=[]; warnings=[]; prev_start=-1.0
    print(f'Session : {root.name}')
    print(f'Schema  : {schema or "missing"}')
    print(f'Clock   : {clock:.3f}s')
    print(f'Exact   : {exact}')
    print(f'Basis   : {meta.get("recording_time_basis") or "missing"}')
    print(f'SEGs    : {len(recs)}')
    if exact and not schema.startswith('v8.0-alpha'):
        errors.append('exact session does not advertise V8 timeline schema')
    for n,r in enumerate(recs,1):
        seg=int(r.get('segment') or n)
        a=r.get('recording_start'); b=r.get('recording_end')
        dur=float(r.get('duration_sec') or 0.0)
        if a is None or b is None:
            if exact: errors.append(f'SEG {seg}: missing recording_start/end')
            else: warnings.append(f'SEG {seg}: legacy/no exact source span')
            continue
        a=float(a); b=float(b)
        if a < -1e-6 or b + 1e-6 < a: errors.append(f'SEG {seg}: invalid span {a}-{b}')
        if b > clock + 0.050: errors.append(f'SEG {seg}: end {b:.3f}s exceeds session clock {clock:.3f}s')
        if prev_start >= 0 and a + 1e-6 < prev_start: errors.append(f'SEG {seg}: start moved backward {prev_start:.3f}->{a:.3f}')
        prev_start=max(prev_start,a)
        if abs((b-a)-dur) > 0.020: errors.append(f'SEG {seg}: source span {(b-a):.3f}s != WAV duration {dur:.3f}s')
    deleted=read_json(root/'deleted_segments.json',{'segments':{}}).get('segments',{}) or {}
    print(f'Deleted : {len(deleted)} (does not participate in clock calculation)')
    for w in warnings[:20]: print('WARN   :',w)
    for e in errors: print('ERROR  :',e)
    if errors:
        print(f'RESULT : FAIL ({len(errors)} errors)')
        return 1
    print('RESULT : PASS')
    return 0
if __name__=='__main__': raise SystemExit(main())
