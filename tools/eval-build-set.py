#!/usr/bin/env python3
"""Build the V8.3 STT evaluation set (plan step S0) from recorded lectures.

Picks whole lectures per subject with a fixed seed, samples VAD segments from
them, and copies each segment WAV exactly as the app saved it, so every ASR
engine is scored on the same input the production worker gets. Also cuts
non-speech candidates from lecture_raw.wav gaps between segments (where VAD
heard no speech) to measure output on silence and noise.

  python3 tools/eval-build-set.py                      # data/eval/ko-lecture-v1
  python3 tools/eval-build-set.py --name trial --segments 40 --blind 10 --nonspeech 10

Items get a mode for labeling (tools/eval-label-server.py):
  blind     transcribe from audio only; Whisper's text is never shown
  correct   fix Whisper's text
  nonspeech confirm there is no speech (or transcribe what is there)

Lectures in a set are evaluation-only: keep them out of any LoRA training.
The set lives under data/ (lecture audio and text, never committed).
"""
import argparse
import json
import random
import shutil
import sys
import wave
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SR = 16000
GAP_MIN_SEC = 3.0       # silence between segments worth sampling
GAP_MARGIN_SEC = 0.5    # stay clear of the neighbouring segments
NONSPEECH_LEN = (2.0, 10.0)


def read_records(session_dir):
    deleted = {}
    path = session_dir / "deleted_segments.json"
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        deleted = raw.get("segments", raw) if isinstance(raw, dict) else {}
    records = []
    for line in (session_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(rec, dict)
            and rec.get("final_source") == "whisper_large_v3"
            and str(rec.get("segment")) not in deleted
            and (session_dir / "segments" / f"{int(rec['segment']):06d}.wav").is_file()
        ):
            records.append(rec)
    return records


def lectures_by_subject(min_segments):
    out = defaultdict(list)
    for session_dir in sorted((DATA / "sessions").iterdir()):
        if not (session_dir / "transcript.jsonl").is_file():
            continue
        meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        subject = str(meta.get("subject_id") or "")
        records = read_records(session_dir)
        if subject and len(records) >= min_segments:
            out[subject].append((session_dir, meta, records))
    return out


def gap_clips(records, rng, count):
    """Random (start, end) seconds inside gaps between consecutive segments."""
    spans = sorted(
        (float(r["recording_start"]), float(r["recording_end"]))
        for r in records
        if r.get("recording_start") is not None and r.get("recording_end") is not None
    )
    gaps = [
        (a_end + GAP_MARGIN_SEC, b_start - GAP_MARGIN_SEC)
        for (_, a_end), (b_start, _) in zip(spans, spans[1:])
        if b_start - a_end >= GAP_MIN_SEC
    ]
    rng.shuffle(gaps)
    clips = []
    for lo, hi in gaps[:count]:
        length = min(hi - lo, rng.uniform(*NONSPEECH_LEN))
        start = rng.uniform(lo, hi - length)
        clips.append((round(start, 3), round(start + length, 3)))
    return clips


def cut_raw(raw_path, raw_start_sample, start_sec, end_sec, out_path):
    """Mono 16 kHz PCM16 clip, downmixed the same way the backend builds segments."""
    with wave.open(str(raw_path), "rb") as w:
        channels = w.getnchannels()
        first = max(0, int(round(start_sec * SR)) - raw_start_sample)
        frames = int(round((end_sec - start_sec) * SR))
        w.setpos(min(first, w.getnframes()))
        pcm = np.frombuffer(w.readframes(frames), dtype="<i2")
    mono = pcm.reshape(-1, channels).astype(np.float32).mean(axis=1) / 32768.0
    out = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(out.tobytes())
    return len(out) / SR


