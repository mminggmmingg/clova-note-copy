#!/usr/bin/env python3
from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "native_audio_daemon_v8_2_beta.py"

class State:
    starts = []
    chunk_bytes = []
    clocks = []

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(n) if n else b""
        if self.path.startswith("/api/chunk"):
            State.starts.append(int(self.headers.get("X-Clova-Sample-Start", "-1")))
            State.chunk_bytes.append(len(body))
            payload = b'{"ok":true}'
        elif self.path == "/api/native/clock":
            try:
                State.clocks.append(json.loads(body.decode("utf-8") or "{}"))
            except Exception:
                State.clocks.append({})
            payload = b'{"ok":true}'
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    project = td / "project"
    session = project / "data" / "sessions" / "test-session"
    session.mkdir(parents=True)
    (project / "logs").mkdir(parents=True)
    status = project / "status.json"

    # Fake pw-record: help probe + deterministic 2 seconds of PCM, emitted
    # fast enough that the artificial ASR stall creates a real durable backlog.
    bindir = td / "bin"
    bindir.mkdir()
    fake = bindir / "pw-record"
    fake.write_text(r'''#!/usr/bin/env python3
import os, sys, time
if "--help" in sys.argv:
    print("pw-record fake --rate --channels --format --latency")
    raise SystemExit(0)
# 2 s * 16 kHz * 2 bytes = 64000 bytes.
block = (b"\x01\x00\x02\x00" * 800)  # 3200 bytes = 0.1 s
for _ in range(20):
    os.write(1, block)
    time.sleep(0.10)
''', encoding="utf-8")
    fake.chmod(0o755)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    env = dict(os.environ)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    cp = subprocess.run([
        "python3", str(DAEMON),
        "--session-id", "test-session",
        "--project-dir", str(project),
        "--backend-url", f"http://127.0.0.1:{port}",
        "--token", "test-token",
        "--start-sample", "0",
        "--rate", "16000",
        "--status-file", str(status),
        "--test-asr-stall-sec", "1.0",
        "--test-asr-stall-after-sec", "0.3",
        "--shutdown-drain-sec", "5",
    ], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)

    server.shutdown(); server.server_close()
    assert cp.returncode == 0, cp.stdout

    raw = session / "lecture_raw.wav"
    with wave.open(str(raw), "rb") as f:
        assert f.getframerate() == 16000
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert f.getnframes() == 32000, f.getnframes()

    # 250 ms chunks = 4000 samples = 8000 bytes. Two seconds => 8 chunks.
    assert len(State.starts) == 8, (len(State.starts), State.starts, cp.stdout)
    assert State.starts == [i * 4000 for i in range(8)], State.starts
    assert State.chunk_bytes == [8000] * 8, State.chunk_bytes

    st = json.loads(status.read_text(encoding="utf-8"))
    assert st["active"] is False
    assert st["sample_count"] == 32000
    assert st["inference_cursor_sample"] == 32000
    assert st["inference_backlog_samples"] == 0
    assert st["dropped_chunks"] == 0
    assert st["test_asr_stall_done"] is True

    # During the injected model stall capture clock must have advanced while
    # inference cursor lagged behind. At least one heartbeat should expose it.
    assert any(
        int(x.get("sample_count") or 0) > int(x.get("inference_cursor_sample") or 0)
        for x in State.clocks
    ), State.clocks

print("V8.2-beta RAW-backed inference separation: PASS")
