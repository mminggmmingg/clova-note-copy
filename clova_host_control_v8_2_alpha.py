#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "v8.2-alpha-control"


class CaptureManager:
    def __init__(self, project: Path, token: str, container: str, audio_target: str = ""):
        self.project = Path(project)
        self.token = token
        self.container = container
        self.audio_target = audio_target
        self.runtime_dir = self.project / ".runtime-v8.2-alpha"
        self.log_dir = self.project / "logs"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self.session_id = ""
        self.status_file: Path | None = None

    def _reap(self):
        if self.proc is not None and self.proc.poll() is not None:
            self.proc = None
            self.session_id = ""

    def status(self):
        with self.lock:
            self._reap()
            payload = {
                "active": bool(self.proc is not None and self.proc.poll() is None),
                "pid": int(self.proc.pid) if self.proc is not None and self.proc.poll() is None else 0,
                "session_id": self.session_id,
            }
            if self.status_file and self.status_file.is_file():
                try:
                    daemon = json.loads(self.status_file.read_text(encoding="utf-8"))
                    payload["daemon"] = daemon
                    if daemon.get("session_id") == self.session_id:
                        payload["active"] = bool(payload["active"] and daemon.get("active", True))
                except Exception:
                    pass
            return payload

    def _prepare_host_writable_session(self, session_id: str):
        """Make the bind-mounted session directory/raw WAV writable by the host user.

        Flask runs as root inside the ROCm container and creates new session
        directories on the bind mount.  The native capture daemon runs as the
        desktop user on the host, so without this ownership handoff it cannot
        create/append lecture_raw.wav.  Use container-root only for the minimal
        directory + RAW file ownership change; the rest of the session stays
        untouched.
        """
        if not session_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in session_id):
            raise RuntimeError(f"invalid session id for native capture: {session_id!r}")

        host_session = self.project / "data" / "sessions" / session_id
        if not host_session.is_dir():
            raise RuntimeError(f"session directory missing: {session_id}")

        uid = os.getuid()
        gid = os.getgid()
        owner = f"{uid}:{gid}"
        container_session = f"/workspace/data/sessions/{session_id}"
        container_raw = f"{container_session}/lecture_raw.wav"

        def docker_exec(*argv, check=True):
            result = subprocess.run(
                ["docker", "exec", "-u", "0", self.container, *argv],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if check and result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()[-800:]
                raise RuntimeError(
                    f"failed to prepare native capture permissions: {' '.join(argv)}: {detail}"
                )
            return result

        # The directory itself is normally created by root in Docker (0755).
        # Hand only this one session directory to the logged-in host user.
        docker_exec("chown", owner, container_session)
        docker_exec("chmod", "u+rwx", container_session)

        # On resume / failed-start retry an existing RAW WAV may still be root
        # owned.  Transfer it too, but do not recursively chown transcript/PDF
        # artifacts that the backend owns.
        exists = docker_exec("test", "-e", container_raw, check=False)
        if exists.returncode == 0:
            docker_exec("chown", owner, container_raw)
            docker_exec("chmod", "u+rw", container_raw)

        if not os.access(host_session, os.W_OK | os.X_OK):
            raise RuntimeError(
                f"session directory is still not host-writable after ownership handoff: {host_session}"
            )

    def start(self, session_id: str, start_sample: int, sample_rate: int = 16000):
        with self.lock:
            self._reap()
            if self.proc is not None and self.proc.poll() is None:
                if self.session_id == session_id:
                    return {"ok": True, "already_running": True, **self.status()}
                raise RuntimeError(f"native capture already active for {self.session_id}")

            daemon = self.project / "native_audio_daemon_v8_2_alpha.py"
            if not daemon.is_file():
                raise RuntimeError(f"native capture daemon missing: {daemon}")
            if not (self.project / "data" / "sessions" / session_id).is_dir():
                raise RuntimeError(f"session directory missing: {session_id}")

            # Docker creates the bind-mounted session as root. Before launching
            # host-side pw-record, hand off only the session directory and any
            # existing lecture_raw.wav to the desktop user.
            self._prepare_host_writable_session(session_id)

            status_file = self.runtime_dir / f"capture-{session_id}.json"
            try:
                status_file.unlink()
            except FileNotFoundError:
                pass
            log_path = self.log_dir / f"native-audio-v8.2-alpha-{session_id}.log"
            cmd = [
                sys.executable,
                str(daemon),
                "--session-id", session_id,
                "--project-dir", str(self.project),
                "--backend-url", "http://127.0.0.1:8000",
                "--token", self.token,
                "--start-sample", str(max(0, int(start_sample))),
                "--rate", str(int(sample_rate)),
                "--status-file", str(status_file),
            ]
            if self.audio_target:
                cmd += ["--target", self.audio_target]

            with log_path.open("wb", buffering=0) as log:
                proc = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            self.proc = proc
            self.session_id = session_id
            self.status_file = status_file

            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    tail = ""
                    try:
                        tail = log_path.read_text(encoding="utf-8", errors="replace")[-1800:]
                    except Exception:
                        pass
                    self.proc = None
                    self.session_id = ""
                    raise RuntimeError(f"native capture exited during startup ({proc.returncode}): {tail}")
                if status_file.is_file():
                    try:
                        st = json.loads(status_file.read_text(encoding="utf-8"))
                        if st.get("active") and st.get("session_id") == session_id:
                            return {"ok": True, "pid": proc.pid, "log": str(log_path), "daemon": st}
                    except Exception:
                        pass
                time.sleep(0.1)

            # pw-record can take a moment before the first status update. The
            # process being alive is sufficient to continue; heartbeat will
            # expose health to the UI.
            return {"ok": True, "pid": proc.pid, "log": str(log_path), "starting": True}

    def stop(self, session_id: str = ""):
        with self.lock:
            self._reap()
            if self.proc is None:
                return {"ok": True, "already_stopped": True, **self.status()}
            if session_id and self.session_id and session_id != self.session_id:
                raise RuntimeError(f"capture owner mismatch: active={self.session_id} requested={session_id}")
            proc = self.proc
            sid = self.session_id
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=20.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)
            rc = proc.returncode
            self.proc = None
            self.session_id = ""
            status = self.status()
            return {"ok": True, "session_id": sid, "returncode": rc, **status}

    def stop_for_shutdown(self):
        try:
            self.stop()
        except Exception as exc:
            print("[Host Control] capture stop warning:", repr(exc), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--token-file", type=Path, required=True)
    ap.add_argument("--container", default="local-clova-v8-2-alpha")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--audio-target", default=os.environ.get("CLOVA_AUDIO_TARGET", ""))
    args = ap.parse_args()

    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("empty control token")
    manager = CaptureManager(args.project, token, args.container, args.audio_target)

    def log(msg):
        print(f"[Clova Host Control] {msg}", flush=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, status, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            return self.headers.get("X-Clova-Token", "") == token

        def json_body(self):
            try:
                n = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(n) if n else b"{}"
                return json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return {}

        def do_GET(self):
            if self.path == "/health":
                return self.send_json(200, {"ok": True, "version": VERSION, "capture": manager.status()})
            if self.path.startswith("/capture/status"):
                if not self.authorized():
                    return self.send_json(403, {"error": "forbidden"})
                return self.send_json(200, {"ok": True, **manager.status()})
            return self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if not self.authorized():
                return self.send_json(403, {"error": "forbidden"})
            body = self.json_body()
            try:
                if self.path == "/capture/start":
                    sid = str(body.get("session_id") or "").strip()
                    if not sid:
                        return self.send_json(400, {"error": "session_id required"})
                    result = manager.start(
                        sid,
                        int(body.get("start_sample") or 0),
                        int(body.get("sample_rate") or 16000),
                    )
                    return self.send_json(200, result)
                if self.path == "/capture/stop":
                    result = manager.stop(str(body.get("session_id") or "").strip())
                    return self.send_json(200, result)
                if self.path == "/shutdown":
                    self.send_json(202, {"ok": True, "status": "shutting_down", "version": VERSION})

                    def shutdown_stack():
                        manager.stop_for_shutdown()
                        subprocess.run(
                            ["docker", "stop", "-t", "8", args.container],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        log("Local Clova Docker stopped")
                        threading.Timer(0.4, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()

                    threading.Thread(target=shutdown_stack, daemon=True).start()
                    return
                return self.send_json(404, {"error": "not found"})
            except Exception as exc:
                log(f"request error {self.path}: {exc!r}")
                return self.send_json(500, {"error": str(exc)})

    log(f"{VERSION} listening on {args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
