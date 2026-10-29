import time
import requests
import numpy as np
import wave

BASE = "http://127.0.0.1:8000"
AUDIO = "audio/test.wav"
TITLE = "로보틱스 - Coordinate Frame과 Relative Pose"

SR = 16000

# 100 ms씩 전송
# 실제 microphone streaming과 비슷하게 작은 chunk 사용
CHUNK_SAMPLES = 1600


# =========================================================
# 1. Session start
# =========================================================

r = requests.post(
    f"{BASE}/api/start",
    json={
        "title": TITLE
    },
    timeout=30,
)

r.raise_for_status()

j = r.json()

sid = j["session_id"]

print()
print("========================================")
print("[START]")
print("session_id:", sid)
print("postprocess:", j.get("postprocess_status"))
print("========================================")


# =========================================================
# 2. WAV load
# =========================================================

with wave.open(AUDIO, "rb") as wf:

    sr = wf.getframerate()
    channels = wf.getnchannels()
    sample_width = wf.getsampwidth()
    frames = wf.readframes(
        wf.getnframes()
    )

if sample_width != 2:
    raise RuntimeError(
        f"expected 16-bit PCM WAV, "
        f"got {sample_width * 8}-bit"
    )

audio = np.frombuffer(
    frames,
    dtype="<i2",
).astype(np.float32)

audio /= 32768.0

if channels > 1:
    audio = audio.reshape(
        -1,
        channels,
    ).mean(axis=1)

audio = np.ascontiguousarray(
    audio,
    dtype=np.float32,
)

if sr != SR:
    raise RuntimeError(
        f"test.wav sample rate is {sr} Hz, "
        f"expected {SR} Hz"
    )

print(
    f"[AUDIO] {len(audio) / sr:.2f}s "
    f"/ {sr} Hz / {len(audio)} samples"
)


# =========================================================
# 3. Feed like microphone
# =========================================================

last_committed = ""

for n, start in enumerate(
    range(
        0,
        len(audio),
        CHUNK_SAMPLES,
    ),
    start=1,
):

    chunk = audio[
        start:
        start + CHUNK_SAMPLES
    ]

    # 서버는 raw float32 little-endian을 기대
    raw = (
        chunk
        .astype("<f4", copy=False)
        .tobytes()
    )

    r = requests.post(
        f"{BASE}/api/chunk",
        params={
            "session_id": sid
        },
        headers={
            "Content-Type":
                "application/octet-stream"
        },
        data=raw,
        timeout=300,
    )

    if not r.ok:
        print()
        print(
            "[CHUNK ERROR]",
            n,
            r.status_code,
            r.text,
        )
        raise SystemExit(1)

    j = r.json()

    committed = (
        j.get("committed_text")
        or ""
    )

    unfixed = (
        j.get("unfixed_text")
        or ""
    )

    if committed != last_committed:

        print()
        print(
            "[COMMITTED]"
        )

        print(committed)

        last_committed = committed

    if n % 10 == 0:

        sent_sec = min(
            start + len(chunk),
            len(audio),
        ) / SR

        print(
            f"[STREAM] {sent_sec:.1f}s "
            f"unfixed={unfixed!r}"
        )

    # 테스트에서는 굳이 realtime 속도로
    # sleep할 필요 없음.
    # 필요하면 아래 주석 해제:
    #
    # time.sleep(
    #     len(chunk) / SR
    # )


# =========================================================
# 4. Stop
# =========================================================

print()
print("========================================")
print("[STOP]")
print("========================================")

r = requests.post(
    f"{BASE}/api/finish",
    params={
        "session_id": sid
    },
    timeout=300,
)

r.raise_for_status()

stopped = r.json()

print(
    "postprocess_status:",
    stopped.get(
        "postprocess_status"
    )
)

print()
print(
    "[SENTENCE CORRECTED]"
)

print(
    stopped.get(
        "committed_text",
        ""
    )
)


# 여기서 반드시 not_run이어야 함
if (
    stopped.get(
        "postprocess_status"
    )
    != "not_run"
):

    print(
        "⚠️ unexpected postprocess state"
    )


# =========================================================
# 5. Lazy Postprocess
# =========================================================

print()
print("========================================")
print("[POSTPROCESS BUTTON]")
print("========================================")

r = requests.post(
    f"{BASE}/api/postprocess",
    params={
        "session_id": sid
    },
    timeout=600,
)

if not r.ok:

    print(
        "[POSTPROCESS ERROR]",
        r.status_code,
        r.text,
    )

    raise SystemExit(1)


final = r.json()

print(
    "postprocess_status:",
    final.get(
        "postprocess_status"
    )
)

print(
    "source:",
    final.get(
        "source"
    )
)

print()
print(
    "============== FINAL =============="
)

print(
    final.get(
        "whole_reviewed_text"
    )
    or final.get(
        "text",
        ""
    )
)

print(
    "==================================="
)

print()
print(
    "✅ V4 lifecycle complete"
)
print(
    "session_id:",
    sid
)
