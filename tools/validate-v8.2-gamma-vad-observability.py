#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = Path.home() / "clova-note-copy"
SESSIONS = PROJECT / "data" / "sessions"


def latest_session():
    if not SESSIONS.exists():
        return None
    items = [p for p in SESSIONS.iterdir() if p.is_dir()]
    return max(items, key=lambda p: p.stat().st_mtime) if items else None


def fetch_status(sid):
    q = urllib.parse.urlencode({"session_id": sid})
    with urllib.request.urlopen(f"http://127.0.0.1:8000/api/recording/status?{q}", timeout=3) as r:
        return json.load(r)


def main():
    session = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else latest_session()
    if session is None:
        print("RESULT        : FAIL")
        print("Reason        : no session found")
        return 1
    sid = session.name
    print(f"Session       : {sid}")

    try:
        status = fetch_status(sid)
    except Exception as e:
        status = None
        print(f"Status API    : unavailable ({e})")

    required = [
        "silero_vad_version",
        "vad_threshold",
        "vad_input_gain_db",
        "vad_reset_policy",
        "vad_reset_count",
        "vad_probability",
        "vad_probability_mean_1s",
        "vad_probability_max_1s",
        "vad_probability_above_threshold_ratio_1s",
        "vad_input_rms_dbfs_1s",
        "vad_input_peak_dbfs_1s",
        "vad_telemetry_enabled",
    ]

    ok = True
    if status is not None:
        missing = [k for k in required if k not in status]
        if missing:
            print("Status fields : MISSING " + ", ".join(missing))
            ok = False
        else:
            print(f"Silero VAD    : {status['silero_vad_version']}")
            print(f"Threshold     : {status['vad_threshold']}")
            print(f"VAD gain      : {status['vad_input_gain_db']} dB")
            print(f"Reset policy  : {status['vad_reset_policy']}")
            print(f"Reset count   : {status['vad_reset_count']}")
            print(f"P(last/mean/max): {status['vad_probability']:.3f} / {status['vad_probability_mean_1s']:.3f} / {status['vad_probability_max_1s']:.3f}")
            print(f"Above thresh  : {status['vad_probability_above_threshold_ratio_1s']:.3f}")
            print(f"VAD input lvl : RMS {status['vad_input_rms_dbfs_1s']:.1f} dBFS / peak {status['vad_input_peak_dbfs_1s']:.1f} dBFS")

    telemetry = session / "vad_telemetry.jsonl"
    if telemetry.exists() and telemetry.stat().st_size > 0:
        lines = telemetry.read_text(encoding="utf-8", errors="replace").splitlines()
        try:
            last = json.loads(lines[-1])
            print(f"Telemetry     : {telemetry} ({len(lines)} summaries)")
            print(f"Last rec time : {last.get('recording_time')} s")
            print(f"Last probs    : mean={last.get('probability_mean')} max={last.get('probability_max')}")
        except Exception as e:
            print(f"Telemetry     : malformed last line ({e})")
            ok = False
    else:
        if status is not None and status.get("recording"):
            print("Telemetry     : waiting for first ~1 s summary")
        else:
            print("Telemetry     : no file yet")

    print("RESULT        : " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
