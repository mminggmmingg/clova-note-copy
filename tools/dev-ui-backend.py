#!/usr/bin/env python3
"""Run the Local Clova HTTP API for UI development, without ASR or capture.

Serves the real Flask routes (register_routes) with no whisper server, VAD
model or host controller, so the native UI can browse sessions, transcripts,
segment audio, PDFs and annotations. Recording endpoints fail by design.
Sessions load lazily on first request; nothing is hydrated or rewritten up
front, so the project can be mounted read-only.

  docker run --rm --name clova-dev-ui-backend -p 127.0.0.1:8001:8000 \
    -v ~/clova-note-copy:/workspace:ro local-clova:rocm-v8-2-gamma-hotfix6 \
    python3 /workspace/tools/dev-ui-backend.py

Then: .venv-ui/bin/python -m ui_native --backend http://127.0.0.1:8001
"""
import importlib.util
import sys

sys.path.insert(0, "/workspace")
spec = importlib.util.spec_from_file_location("clova_backend", "/workspace/run_clova_v8_2_gamma.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

backend.register_routes(backend.app)
print(f"[DEV UI BACKEND] {len(list(backend.app.url_map.iter_rules()))} routes, no ASR/capture", flush=True)
backend.app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False, threaded=True)
