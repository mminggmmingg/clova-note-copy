#!/usr/bin/env python3
"""Local Clova V8.2-alpha host-side native audio capture daemon.

Design invariant:
    PipeWire capture + lecture_raw.wav persistence must never wait on ASR.

The daemon captures mono 16 kHz S16_LE from pw-record, appends it directly to
session/lecture_raw.wav, then forwards 250 ms inference chunks to Flask from a
separate sender thread. A third heartbeat thread advances the backend's exact
recording_time from the native sample counter even if ASR temporarily lags.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "v8.2-alpha-native-capture"
DEFAULT_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_CHUNK_MS = 250
PCM_STALL_SEC = 3.0
PCM_STARTUP_GRACE_SEC = 5.0


def wav_header(sample_rate: int, data_bytes: int) -> bytes:
    channels = 1
    bits = 16
    block_align = channels * bits // 8
    byte_rate = sample_rate * block_align
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + int(data_bytes), b"WAVE", b"fmt ", 16, 1,
        channels, int(sample_rate), int(byte_rate), int(block_align), bits,
        b"data", int(data_bytes),
    )


class CrashSafePcm16WavWriter:
    def __init__(self, path: Path, sample_rate: int):
        self.path = Path(path)
        self.sample_rate = int(sample_rate)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size < 44:
            self.path.write_bytes(wav_header(self.sample_rate, 0))
        self.f = self.path.open("r+b", buffering=0)
        self.f.seek(0, os.SEEK_END)
        if self.f.tell() < 44:
            self.f.seek(0)
            self.f.write(wav_header(self.sample_rate, 0))
        self.f.seek(0, os.SEEK_END)
        self._last_fsync = time.monotonic()

    @property
    def frames(self) -> int:
        size = max(44, self.path.stat().st_size)
        return max(0, size - 44) // 2

    def append(self, pcm16: bytes) -> int:
        if not pcm16:
            return 0
        if len(pcm16) % 2:
            raise ValueError("PCM16 payload must contain complete samples")
        self.f.seek(0, os.SEEK_END)
        self.f.write(pcm16)
        end = self.f.tell()
        data_bytes = max(0, end - 44)
        self.f.seek(0)
        self.f.write(wav_header(self.sample_rate, data_bytes))
        self.f.seek(0, os.SEEK_END)
        now = time.monotonic()
        if now - self._last_fsync >= 1.0:
            os.fsync(self.f.fileno())
            self._last_fsync = now
        return len(pcm16) // 2

    def close(self):
        if self.f.closed:
            return
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()


def http_json(url: str, token: str, payload: dict, timeout: float = 3.0):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Clova-Token": token,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def http_audio(url: str, token: str, pcm16: bytes, start_sample: int, timeout: float = 30.0):
    req = urllib.request.Request(
        url,
        data=pcm16,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Clova-Token": token,
            "X-Clova-Native-Capture": "1",
            "X-Clova-Audio-Format": "s16le",
            "X-Clova-Sample-Start": str(int(start_sample)),
            "X-Clova-Sample-End": str(int(start_sample) + len(pcm16) // 2),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def atomic_status(path: Path, payload: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--project-dir", type=Path, required=True)
    ap.add_argument("--backend-url", default="http://127.0.0.1:8000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--start-sample", type=int, default=0)
    ap.add_argument("--rate", type=int, default=DEFAULT_RATE)
    ap.add_argument("--chunk-ms", type=int, default=DEFAULT_CHUNK_MS)
    ap.add_argument("--target", default="")
    ap.add_argument("--status-file", type=Path, required=True)
    ap.add_argument("--queue-chunks", type=int, default=240)
    args = ap.parse_args()

    if args.rate != 16000:
        raise SystemExit("V8.2-alpha currently requires --rate 16000")
    if args.chunk_ms <= 0:
        raise SystemExit("--chunk-ms must be > 0")

    sid = args.session_id.strip()
    session_dir = args.project_dir / "data" / "sessions" / sid
    if not session_dir.is_dir():
        raise SystemExit(f"session directory missing: {session_dir}")

    raw_path = session_dir / "lecture_raw.wav"
    writer = CrashSafePcm16WavWriter(raw_path, args.rate)
    existing_frames = writer.frames
    start_sample = max(0, int(args.start_sample))
    if existing_frames != start_sample:
        # New V8.2 sessions start at zero and resumes append exactly. Refuse a
        # mismatch rather than silently corrupt source-time provenance.
        writer.close()
        raise SystemExit(
            f"RAW frame/start mismatch: wav_frames={existing_frames} start_sample={start_sample}"
        )

    stop_event = threading.Event()
    sender_done = threading.Event()
    q: queue.Queue = queue.Queue(maxsize=max(8, int(args.queue_chunks)))
    lock = threading.Lock()
    stats = {
        "sample_count": start_sample,
        "queue_depth": 0,
        "dropped_chunks": 0,
        "sent_chunks": 0,
        "send_errors": 0,
        "capture_bytes": 0,
        "started_at": time.time(),
        "started_monotonic": time.monotonic(),
        "last_pcm_monotonic": 0.0,
        "first_pcm_seen": False,
        "capture_stalled": False,
        "last_error": "",
    }

    def snapshot(active=True):
        now_mono = time.monotonic()
        with lock:
            first_pcm_seen = bool(stats["first_pcm_seen"])
            last_pcm = float(stats["last_pcm_monotonic"] or 0.0)
            started_mono = float(stats["started_monotonic"] or now_mono)
            if first_pcm_seen and last_pcm > 0:
                pcm_age = max(0.0, now_mono - last_pcm)
            else:
                pcm_age = max(0.0, now_mono - started_mono)
            stalled = bool(
                active
                and (
                    (first_pcm_seen and pcm_age > PCM_STALL_SEC)
                    or ((not first_pcm_seen) and pcm_age > PCM_STARTUP_GRACE_SEC)
                )
            )
            stats["capture_stalled"] = stalled
            return {
                "version": VERSION,
                "active": bool(active),
                "pid": os.getpid(),
                "session_id": sid,
                "sample_rate": args.rate,
                "sample_count": int(stats["sample_count"]),
                "recording_time_sec": round(int(stats["sample_count"]) / float(args.rate), 6),
                "queue_depth": q.qsize(),
                "dropped_chunks": int(stats["dropped_chunks"]),
                "sent_chunks": int(stats["sent_chunks"]),
                "send_errors": int(stats["send_errors"]),
                "capture_bytes": int(stats["capture_bytes"]),
                "first_pcm_seen": first_pcm_seen,
                "last_pcm_age_sec": round(pcm_age, 3),
                "capture_stalled": stalled,
                "last_error": str(stats["last_error"]),
                "raw_path": str(raw_path),
                "updated_at": time.time(),
            }

    def save_status(active=True):
        try:
            args.status_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_status(args.status_file, snapshot(active))
        except Exception as exc:
            print("[NATIVE STATUS WARN]", repr(exc), flush=True)

    chunk_samples = int(args.rate * args.chunk_ms / 1000)
    chunk_bytes = chunk_samples * 2
    infer_buffer = bytearray()
    infer_next_sample = start_sample

    def queue_chunk(payload: bytes, sample_start: int):
        if not payload:
            return
        try:
            q.put_nowait((bytes(payload), int(sample_start)))
        except queue.Full:
            # Capture and RAW persistence are more important than realtime ASR.
            with lock:
                stats["dropped_chunks"] += 1
                stats["last_error"] = "inference queue full; dropped ASR chunk"
            print("[NATIVE CAPTURE] inference queue full; RAW preserved, ASR chunk dropped", flush=True)

    backend_chunk_url = args.backend_url.rstrip("/") + f"/api/chunk?session_id={sid}"
    backend_clock_url = args.backend_url.rstrip("/") + "/api/native/clock"

    def sender_loop():
        while not sender_done.is_set() or not q.empty():
            try:
                payload, sample_start = q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                attempts = 0
                while True:
                    try:
                        http_audio(backend_chunk_url, args.token, payload, sample_start, timeout=30.0)
                        with lock:
                            stats["sent_chunks"] += 1
                        break
                    except urllib.error.HTTPError as exc:
                        # 409 after a deliberate stop means Flask is already closed.
                        if exc.code == 409 and stop_event.is_set():
                            break
                        attempts += 1
                        with lock:
                            stats["send_errors"] += 1
                            stats["last_error"] = f"audio HTTP {exc.code}"
                        if attempts >= 5 or stop_event.is_set():
                            print("[NATIVE ASR SEND ERROR]", repr(exc), flush=True)
                            break
                        time.sleep(min(2.0, 0.2 * (2 ** attempts)))
                    except Exception as exc:
                        attempts += 1
                        with lock:
                            stats["send_errors"] += 1
                            stats["last_error"] = repr(exc)
                        if attempts >= 5 or stop_event.is_set():
                            print("[NATIVE ASR SEND ERROR]", repr(exc), flush=True)
                            break
                        time.sleep(min(2.0, 0.2 * (2 ** attempts)))
            finally:
                q.task_done()
        print("[NATIVE ASR] sender stopped", flush=True)

    def heartbeat_loop():
        stall_reported = False
        while not stop_event.wait(0.5):
            snap = snapshot(True)
            if snap["capture_stalled"] and not stall_reported:
                stall_reported = True
                with lock:
                    stats["last_error"] = f"PCM stalled: no captured bytes for {snap['last_pcm_age_sec']:.3f}s"
                print(
                    "[NATIVE CAPTURE STALLED]",
                    f"last_pcm_age={snap['last_pcm_age_sec']:.3f}s",
                    f"samples={snap['sample_count']}",
                    flush=True,
                )
            elif not snap["capture_stalled"] and stall_reported:
                stall_reported = False
                print("[NATIVE CAPTURE RECOVERED] PCM resumed", flush=True)
            try:
                http_json(
                    backend_clock_url,
                    args.token,
                    {
                        "session_id": sid,
                        "sample_count": snap["sample_count"],
                        "queue_depth": snap["queue_depth"],
                        "dropped_chunks": snap["dropped_chunks"],
                        "pid": os.getpid(),
                        "last_pcm_age_sec": snap["last_pcm_age_sec"],
                        "capture_stalled": snap["capture_stalled"],
                    },
                    timeout=2.0,
                )
            except Exception as exc:
                with lock:
                    stats["last_error"] = f"clock heartbeat: {exc!r}"
            save_status(True)

    sender = threading.Thread(target=sender_loop, name="clova-native-asr-sender", daemon=True)
    heartbeat = threading.Thread(target=heartbeat_loop, name="clova-native-clock", daemon=True)
    sender.start()
    heartbeat.start()

    # PipeWire compatibility: pw-record in older Ubuntu/PipeWire releases
    # (including the 1.0.x line) does not expose the newer --raw switch.
    # FILE="-" is already a raw PCM stdout stream there. Newer builds may
    # support --raw explicitly, so feature-detect it instead of assuming.
    try:
        help_probe = subprocess.run(
            ["pw-record", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2.0,
            check=False,
        ).stdout or ""
    except Exception:
        help_probe = ""

    cmd = ["pw-record"]
    if "--raw" in help_probe:
        cmd.append("--raw")
    cmd += [
        f"--rate={args.rate}",
        "--channels=1",
        "--channel-map=mono",
        "--format=s16",
        "--quality=10",
        "--latency=100ms",
    ]
    if args.target:
        cmd.append(f"--target={args.target}")
    cmd.append("-")

    print("[NATIVE CAPTURE]", " ".join(cmd[:-1]), "STDOUT", flush=True)
    pw_stderr_path = args.project_dir / "logs" / f"pw-record-v8.2-alpha-{sid}.stderr.log"
    pw_stderr_path.parent.mkdir(parents=True, exist_ok=True)
    pw_stderr_log = pw_stderr_path.open("ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=pw_stderr_log,
        bufsize=0,
    )

    def request_stop(signum=None, frame=None):
        if stop_event.is_set():
            return
        print("[NATIVE CAPTURE] stop requested", signum if signum is not None else "", flush=True)
        stop_event.set()
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                pass

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    # Mark ready once pw-record has survived startup.
    time.sleep(0.15)
    if proc.poll() is not None:
        try:
            pw_stderr_log.flush()
            err = pw_stderr_path.read_text(encoding="utf-8", errors="replace")[-1200:]
        except Exception:
            err = ""
        pw_stderr_log.close()
        writer.close()
        raise SystemExit(f"pw-record exited during startup: {proc.returncode}: {err}")
    save_status(True)

    capture_buffer = bytearray()
    try:
        while True:
            if proc.stdout is None:
                break
            data = os.read(proc.stdout.fileno(), 8192)
            if not data:
                break
            capture_buffer.extend(data)
            even_len = (len(capture_buffer) // 2) * 2
            if not even_len:
                continue
            pcm = bytes(capture_buffer[:even_len])
            del capture_buffer[:even_len]

            appended = writer.append(pcm)
            with lock:
                stats["sample_count"] += appended
                stats["capture_bytes"] += len(pcm)
                stats["last_pcm_monotonic"] = time.monotonic()
                stats["first_pcm_seen"] = True
                stats["capture_stalled"] = False

            infer_buffer.extend(pcm)
            while len(infer_buffer) >= chunk_bytes:
                payload = bytes(infer_buffer[:chunk_bytes])
                del infer_buffer[:chunk_bytes]
                queue_chunk(payload, infer_next_sample)
                infer_next_sample += chunk_samples

            if stop_event.is_set() and proc.poll() is not None:
                break
    except KeyboardInterrupt:
        request_stop()
    finally:
        stop_event.set()
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except Exception:
                    proc.kill()
        # Forward the final partial inference chunk. RAW has already been saved.
        if infer_buffer:
            usable = (len(infer_buffer) // 2) * 2
            if usable:
                payload = bytes(infer_buffer[:usable])
                queue_chunk(payload, infer_next_sample)
                infer_next_sample += usable // 2
        writer.close()

        # Final clock is sent before Flask marks the session stopped.
        snap = snapshot(True)
        try:
            http_json(
                backend_clock_url,
                args.token,
                {
                    "session_id": sid,
                    "sample_count": snap["sample_count"],
                    "queue_depth": snap["queue_depth"],
                    "dropped_chunks": snap["dropped_chunks"],
                    "pid": os.getpid(),
                },
                timeout=2.0,
            )
        except Exception as exc:
            print("[NATIVE FINAL CLOCK WARN]", repr(exc), flush=True)

        # Give ASR forwarding a finite grace period; capture integrity never depends on it.
        deadline = time.monotonic() + 15.0
        while q.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.05)
        sender_done.set()
        sender.join(timeout=2.0)
        if q.unfinished_tasks:
            print(f"[NATIVE ASR] {q.unfinished_tasks} inference chunk(s) remained at shutdown; RAW is complete", flush=True)

        save_status(False)
        try:
            pw_stderr_log.flush()
            pw_stderr_log.close()
        except Exception:
            pass

    snap = snapshot(False)
    print(
        "[NATIVE CAPTURE STOPPED]",
        f"samples={snap['sample_count']}",
        f"seconds={snap['recording_time_sec']}",
        f"dropped_asr_chunks={snap['dropped_chunks']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
