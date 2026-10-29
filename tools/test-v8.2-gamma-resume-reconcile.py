#!/usr/bin/env python3
from pathlib import Path
import ast

root=Path(__file__).resolve().parents[1]
backend=(root/'run_clova_v8_2_gamma.py').read_text()
daemon=(root/'native_audio_daemon_v8_2_beta.py').read_text()
ast.parse(backend)
ast.parse(daemon)
assert 'def _reconcile_capture_cursor_from_raw' in backend
assert '_reconcile_capture_cursor_from_raw(s, reason="resume")' in backend
assert '_reconcile_capture_cursor_from_raw(s, reason="stop")' in backend
assert '[NATIVE CAPTURE RECONCILE]' in daemon
assert 'RAW shorter than requested start' in daemon
print('V8.2-gamma resume reconcile hotfix: PASS')
