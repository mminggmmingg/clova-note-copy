#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
backend=root/'run_clova_v8_2_gamma.py'
if not backend.is_file(): backend=root/'run_clova_v8_eta.py'
s=backend.read_text(encoding='utf-8')
assert 'PDF_SEMANTIC_TIMELINE_SCHEMA = "v8.0-eta-pdf-semantic-timeline-v1"' in s
assert 'PDF_SEMANTIC_TIMELINE_FILENAME = "pdf_semantic_timeline.json"' in s
assert 'semantic_pdf_timeline = _build_pdf_semantic_timeline_locked(s, write=True)' in s
assert '"llm_used": False' in s
assert '/api/pdf/semantic-timeline' in s
assert 'pdf_semantic_timeline_dirty' in s
assert 'PDF_DWELL_IGNORE_LT = 1.5' in s
assert 'PDF_DWELL_WEAK_LT = 4.0' in s
assert 'PDF_DWELL_INCLUDE_LT = 10.0' in s
print('PASS: V8.0-eta backend semantic timeline invariants')
