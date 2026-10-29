#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
css = (root / 'web' / 'app_v6.css').read_text(encoding='utf-8')
js = (root / 'web' / 'app_v6.js').read_text(encoding='utf-8')
html = (root / 'web' / 'index_v6.html').read_text(encoding='utf-8')

checks = {
    'beta4 cache/version marker': '8.0-beta.4' in html,
    'stable row-owned notebook rules': 'background-size: 100% 32px !important;' in css,
    'fixed horizontal pdf toolbar': '.pdf-pane-head > .pdf-head-controls' in css and 'flex-direction: row !important;' in css,
    'page navigation group exists': 'class="pdf-nav-controls"' in html,
    'zoom controls exist': all(x in html for x in ['pdfZoomOut','pdfZoomLabel','pdfZoomIn','pdfZoomFit']),
    'fit-width page invariant': 'V8.0-beta.4 · fixed PDF toolbar + true fit-width + zoom' in css and 'height: auto !important;' in css and 'object-fit: unset !important;' in css,
    'viewer scrolls single oversized page': '.pdf-viewer-stage {' in css and 'overflow: auto !important;' in css,
    'zoom is applied as percent width': 'setProperty("--pdf-page-width"' in js and 'width: var(--pdf-page-width, 100%) !important;' in css,
    'zoom range 50-300': 'clampNumber(value, 0.5, 3, 1)' in js,
    'fit resets to width baseline': 'function fitPdfToWidth()' in js and 'setPdfZoom(1);' in js,
    'splitter can nearly fill workspace': 'fullscreen && sidebarCollapsed ? 166 : 186' in js and 'total - transcriptFloor - 6' in js,
    'raf splitter repaint': 'state.columnResizeFrame = requestAnimationFrame' in js,
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
if failed:
    raise SystemExit('V8.0-beta.4 UI core FAILED: ' + ', '.join(failed))
print('V8.0-beta.4 UI core: PASS')
