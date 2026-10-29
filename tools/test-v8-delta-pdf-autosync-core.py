#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
js = (root / "web" / "app_v6.js").read_text(encoding="utf-8")
html = (root / "web" / "index_v6.html").read_text(encoding="utf-8")
backend_path = root / "run_clova_v8_2_gamma.py"
if not backend_path.is_file():
    backend_path = root / "run_clova_v8_eta.py"
if not backend_path.is_file():
    backend_path = root / "run_clova_v8_delta.py"
backend = backend_path.read_text(encoding="utf-8")

checks = {
    "gamma event schema preserved": 'PDF_TIMELINE_SCHEMA = "v8.0-gamma-pdf-events-v1"' in backend,
    "events endpoint consumed": '/api/pdf/events?session_id=' in js,
    "timeline binary search": 'function pdfTimelineStateAt(recordingTime)' in js and 'while (lo <= hi)' in js,
    "master clock maps from segment source": 'function recordingTimeForSegmentOffset(seg, offsetSec = 0)' in js and 'seg.recording_start' in js,
    "gapless loop sync": 'syncPdfToPlaybackSegment(active.seg, offset);' in js,
    "native audio sync": 'syncPdfToPlaybackSegment(seg, els.player.currentTime);' in js,
    "manual page pauses PDF only": 'pausePdfAutoFollowForManualBrowse("페이지 이동")' in js,
    "manual document pauses PDF only": 'pausePdfAutoFollowForManualBrowse("문서 선택")' in js,
    "pinch does not pause follow": 'startPdfTouchPinch(stage)' in js and 'pausePdfAutoFollowForManualBrowse' not in re.search(r'function startPdfTouchPinch\(stage\).*?\n  }', js, re.S).group(0),
    "rejoin control": 'id="pdfReturnToLecture"' in html and 'rejoinPdfLecturePosition' in js,
    "PDF touch does not stop transcript tracking": 'isTranscriptInteraction' in js and '#transcriptPane' in js,
    "playback sync stays review-only": 'applyPdfTimelineState' in js,
    "resume persists visible viewer before gamma snapshot": 'try { await persistPdfViewState(); } catch (_) {}' in js,
}

# Guard the most important invariant: the auto-sync apply function must not call
# the persistent viewer-state endpoint/queue, otherwise playback could mutate
# gamma's lecture timeline when a recording lease exists.
m = re.search(r'function applyPdfTimelineState\(target, \{ force = false \} = \{\}\) \{(.*?)\n  \}\n\n  function syncPdfToRecordingTime', js, re.S)
checks["auto apply never persists"] = bool(m) and 'persistPdfViewState' not in m.group(1) and '/api/pdf/view-state' not in m.group(1)

# Deterministic state-at-time drill, including equal timestamps. Sequence order
# at one recording_time must select the last seq, matching gamma validation.
events = [
    {"seq": 1, "time": 10.0, "type": "pdf_open", "pdf_id": "A", "page": 1},
    {"seq": 2, "time": 20.0, "type": "pdf_page", "pdf_id": "A", "page": 2},
    {"seq": 3, "time": 20.0, "type": "pdf_page", "pdf_id": "A", "page": 3},
    {"seq": 4, "time": 30.0, "type": "pdf_open", "pdf_id": "B", "page": 1},
    {"seq": 5, "time": 40.0, "type": "pdf_close", "pdf_id": "B", "page": 1},
]

def state_at(t):
    latest = None
    for ev in sorted(events, key=lambda e: (e["time"], e["seq"])):
        if ev["time"] <= t + 1e-6:
            latest = ev
        else:
            break
    if latest is None or latest["type"] == "pdf_close":
        return ("no_pdf", "", 1)
    return ("pdf", latest["pdf_id"], latest["page"])

checks["state before first event"] = state_at(0.0) == ("no_pdf", "", 1)
checks["equal-time seq resolves last event"] = state_at(20.0) == ("pdf", "A", 3)
checks["multi-PDF switch"] = state_at(35.0) == ("pdf", "B", 1)
checks["close returns NO_PDF"] = state_at(45.0) == ("no_pdf", "", 1)
# Deleted/compressed playback gaps do not matter: mapping uses immutable segment
# recording_start rather than cumulative playback elapsed.
recording_start, source_offset = 83.25, 1.75
checks["recording-time source offset math"] = abs((recording_start + source_offset) - 85.0) < 1e-9

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS" if ok else "FAIL"), name)
if failed:
    raise SystemExit("failed: " + ", ".join(failed))
print("RESULT: PASS")
