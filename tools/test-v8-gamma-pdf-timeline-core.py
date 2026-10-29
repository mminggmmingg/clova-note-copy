#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
backend_path = root / "run_clova_v8_2_gamma.py"
if not backend_path.is_file():
    backend_path = root / "run_clova_v8_eta.py"
if not backend_path.is_file():
    backend_path = root / "run_clova_v8_delta.py"
backend = backend_path.read_text(encoding="utf-8")
js = (root / "web" / "app_v6.js").read_text(encoding="utf-8")

checks = {
    "gamma schema": 'PDF_TIMELINE_SCHEMA = "v8.0-gamma-pdf-events-v1"' in backend,
    "append-only file": 'PDF_EVENTS_FILENAME = "pdf_events.jsonl"' in backend,
    "fsync durability": "os.fsync(f.fileno())" in backend,
    "master sample anchor": '"recording_sample": sample' in backend,
    "canonical ref": 'f"clova://pdf/{pdf_id}/page/{page}"' in backend,
    "recorder owner gate": "timeline_recording_owner" in backend and "s.recording_client_id" in backend,
    "resume reconcile": '_sync_pdf_timeline_to_view_locked(s, reason="recording_resume")' in backend,
    "events API": '"/api/pdf/events"' in backend,
    "serialized client queue": "pdfPersistChain" in js,
    "recorder client id sent": "client_id: recorderClientId" in js,
    "stop flushes pdf queue": "try { await state.pdfPersistChain; } catch (_) {}" in js,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS" if ok else "FAIL"), name)
if failed:
    raise SystemExit("failed: " + ", ".join(failed))
print("RESULT: PASS")
