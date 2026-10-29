#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
html=(root/'web/index_v6.html').read_text(encoding='utf-8')
js=(root/'web/app_v6.js').read_text(encoding='utf-8')
backend=(root/'run_clova_v8_2_gamma.py').read_text(encoding='utf-8')
css=(root/'web/app_v6.css').read_text(encoding='utf-8')
for token in ['pdfToolPen','pdfToolEraser','pdfToolHighlighter','pdfAnnotationCanvas','pdfPageSurface']:
    assert token in html, token
for token in ['annotationLectureTimeContext','annotationSuppressUntilClear','softEraseAnnotation','anchor_type: "page_only"']:
    assert token in js, token
for token in ['annotation_add','annotation_erase','ANNOTATION_EVENTS_FILENAME','/api/annotation/anchor','operation_lecture_time','page_only']:
    assert token in backend, token
assert 'state.pdfGesturePointers.size >= 2' in js
assert 'pausePdfAutoFollowForManualBrowse("필기")' in js
assert '.pdf-annotation-canvas' in css
assert '@container (max-width: 690px)' in css
assert 'grid-template-columns: minmax(0,1fr) auto auto' in css
assert 'state.playbackRecordingTime != null' in js
assert 'lecture_time: null' not in js  # values are resolved dynamically, not hardcoded events
print('PASS : V8.1-alpha.1 page-only anchors / single-finger ink / two-finger navigation invariants')
