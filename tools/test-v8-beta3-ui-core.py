#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
css = (root / 'web' / 'app_v6.css').read_text(encoding='utf-8')
js = (root / 'web' / 'app_v6.js').read_text(encoding='utf-8')
html = (root / 'web' / 'index_v6.html').read_text(encoding='utf-8')

checks = {
    'beta3 cache/version marker': '8.0-beta.3' in html,
    'row-owned notebook rules': 'V8.0-beta.3 · resize/render stabilization' in css and 'background-size: 100% 32px !important;' in css,
    'no giant list repeating rule in beta3 override': 'html[data-theme="notebook"] .transcript-list::before' in css,
    'fixed pdf header row': 'flex: 0 0 52px !important;' in css and '.pdf-head-controls #pdfPageLabel' in css,
    'pdf may upscale to stage': 'width: 100% !important;' in css and 'height: 100% !important;' in css and 'object-fit: contain !important;' in css,
    'fullscreen sidebar-collapse expansion': 'fullscreen-active.sidebar-collapsed .session-view.pdf-reading' in css,
    'raf splitter repaint': 'state.columnResizeFrame = requestAnimationFrame' in js,
    'fullscreen dynamic transcript floor': 'fullscreen && sidebarCollapsed ? 226 : 266' in js,
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
if failed:
    raise SystemExit('V8.0-beta.3 UI core FAILED: ' + ', '.join(failed))
print('V8.0-beta.3 UI core: PASS')
