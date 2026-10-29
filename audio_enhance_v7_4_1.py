"""Local Clova V7.4.1 lecture-audio enhancement.

Primary backend: the official DeepFilterNet v0.5.6 precompiled `deep-filter`
binary. The binary operates at 48 kHz, while Local Clova records at 16 kHz,
so this module performs a deterministic 16 -> 48 -> 16 kHz round trip and
forces the cleaned signal back to the exact original sample count.

If the neural backend is unavailable or fails for one segment, a conservative
stationary-noise Wiener/spectral-gate fallback is used. This keeps recording
usable even when the optional binary cannot run.
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

DF_SR = 48_000
DEFAULT_SR = 16_000
DEFAULT_DF_BIN = Path(
    os.getenv("DENOISE_BIN", "/workspace/tools/deep-filter")
)


def _float32_mono(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not np.all(np.isfinite(x)):
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(x, -1.0, 1.0)


def _match_length(audio: np.ndarray, target_len: int) -> np.ndarray:
    x = _float32_mono(audio)
    if len(x) > target_len:
        return x[:target_len].copy()
    if len(x) < target_len:
        return np.pad(x, (0, target_len - len(x))).astype(np.float32)
    return x.copy()


def _write_pcm16_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(pcm.tobytes())


def _read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sampwidth == 2:
        x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 4:
        x = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        x = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported WAV sample width: {sampwidth}")

    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)

    return _float32_mono(x), int(sr)


def _upsample_integer_linear(audio: np.ndarray, factor: int) -> np.ndarray:
    """Deterministic interpolation for 16 -> 48 kHz.

    Local Clova's source contains no information above 8 kHz. The neural model
    only needs a valid 48 kHz waveform, so interpolation is sufficient on the
    way up. The return path uses an anti-alias FIR before decimation.
    """
    x = _float32_mono(audio)
    if factor == 1 or len(x) < 2:
        return x.copy()
    old = np.arange(len(x), dtype=np.float64)
    new = np.arange(len(x) * factor, dtype=np.float64) / float(factor)
    y = np.interp(new, old, x, left=float(x[0]), right=float(x[-1]))
    return y.astype(np.float32)


def _lowpass_for_decimation(audio: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return _float32_mono(audio)

    # 127-tap windowed-sinc filter. For factor=3 at 48 kHz this places the
    # cutoff safely below the new 8 kHz Nyquist limit.
    taps = 127
    half = taps // 2
    n = np.arange(-half, half + 1, dtype=np.float64)
    cutoff_cycles = 0.158  # ~= 7.58 kHz / 48 kHz
    h = 2.0 * cutoff_cycles * np.sinc(2.0 * cutoff_cycles * n)
    h *= np.hanning(taps)
    h /= np.sum(h)
    return np.convolve(_float32_mono(audio), h.astype(np.float32), mode="same").astype(np.float32)


def _resample(audio: np.ndarray, src_sr: int, dst_sr: int, target_len: int | None = None) -> np.ndarray:
    if src_sr == dst_sr:
        out = _float32_mono(audio)
    elif dst_sr == src_sr * 3:
        out = _upsample_integer_linear(audio, 3)
    elif src_sr == dst_sr * 3:
        filtered = _lowpass_for_decimation(audio, 3)
        out = filtered[::3].astype(np.float32)
    else:
        # Generic linear fallback for unexpected rates.
        x = _float32_mono(audio)
        out_len = max(1, int(round(len(x) * float(dst_sr) / float(src_sr))))
        old = np.arange(len(x), dtype=np.float64)
        new = np.arange(out_len, dtype=np.float64) * float(src_sr) / float(dst_sr)
        out = np.interp(new, old, x, left=float(x[0]) if len(x) else 0.0,
                        right=float(x[-1]) if len(x) else 0.0).astype(np.float32)

    if target_len is not None:
        out = _match_length(out, int(target_len))
    return out


def _frame_signal(x: np.ndarray, frame: int, hop: int) -> tuple[np.ndarray, int]:
    if len(x) == 0:
        return np.zeros((1, frame), dtype=np.float32), 0
    n_frames = max(1, int(math.ceil(max(0, len(x) - frame) / hop)) + 1)
    padded_len = (n_frames - 1) * hop + frame
    padded = np.pad(x, (0, max(0, padded_len - len(x))))
    frames = np.stack([padded[i * hop:i * hop + frame] for i in range(n_frames)], axis=0)
    return frames.astype(np.float32), len(x)


def _adaptive_wiener_fallback(audio: np.ndarray, sr: int) -> np.ndarray:
    """Conservative stationary-noise suppression with no extra dependencies.

    Noise PSD is estimated from the quietest 20% of frames. A smoothed Wiener
    gain attenuates fan/air-conditioner style stationary noise while keeping a
    non-zero floor so consonants are not aggressively erased.
    """
    x = _float32_mono(audio)
    if len(x) < max(256, int(sr * 0.08)):
        return x.copy()

    frame = max(256, int(round(sr * 0.032)))
    # FFT efficiency without making frame excessively large.
    frame = 1 << int(math.ceil(math.log2(frame)))
    hop = max(64, int(round(sr * 0.010)))
    frames, orig_len = _frame_signal(x, frame, hop)

    win = np.sqrt(np.hanning(frame).astype(np.float32) + 1e-8)
    windowed = frames * win[None, :]
    spec = np.fft.rfft(windowed, axis=1)
    power = np.abs(spec) ** 2

    energy = np.mean(frames * frames, axis=1) + 1e-12
    quiet_count = max(1, int(math.ceil(len(frames) * 0.20)))
    quiet_idx = np.argpartition(energy, quiet_count - 1)[:quiet_count]
    noise_psd = np.median(power[quiet_idx], axis=0) + 1e-12

    # Wiener-like gain. Limit attenuation to around -18 dB so speech remains
    # intelligible even if the noise estimate contains a little speech.
    snr = np.maximum(power - noise_psd[None, :], 0.0) / noise_psd[None, :]
    gain = snr / (snr + 1.0)
    floor = 10.0 ** (-18.0 / 20.0)
    gain = np.clip(gain, floor, 1.0)

    # Smooth in frequency and time to reduce musical-noise artifacts.
    if gain.shape[1] >= 5:
        kernel = np.array([1, 2, 3, 2, 1], dtype=np.float32) / 9.0
        gain = np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="same"), 1, gain)
    if len(gain) > 1:
        smooth = gain.copy()
        alpha = 0.72
        for i in range(1, len(smooth)):
            smooth[i] = alpha * smooth[i - 1] + (1.0 - alpha) * smooth[i]
        gain = smooth

    cleaned_spec = spec * gain
    cleaned_frames = np.fft.irfft(cleaned_spec, n=frame, axis=1).astype(np.float32) * win[None, :]

    out_len = (len(cleaned_frames) - 1) * hop + frame
    out = np.zeros(out_len, dtype=np.float32)
    weight = np.zeros(out_len, dtype=np.float32)
    w2 = win * win
    for i, fr in enumerate(cleaned_frames):
        start = i * hop
        out[start:start + frame] += fr
        weight[start:start + frame] += w2
    nz = weight > 1e-7
    out[nz] /= weight[nz]
    out = out[:orig_len]

    # No loudness normalization: preserve the recording's level relationship.
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def _deepfilternet_enhance(
    audio: np.ndarray,
    sr: int,
    *,
    binary: Path,
    work_root: Path | None,
    timeout_sec: float,
    post_filter: bool,
    pf_beta: float,
    atten_lim_db: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if sr <= 0:
        raise ValueError("invalid sample rate")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(f"DeepFilterNet binary not executable: {binary}")

    raw = _float32_mono(audio)
    target_len = len(raw)
    dfn_in = _resample(raw, sr, DF_SR)

    parent = Path(work_root) if work_root else None
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="clova-dfn-", dir=str(parent) if parent else None) as td:
        td_path = Path(td)
        inp = td_path / "input.wav"
        out_dir = td_path / "out"
        out_dir.mkdir()
        _write_pcm16_wav(inp, dfn_in, DF_SR)

        # Strong lecture profile. DeepFilterNet already defaults to a 100 dB
        # attenuation limit (effectively uncapped); the post-filter is the
        # intended control for stronger attenuation of noisy regions.
        common = [str(binary), "-D", "-o", str(out_dir)]
        tuning = []
        if post_filter:
            tuning.extend(["--pf", "--pf-beta", f"{float(pf_beta):.4f}"])
        tuning.extend(["--atten-lim-db", f"{float(atten_lim_db):.1f}"])
        proc = subprocess.run(
            common + tuning + [str(inp)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=float(timeout_sec),
            check=False,
        )
        compatibility_retry = False
        if proc.returncode != 0:
            msg = (proc.stdout or "").lower()
            option_error = any(token in msg for token in (
                "unexpected argument", "unknown argument", "unrecognized option",
                "found argument", "invalid option",
            ))
            if option_error and post_filter:
                compatibility_retry = True
                for old_wav in out_dir.glob("*.wav"):
                    old_wav.unlink(missing_ok=True)
                proc = subprocess.run(
                    common + ["--pf", str(inp)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=float(timeout_sec),
                    check=False,
                )
        if proc.returncode != 0:
            tail = (proc.stdout or "")[-1200:]
            raise RuntimeError(f"deep-filter exit={proc.returncode}: {tail}")

        outputs = sorted(out_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime_ns)
        if not outputs:
            raise RuntimeError("deep-filter produced no WAV output")

        enhanced_48, out_sr = _read_wav_mono(outputs[-1])
        if out_sr != DF_SR:
            enhanced_48 = _resample(enhanced_48, out_sr, DF_SR)

    cleaned = _resample(enhanced_48, DF_SR, sr, target_len=target_len)
    return np.clip(cleaned, -1.0, 1.0).astype(np.float32), {
        "post_filter": bool(post_filter),
        "pf_beta": float(pf_beta),
        "atten_lim_db": float(atten_lim_db),
        "compatibility_retry": bool(compatibility_retry),
    }


def enhance_segment(
    audio: np.ndarray,
    *,
    sr: int = DEFAULT_SR,
    binary: str | os.PathLike[str] | None = None,
    work_root: str | os.PathLike[str] | None = None,
    enabled: bool = True,
    timeout_sec: float = 90.0,
    post_filter: bool = True,
    pf_beta: float = 0.04,
    atten_lim_db: float = 100.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return a time-preserving cleaned waveform and audit metadata."""
    raw = _float32_mono(audio)
    target_len = len(raw)
    started = __import__("time").monotonic()

    if not enabled or target_len == 0:
        return raw.copy(), {
            "status": "bypassed",
            "backend": "none",
            "model": None,
            "input_samples": target_len,
            "output_samples": target_len,
            "duration_preserved": True,
            "elapsed_sec": 0.0,
        }

    bin_path = Path(binary) if binary is not None else DEFAULT_DF_BIN
    root_path = Path(work_root) if work_root is not None else None

    try:
        cleaned, neural_meta = _deepfilternet_enhance(
            raw,
            int(sr),
            binary=bin_path,
            work_root=root_path,
            timeout_sec=timeout_sec,
            post_filter=bool(post_filter),
            pf_beta=float(pf_beta),
            atten_lim_db=float(atten_lim_db),
        )
        backend = "deepfilternet"
        model = "DeepFilterNet2-v0.5.6"
        status = "ok"
        error = None
    except Exception as exc:
        neural_meta = {}
        cleaned = _adaptive_wiener_fallback(raw, int(sr))
        backend = "adaptive-wiener-fallback"
        model = None
        status = "fallback"
        error = repr(exc)

    cleaned = _match_length(cleaned, target_len)
    elapsed = __import__("time").monotonic() - started
    return cleaned, {
        "status": status,
        "backend": backend,
        "model": model,
        "error": error,
        "input_samples": target_len,
        "output_samples": len(cleaned),
        "duration_preserved": len(cleaned) == target_len,
        "sample_rate": int(sr),
        "elapsed_sec": round(float(elapsed), 4),
        "profile": "strong-pf" if backend == "deepfilternet" and post_filter else "default",
        "post_filter": bool(neural_meta.get("post_filter", False)),
        "pf_beta": neural_meta.get("pf_beta"),
        "atten_lim_db": neural_meta.get("atten_lim_db"),
        "compatibility_retry": bool(neural_meta.get("compatibility_retry", False)),
    }


__all__ = ["enhance_segment"]