def split_evenly(total, parts):
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", default="ko-lecture-v1")
    ap.add_argument("--lectures-per-subject", type=int, default=3)
    ap.add_argument("--segments", type=int, default=400)
    ap.add_argument("--blind", type=int, default=100, help="of --segments, transcribed without Whisper's text")
    ap.add_argument("--nonspeech", type=int, default=100)
    ap.add_argument("--min-segments", type=int, default=50, help="skip shorter (test) sessions")
    ap.add_argument("--seed", type=int, default=20261103)
    args = ap.parse_args()

    out_dir = DATA / "eval" / args.name
    if out_dir.exists():
        print(f"{out_dir} already exists; labels there are not overwritten. Pick another --name.", file=sys.stderr)
        return 1
    if args.blind > args.segments:
        print("--blind cannot exceed --segments", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    subjects = lectures_by_subject(args.min_segments)
    lectures = []
    for subject in sorted(subjects):
        pool = subjects[subject]
        lectures += rng.sample(pool, min(args.lectures_per_subject, len(pool)))
    if not lectures:
        print("no lectures with Whisper finals found", file=sys.stderr)
        return 1

    items = []
    for (session_dir, meta, records), quota, ns_quota in zip(
        lectures,
        split_evenly(args.segments, len(lectures)),
        split_evenly(args.nonspeech, len(lectures)),
    ):
        lecture = session_dir.name
        for rec in sorted(rng.sample(records, min(quota, len(records))), key=lambda r: int(r["segment"])):
            seg = int(rec["segment"])
            items.append({
                "id": f"{lecture}:{seg:06d}",
                "kind": "speech",
                "session_id": lecture,
                "subject_id": meta.get("subject_id"),
                "segment": seg,
                "duration_sec": rec.get("duration_sec"),
                "recording_start": rec.get("recording_start"),
                "recording_end": rec.get("recording_end"),
                "source_wav": f"data/sessions/{lecture}/segments/{seg:06d}.wav",
                "whisper_text": rec.get("final_text") or rec.get("segment_stt_raw") or "",
                "whisper_rejected": bool(rec.get("segment_stt_rejected")),
            })
        raw_start = int(meta.get("continuous_raw_start_sample") or 0)
        for start, end in gap_clips(records, rng, ns_quota):
            items.append({
                "id": f"{lecture}:gap-{int(start * 1000):09d}",
                "kind": "nonspeech",
                "session_id": lecture,
                "subject_id": meta.get("subject_id"),
                "recording_start": start,
                "recording_end": end,
                "source_wav": f"data/sessions/{lecture}/lecture_raw.wav",
                "raw_start_sample": raw_start,
            })

    speech = [it for it in items if it["kind"] == "speech"]
    blind_ids = {it["id"] for it in rng.sample(speech, min(args.blind, len(speech)))}
    for it in items:
        it["mode"] = "nonspeech" if it["kind"] == "nonspeech" else ("blind" if it["id"] in blind_ids else "correct")

    clips = out_dir / "clips"
    clips.mkdir(parents=True)
    for it in items:
        it["clip"] = f"clips/{it['id'].replace(':', '_')}.wav"
        if it["kind"] == "speech":
            shutil.copy2(ROOT / it["source_wav"], out_dir / it["clip"])
        else:
            it["duration_sec"] = round(cut_raw(
                ROOT / it["source_wav"], it["raw_start_sample"],
                it["recording_start"], it["recording_end"], out_dir / it["clip"],
            ), 3)

    with (out_dir / "manifest.jsonl").open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    info = {
        "name": args.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "seed": args.seed,
        "lectures": [d.name for d, _, _ in lectures],
        "eval_only_note": "Exclude these lectures from LoRA training data.",
        "counts": {
            mode: sum(1 for it in items if it["mode"] == mode)
            for mode in ("blind", "correct", "nonspeech")
        },
        "audio_minutes": round(sum(float(it["duration_sec"] or 0) for it in items) / 60, 1),
        "args": vars(args),
    }
    (out_dir / "set.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("name", "counts", "audio_minutes")}, ensure_ascii=False))
    print(f"lectures: {len(info['lectures'])} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
