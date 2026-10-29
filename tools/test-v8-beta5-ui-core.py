#!/usr/bin/env python3
from pathlib import Path
root = Path(__file__).resolve().parents[1]
css = (root/'web/app_v6.css').read_text(encoding='utf-8')
js = (root/'web/app_v6.js').read_text(encoding='utf-8')
html = (root/'web/index_v6.html').read_text(encoding='utf-8')
checks = {
    'beta5 cache/version marker': '8.0-beta.5' in html,
    'uncapped PDF grid child width': 'V8.0-beta.5 · uncapped grid panes + touch pinch zoom' in css and 'width: auto !important;' in css and 'justify-self: stretch !important;' in css,
    'touch stage owns gestures': 'touch-action: none !important;' in css,
    'pinch distance implementation': 'pdfTouchDistance' in js and 'startPdfTouchPinch' in js,
    'pinch updates shared PDF zoom': 'setPdfZoom(pending.zoom, { persist: false })' in js,
    'one finger pan': 'stage.scrollLeft = pan.scrollLeft' in js and 'stage.scrollTop = pan.scrollTop' in js,
    'zoom persisted after touch': 'localStorage.setItem(PDF_ZOOM_KEY, String(state.pdfZoom))' in js,
    'gesture wired': 'wirePdfTouchGestures();' in js,
    'fit width still present': '--pdf-page-width' in js and 'width: var(--pdf-page-width, 100%) !important;' in css,
}
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items(): print(f"[{'PASS' if v else 'FAIL'}] {k}")
if failed: raise SystemExit('V8.0-beta.5 UI core FAILED: '+', '.join(failed))
print('V8.0-beta.5 UI core: PASS')
