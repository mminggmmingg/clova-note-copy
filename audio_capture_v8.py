"""V8 audio provenance helpers.

Small, dependency-light helpers used by Local Clova V8.0-alpha.1.
- browser DSP is disabled in the frontend
- every accepted /api/chunk sample is appended to one continuous PCM16 WAV
- WAV header is updated on every append so the file remains playable after a crash
"""

from pathlib import Path
import struct

import numpy as np

VALID_STT_AUDIO_SOURCES = {"raw", "clean"}


def normalize_stt_audio_source(value, default="raw"):
    value = str(value or "").strip().lower()
    if value in VALID_STT_AUDIO_SOURCES:
        return value
    return default if default in VALID_STT_AUDIO_SOURCES else "raw"


def _pcm16_bytes(audio):
    pcm16 = (
        np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
        * 32767.0
    ).astype("<i2", copy=False)
    return pcm16.tobytes(order="C")


def _header(*, sample_rate, data_bytes):
    channels = 1
    bits = 16
    block_align = channels * bits // 8
    byte_rate = sample_rate * block_align
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + int(data_bytes),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        int(sample_rate),
        int(byte_rate),
        int(block_align),
        bits,
        b"data",
        int(data_bytes),
    )


def append_float32_mono_wav(path, audio, *, sample_rate=16000):
    """Append float32 mono samples to a standard PCM16 WAV.

    The file is closed after each append and its RIFF/data lengths are updated,
    so it stays readable even if the process exits unexpectedly later.
    Returns the number of appended samples.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _pcm16_bytes(audio)
    samples = len(payload) // 2
    if not samples:
        return 0

    if not path.exists() or path.stat().st_size < 44:
        with path.open("wb") as f:
            f.write(_header(sample_rate=sample_rate, data_bytes=0))

    with path.open("r+b") as f:
        f.seek(0, 2)
        if f.tell() < 44:
            f.seek(0)
            f.write(_header(sample_rate=sample_rate, data_bytes=0))
            f.seek(44)
        f.write(payload)
        end = f.tell()
        data_bytes = max(0, end - 44)
        f.seek(0)
        f.write(_header(sample_rate=sample_rate, data_bytes=data_bytes))
        f.flush()

    return samples


def wav_frame_count(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size < 44:
        return 0
    # Local Clova writes standard 44-byte PCM16 mono WAVs here.
    return max(0, path.stat().st_size - 44) // 2
