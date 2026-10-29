#!/usr/bin/env python3
"""Local Clova V8.2-beta host-side native audio capture daemon.

V8.2-beta invariant:
    capture/RAW persistence never waits on inference.

Unlike V8.2-alpha's bounded in-memory inference queue, beta uses lecture_raw.wav
itself as the durable inference spool. The capture loop only appends PCM and
advances the native sample clock. A sender thread owns an independent
``inference_cursor_sample`` and re-reads already-durable PCM from RAW. If
Qwen/VAD/BatiSay stalls, inference backlog grows on disk without blocking or
dropping capture samples.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "v8.2-gamma-stereo-raw-backed-inference-v1"
DEFAULT_RATE = 16000
DEFAULT_CHANNELS = 2
DEFAULT_CHUNK_MS = 250
PCM_STALL_SEC = 3.0
PCM_STARTUP_GRACE_SEC = 5.0


def wav_header(sample_rate: int, data_bytes: int, channels: int) -> bytes:
    channels = int(channels)
    bits = 16
    block_align = channels * bits // 8
    byte_rate = int(sample_rate) * block_align
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + int(data_bytes), b"WAVE", b"fmt ", 16, 1,
        channels, int(sample_rate), int(byte_rate), int(block_align), bits,
        b"data", int(data_bytes),
    )


def read_wav_format(path: Path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 44:
        return None
    with path.open("rb") as f:
        header = f.read(44)
    if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise ValueError(f"unsupported RAW WAV header: {path}")
    channels = struct.unpack_from("<H", header, 22)[0]
    sample_rate = struct.unpack_from("<I", header, 24)[0]
    bits = struct.unpack_from("<H", header, 34)[0]
    if bits != 16 or channels not in (1, 2):
        raise ValueError(
            f"unsupported RAW WAV format channels={channels} bits={bits}: {path}"
        )
    return int(channels), int(sample_rate)


class CrashSafePcm16WavWriter:
    def __init__(self, path: Path, sample_rate: int, channels: int):
        self.path = Path(path)
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.frame_bytes = self.channels * 2
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = read_wav_format(self.path)
        if existing is not None:
            existing_channels, existing_rate = existing
            if existing_channels != self.channels or existing_rate != self.sample_rate:
                raise ValueError(
                    f"RAW WAV format mismatch existing={existing_rate}Hz/{existing_channels}ch "
                    f"requested={self.sample_rate}Hz/{self.channels}ch"
                )
        if not self.path.exists() or self.path.stat().st_size < 44:
            self.path.write_bytes(wav_header(self.sample_rate, 0, self.channels))
        self.f = self.path.open("r+b", buffering=0)
        self.f.seek(0, os.SEEK_END)
        if self.f.tell() < 44:
            self.f.seek(0)
            self.f.write(wav_header(self.sample_rate, 0, self.channels))
        self.f.seek(0, os.SEEK_END)
        self._last_fsync = time.monotonic()

    @property
    def frames(self) -> int:
        size = max(44, self.path.stat().st_size)
        return max(0, size - 44) // self.frame_bytes

    def append(self, pcm16: bytes) -> int:
        if not pcm16:
            return 0
        if len(pcm16) % self.frame_bytes:
            raise ValueError(
                f"PCM16 payload must contain complete {self.channels}-channel frames"
            )
        self.f.seek(0, os.SEEK_END)
        self.f.write(pcm16)
        end = self.f.tell()
        data_bytes = max(0, end - 44)
        self.f.seek(0)
        self.f.write(wav_header(self.sample_rate, data_bytes, self.channels))
        self.f.seek(0, os.SEEK_END)
        now = time.monotonic()
        if now - self._last_fsync >= 1.0:
            os.fsync(self.f.fileno())
            self._last_fsync = now
        return len(pcm16) // self.frame_bytes

    def close(self):
        if self.f.closed:
            return
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()


def read_pcm16_frames(path: Path, start_frame: int, frame_count: int, channels: int) -> bytes:
    """Read durable interleaved PCM16 frames from lecture_raw.wav."""
    if frame_count <= 0:
        return b""
    frame_bytes = int(channels) * 2
    with Path(path).open("rb", buffering=0) as f:
        f.seek(44 + int(start_frame) * frame_bytes)
        return f.read(int(frame_count) * frame_bytes)


def http_json(url: str, token: str, payload: dict, timeout: float = 3.0):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Clova-Token": token},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def http_audio(
    url: str, token: str, pcm16: bytes, start_sample: int, channels: int,
    timeout: float = 30.0,
):
    req = urllib.request.Request(
        url,
        data=pcm16,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Clova-Token": token,
            "X-Clova-Native-Capture": "1",
            "X-Clova-Audio-Format": "s16le-interleaved",
            "X-Clova-Channels": str(int(channels)),
            "X-Clova-Sample-Unit": "frames",
            "X-Clova-Sample-Start": str(int(start_sample)),
            "X-Clova-Sample-End": str(
                int(start_sample) + len(pcm16) // (2 * int(channels))
            ),
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
    ap.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    ap.add_argument("--chunk-ms", type=int, default=DEFAULT_CHUNK_MS)
    ap.add_argument("--target", default="")
    ap.add_argument("--status-file", type=Path, required=True)
    ap.add_argument("--shutdown-drain-sec", type=float, default=30.0)
    # Test-only fault injection. 0 keeps production behavior unchanged.
    ap.add_argument("--test-asr-stall-sec", type=float, default=0.0)
    ap.add_argument("--test-asr-stall-after-sec", type=float, default=5.0)
    args = ap.parse_args()

    if args.rate != 16000:
        raise SystemExit("V8.2-beta currently requires --rate 16000")
    if args.channels not in (1, 2):
        raise SystemExit("V8.2-gamma capture supports --channels 1 or 2")
    if args.chunk_ms <= 0:
        raise SystemExit("--chunk-ms must be > 0")

    sid = args.session_id.strip()
    session_dir = args.project_dir / "data" / "sessions" / sid
    if not session_dir.is_dir():
        raise SystemExit(f"session directory missing: {session_dir}")

    raw_path = session_dir / "lecture_raw.wav"
    capture_channels = int(args.channels)
    existing_format = read_wav_format(raw_path)
    if existing_format is not None:
        existing_channels, existing_rate = existing_format
        if existing_rate != args.rate:
            raise SystemExit(
                f"existing RAW rate={existing_rate} does not match requested rate={args.rate}"
            )
        if existing_channels != capture_channels:
            print(
                "[NATIVE CAPTURE RESUME FORMAT]",
                f"requested_channels={capture_channels}",
                f"existing_channels={existing_channels}",
                "preserving existing RAW format",
                flush=True,
            )
            capture_channels = existing_channels
    writer = CrashSafePcm16WavWriter(raw_path, args.rate, capture_channels)
    frame_bytes = capture_channels * 2
    existing_frames = writer.frames
    start_sample = max(0, int(args.start_sample))
    if existing_frames < start_sample:
        writer.close()
        raise SystemExit(
            f"RAW shorter than requested start: wav_frames={existing_frames} start_sample={start_sample}"
        )
    if existing_frames > start_sample:
        print(
            "[NATIVE CAPTURE RECONCILE]",
            f"metadata_start={start_sample}",
            f"raw_frames={existing_frames}",
            f"delta={existing_frames - start_sample}",
            flush=True,
        )
        # lecture_raw.wav is authoritative. A periodic metadata checkpoint may
        # lag the crash-safe RAW writer by a few seconds after stop/restart.
        start_sample = existing_frames

    stop_event = threading.Event()
    sender_done = threading.Event()
    sender_abort = threading.Event()
    data_ready = threading.Event()
    lock = threading.Lock()
    chunk_frames = int(args.rate * args.chunk_ms / 1000)
    stats = {
        "sample_count": start_sample,
        "inference_cursor_sample": start_sample,
        "sent_chunks": 0,
        "send_errors": 0,
        "capture_bytes": 0,
        "started_at": time.time(),
        "started_monotonic": time.monotonic(),
        "last_pcm_monotonic": 0.0,
        "first_pcm_seen": False,
        "capture_stalled": False,
        "last_error": "",
        "test_asr_stall_active": False,
        "test_asr_stall_done": False,
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
                active and (
                    (first_pcm_seen and pcm_age > PCM_STALL_SEC)
                    or ((not first_pcm_seen) and pcm_age > PCM_STARTUP_GRACE_SEC)
                )
            )
            stats["capture_stalled"] = stalled
            captured = int(stats["sample_count"])
            cursor = int(stats["inference_cursor_sample"])
            backlog = max(0, captured - cursor)
            backlog_chunks = int(math.ceil(backlog / float(chunk_frames))) if backlog else 0
            return {
                "version": VERSION,
                "active": bool(active),
                "pid": os.getpid(),
                "session_id": sid,
                "sample_rate": args.rate,
                "channels": capture_channels,
                "clock_unit": "audio_frames",
                "sample_count": captured,
                "recording_time_sec": round(captured / float(args.rate), 6),
                # Backward-compatible names; beta's queue is a RAW-backed cursor.
                "queue_depth": backlog_chunks,
                "dropped_chunks": 0,
                "sent_chunks": int(stats["sent_chunks"]),
                "send_errors": int(stats["send_errors"]),
                "capture_bytes": int(stats["capture_bytes"]),
                "inference_cursor_sample": cursor,
                "inference_backlog_samples": backlog,
                "inference_backlog_sec": round(backlog / float(args.rate), 6),
                "first_pcm_seen": first_pcm_seen,
                "last_pcm_age_sec": round(pcm_age, 3),
                "capture_stalled": stalled,
                "test_asr_stall_active": bool(stats["test_asr_stall_active"]),
                "test_asr_stall_done": bool(stats["test_asr_stall_done"]),
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

    backend_chunk_url = args.backend_url.rstrip("/") + f"/api/chunk?session_id={sid}"
    backend_clock_url = args.backend_url.rstrip("/") + "/api/native/clock"

    def sender_loop():
        artificial_started = False
        while not sender_abort.is_set():
            snap = snapshot(True)
            elapsed = time.monotonic() - float(stats["started_monotonic"])

            if (
                args.test_asr_stall_sec > 0
                and not artificial_started
                and elapsed >= max(0.0, args.test_asr_stall_after_sec)
            ):
                artificial_started = True
                with lock:
                    stats["test_asr_stall_active"] = True
                print(
                    "[NATIVE ASR TEST] artificial inference stall",
                    f"seconds={args.test_asr_stall_sec:.3f}",
                    flush=True,
                )
                deadline = time.monotonic() + max(0.0, args.test_asr_stall_sec)
                while time.monotonic() < deadline and not sender_abort.is_set():
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                with lock:
                    stats["test_asr_stall_active"] = False
                    stats["test_asr_stall_done"] = True
                print("[NATIVE ASR TEST] artificial stall released", flush=True)
                continue

            captured = int(snap["sample_count"])
            cursor = int(snap["inference_cursor_sample"])
            available = max(0, captured - cursor)
            final_mode = sender_done.is_set()

            if available < chunk_frames and not (final_mode and available > 0):
                if final_mode and available <= 0:
                    break
                data_ready.wait(timeout=0.1)
                data_ready.clear()
                continue

            take = chunk_frames if available >= chunk_frames else available
            payload = read_pcm16_frames(raw_path, cursor, take, capture_channels)
            if len(payload) != take * frame_bytes:
                # Writer may have updated sample_count just before bytes became
                # visible to the separate reader. Never advance the cursor.
                time.sleep(0.01)
                continue

            attempts = 0
            sent = False
            while not sender_abort.is_set():
                try:
                    http_audio(backend_chunk_url, args.token, payload, cursor, capture_channels, timeout=30.0)
                    sent = True
                    break
                except urllib.error.HTTPError as exc:
                    # A 409 after explicit stop means Flask has closed ingest.
                    if exc.code == 409 and stop_event.is_set():
                        sender_abort.set()
                        break
                    attempts += 1
                    with lock:
                        stats["send_errors"] += 1
                        stats["last_error"] = f"audio HTTP {exc.code}"
                    if attempts >= 5:
                        print("[NATIVE ASR SEND RETRY]", repr(exc), flush=True)
                        attempts = 0
                        time.sleep(1.0)
                    else:
                        time.sleep(min(2.0, 0.2 * (2 ** attempts)))
                except Exception as exc:
                    attempts += 1
                    with lock:
                        stats["send_errors"] += 1
                        stats["last_error"] = repr(exc)
                    if attempts >= 5:
                        print("[NATIVE ASR SEND RETRY]", repr(exc), flush=True)
                        attempts = 0
                        time.sleep(1.0)
                    else:
                        time.sleep(min(2.0, 0.2 * (2 ** attempts)))

            if sent:
                with lock:
                    stats["inference_cursor_sample"] = cursor + take
                    stats["sent_chunks"] += 1
                save_status(True)

        print("[NATIVE ASR] RAW-backed sender stopped", flush=True)

    def heartbeat_loop():
        stall_reported = False
        while not stop_event.wait(0.5):
            snap = snapshot(True)
            if snap["capture_stalled"] and not stall_reported:
                stall_reported = True
                with lock:
                    stats["last_error"] = (
                        f"PCM stalled: no captured bytes for {snap['last_pcm_age_sec']:.3f}s"
                    )
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
                        "channels": capture_channels,
                        "clock_unit": "audio_frames",
                        "sample_count": snap["sample_count"],
                        "queue_depth": snap["queue_depth"],
                        "dropped_chunks": 0,
                        "pid": os.getpid(),
                        "last_pcm_age_sec": snap["last_pcm_age_sec"],
                        "capture_stalled": snap["capture_stalled"],
                        "inference_cursor_sample": snap["inference_cursor_sample"],
                        "inference_backlog_samples": snap["inference_backlog_samples"],
                        "inference_backlog_sec": snap["inference_backlog_sec"],
                        "test_asr_stall_active": snap["test_asr_stall_active"],
                        "test_asr_stall_done": snap["test_asr_stall_done"],
                    },
                    timeout=2.0,
                )
            except Exception as exc:
                with lock:
                    stats["last_error"] = f"clock heartbeat: {exc!r}"
            save_status(True)

    sender = threading.Thread(target=sender_loop, name="clova-native-asr-raw-cursor", daemon=True)
    heartbeat = threading.Thread(target=heartbeat_loop, name="clova-native-clock", daemon=True)
    sender.start()
    heartbeat.start()

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
        f"--channels={capture_channels}",
        "--format=s16",
        "--quality=10",
        "--latency=100ms",
    ]
    if args.target:
        cmd.append(f"--target={args.target}")
    cmd.append("-")

    print("[NATIVE CAPTURE]", " ".join(cmd[:-1]), "STDOUT", flush=True)
    pw_stderr_path = args.project_dir / "logs" / f"pw-record-v8.2-beta-{sid}.stderr.log"
    pw_stderr_path.parent.mkdir(parents=True, exist_ok=True)
    pw_stderr_log = pw_stderr_path.open("ab", buffering=0)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=pw_stderr_log, bufsize=0)

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
            even_len = (len(capture_buffer) // frame_bytes) * frame_bytes
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
            # Wake inference only after PCM is durably appended to RAW.
            data_ready.set()

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
        writer.close()
        data_ready.set()

        # Final clock is independent of inference drain.
        snap = snapshot(True)
        try:
            http_json(
                backend_clock_url,
                args.token,
                {
                    "session_id": sid,
                    "sample_count": snap["sample_count"],
                    "queue_depth": snap["queue_depth"],
                    "dropped_chunks": 0,
                    "pid": os.getpid(),
                    "last_pcm_age_sec": snap["last_pcm_age_sec"],
                    "capture_stalled": False,
                    "inference_cursor_sample": snap["inference_cursor_sample"],
                    "inference_backlog_samples": snap["inference_backlog_samples"],
                    "inference_backlog_sec": snap["inference_backlog_sec"],
                },
                timeout=2.0,
            )
        except Exception as exc:
            print("[NATIVE FINAL CLOCK WARN]", repr(exc), flush=True)

        # Allow the RAW-backed cursor to catch up. Capture integrity never waits
        # on this during recording; only explicit Finish gets a finite drain.
        sender_done.set()
        data_ready.set()
        deadline = time.monotonic() + max(0.0, args.shutdown_drain_sec)
        while sender.is_alive() and time.monotonic() < deadline:
            if snapshot(True)["inference_backlog_samples"] <= 0:
                break
            time.sleep(0.05)
        if sender.is_alive():
            sender_abort.set()
            data_ready.set()
        sender.join(timeout=2.0)

        # Publish the post-drain inference cursor while Flask still considers
        # the session recording. This makes finish metadata reflect whether the
        # transcript pipeline fully caught up or left a recoverable RAW backlog.
        final_snap = snapshot(True)
        try:
            http_json(
                backend_clock_url,
                args.token,
                {
                    "session_id": sid,
                    "channels": capture_channels,
                    "clock_unit": "audio_frames",
                    "sample_count": final_snap["sample_count"],
                    "queue_depth": final_snap["queue_depth"],
                    "dropped_chunks": 0,
                    "pid": os.getpid(),
                    "last_pcm_age_sec": final_snap["last_pcm_age_sec"],
                    "capture_stalled": False,
                    "inference_cursor_sample": final_snap["inference_cursor_sample"],
                    "inference_backlog_samples": final_snap["inference_backlog_samples"],
                    "inference_backlog_sec": final_snap["inference_backlog_sec"],
                    "test_asr_stall_active": final_snap["test_asr_stall_active"],
                    "test_asr_stall_done": final_snap["test_asr_stall_done"],
                },
                timeout=2.0,
            )
        except Exception as exc:
            print("[NATIVE POST-DRAIN CLOCK WARN]", repr(exc), flush=True)

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
        f"inference_cursor={snap['inference_cursor_sample']}",
        f"backlog_sec={snap['inference_backlog_sec']}",
        "dropped_asr_chunks=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
