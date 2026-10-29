#!/usr/bin/env python3
"""Re-decode Whisper finals that were stored with a repetition loop.

Sessions recorded before the epsilon loop guard kept looping finals as-is
("아 어 어 어 ..."). This applies the live worker's own detector, retry and
word-map code to them, so a backfilled record matches what the worker would
store today: recovered text + rebuilt word map, or the original text marked
segment_stt_rejected ("Whisper · 반복 의심" in the UI). Both texts are kept in
segment_stt_loop_retry.

Run inside the backend image with the project at /workspace (read-write) and
a whisper-server reachable at WHISPER_SERVER_URL:

  python3 tools/backfill-whisper-loops.py           # dry run: list targets
  python3 tools/backfill-whisper-loops.py --apply   # rewrite transcripts

--apply first copies every transcript.jsonl it changes to
backups/loop-backfill-<stamp>/<session>/. Segments with a human edit, or that
already carry segment_stt_loop_retry, are left alone.
"""
import argparse
import importlib.util
import json
import shutil
import sys
import wave
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("clova_backend", ROOT / "run_clova_v8_2_gamma.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="rewrite transcripts (default: dry run)")
    args = ap.parse_args()

    backup_root = ROOT / "backups" / f"loop-backfill-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    totals = {"looped": 0, "recovered": 0, "flagged": 0, "skipped_edited": 0}

    for session in sorted(backend.DATA_ROOT.iterdir()):
        path = session / "transcript.jsonl"
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        edits = backend._read_json_path(session / "manual_edits.json", {"segments": {}}).get("segments") or {}
        changed = False

        for i, line in enumerate(lines):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if (
                not isinstance(rec, dict)
                or rec.get("final_source") != "whisper_large_v3"
                or rec.get("segment_stt_loop_retry")
            ):
                continue
            text = str(rec.get("segment_stt_raw") or "")
            bad, reason = backend.detect_whisper_repetition_loop(text)
            if not bad:
                continue

            seg = int(rec.get("segment") or 0)
            totals["looped"] += 1
            if str(seg) in edits:
                totals["skipped_edited"] += 1
                print(f"[SKIP HUMAN EDIT] {session.name} seg={seg}", flush=True)
                continue
            if not args.apply:
                print(f"[DRY RUN] {session.name} seg={seg} {reason} | {text[:80]}", flush=True)
                continue

            wav = session / "segments" / f"{seg:06d}.wav"
            new_text, chunks, rejected, reject_reason, loop_retry = backend._retry_whisper_loop(
                wav, seg, text, rec.get("segment_stt_chunks") or [], reason,
            )
            loop_retry["backfilled_at"] = backend._now_iso()
            word_map, word_meta = backend._segment_word_map(
                seg, new_text, chunks, wav_seconds(wav),
                audio_variant=rec.get("asr_audio_variant") or "raw",
                rejected=rejected,
            )
            rec.update({
                "segment_stt_raw": new_text,
                "segment_stt_chunks": chunks,
                "final_text": new_text,
                "word_audio_map": word_map,
                "word_alignment_meta": word_meta,
                "segment_stt_rejected": bool(rejected),
                "segment_stt_reject_reason": reject_reason or None,
                "segment_stt_loop_retry": loop_retry,
            })
            lines[i] = json.dumps(rec, ensure_ascii=False)
            changed = True
            totals["recovered" if loop_retry["accepted"] else "flagged"] += 1
            print(
                f"[BACKFILL] {session.name} seg={seg}",
                "recovered" if loop_retry["accepted"] else "kept+flagged",
                f"| {new_text[:80]}",
                flush=True,
            )

        if changed:
            dest = backup_root / session.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest / path.name)
            tmp = path.with_name(f".{path.name}.backfill.tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(path)

    print(json.dumps(totals), flush=True)
    if args.apply and (totals["recovered"] or totals["flagged"]):
        print(f"backups: {backup_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
