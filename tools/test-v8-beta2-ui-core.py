#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
html = (root / 'web/index_v6.html').read_text(encoding='utf-8')
css = (root / 'web/app_v6.css').read_text(encoding='utf-8')
js = (root / 'web/app_v6.js').read_text(encoding='utf-8')

checks = {
    'compact PDF header contains page controls': 'class="pdf-head-controls"' in html and 'id="pdfPrev"' in html and 'id="pdfNext"' in html,
    'legacy separate PDF toolbar removed from markup': 'class="pdf-page-toolbar"' not in html,
    'PDF reading transcript uses full width': '.session-view.pdf-reading > .transcript-pane > *' in css and 'max-width: none;' in css,
    'notebook transcript grid is list-owned': 'V8.0-beta.2 · Notebook grid alignment' in css and 'background-position: 0 0, 0 15px;' in css,
    'follow chooses scroller by PDF state': 'function currentTranscriptScroller()' in js and 'classList.contains("pdf-reading")' in js,
    'generic scroll does not disable follow': 'A layout resize can emit scroll without user intent' in js,
    'PDF layout change re-centers playing segment': 'Changing between alpha-like PDF OFF and split PDF READING' in js,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    for name in failed:
        print('FAIL:', name)
    raise SystemExit(1)
for name in checks:
    print('PASS:', name)
print('V8.0-beta.2 UI core: PASS')
