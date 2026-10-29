import argparse
import threading
import uuid
import json
import wave
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import torch

# gfx1151 MIOpen Conv2D 문제 우회
torch.backends.cudnn.enabled = False

from flask import jsonify, request
from silero_vad import load_silero_vad, VADIterator
from qwen_asr import Qwen3ASRModel
from qwen_asr.cli import demo_streaming as demo


SR = 16000
VAD_FRAME = 512

DATA_DIR = Path("/workspace/data")
SEGMENT_DIR = DATA_DIR / "segments"
TRANSCRIPT_FILE = DATA_DIR / "transcript.jsonl"

SEGMENT_DIR.mkdir(parents=True, exist_ok=True)

VAD_THRESHOLD = 0.50
MIN_SILENCE_MS = 700
SPEECH_PAD_MS = 100

MAX_UTTERANCE_SEC = 20.0
PREROLL_SEC = 0.5

UNFIXED_CHUNK_NUM = 4
UNFIXED_TOKEN_NUM = 5
CHUNK_SIZE_SEC = 1.0

FORCE_LANGUAGE = "Korean"

DOMAIN_CONTEXT = """
This is a Korean university robotics lecture.

Preserve English technical terms in their original English spelling
when they are spoken in English.

Important terminology:
robotics,
relative pose,
absolute pose,
reference frame,
world frame,
body frame,
coordinate frame,
R frame,
W frame,
represented in W frame,
with respect to,
position,
orientation,
rotation,
rotation matrix,
transformation,
transformation matrix,
homogeneous transformation,
translation,
notation,
representation,
coordinate system,
SE(3),
SO(3),
Peter Corke.

The lecturer primarily speaks Korean but frequently mixes English
robotics and mathematics terminology.
""".strip()


asr = None
SESSIONS = {}


def new_qwen_state():
    return asr.init_streaming_state(
        context=DOMAIN_CONTEXT,
        language=FORCE_LANGUAGE,
        unfixed_chunk_num=UNFIXED_CHUNK_NUM,
        unfixed_token_num=UNFIXED_TOKEN_NUM,
        chunk_size_sec=CHUNK_SIZE_SEC,
    )


def new_vad():
    # 세션별 VAD state를 독립적으로 유지
    model = load_silero_vad(onnx=True)

    return VADIterator(
        model,
        threshold=VAD_THRESHOLD,
        sampling_rate=SR,
        min_silence_duration_ms=MIN_SILENCE_MS,
        speech_pad_ms=SPEECH_PAD_MS,
    )


@dataclass
class Session:
    qwen_state: object
    vad: object

    vad_buffer: np.ndarray = field(
        default_factory=lambda: np.empty(0, dtype=np.float32)
    )

    preroll: np.ndarray = field(
        default_factory=lambda: np.empty(0, dtype=np.float32)
    )

    segment_audio: np.ndarray = field(
        default_factory=lambda: np.empty(0, dtype=np.float32)
    )

    committed: list = field(default_factory=list)

    segment_index: int = 0

    active: bool = False
    active_samples: int = 0
    language: str = ""

    lock: object = field(default_factory=threading.Lock)


def feed_vad(session, wav):
    """
    Silero VAD는 16kHz에서 512 sample 단위로 처리.
    start / end 이벤트를 찾아 반환.
    """
    session.vad_buffer = np.concatenate(
        [session.vad_buffer, wav]
    )

    speech_start = False
    speech_end = False

    while len(session.vad_buffer) >= VAD_FRAME:
        frame = session.vad_buffer[:VAD_FRAME].copy()
        session.vad_buffer = session.vad_buffer[VAD_FRAME:]

        event = session.vad(
            torch.from_numpy(frame),
            return_seconds=False,
        )

        if event:
            if "start" in event:
                speech_start = True
                print(
                    f"[VAD] speech start @ {event['start']}",
                    flush=True,
                )

            if "end" in event:
                speech_end = True
                print(
                    f"[VAD] speech end @ {event['end']}",
                    flush=True,
                )

    return speech_start, speech_end


def get_partial(session):
    if not session.active:
        return ""

    return (
        getattr(session.qwen_state, "text", "")
        or ""
    ).strip()


def full_text(session):
    pieces = list(session.committed)

    partial = get_partial(session)

    if partial:
        pieces.append(partial)

    return "\n".join(pieces)


def save_segment(session, text, language):
    """
    확정된 발화의 원본 audio + transcript를 저장한다.

    WAV:
      /workspace/data/segments/000001.wav

    Metadata:
      /workspace/data/transcript.jsonl
    """
    audio = session.segment_audio

    if audio is None or len(audio) == 0:
        return

    session.segment_index += 1

    idx = session.segment_index
    filename = f"{idx:06d}.wav"
    wav_path = SEGMENT_DIR / filename

    # float32 [-1,1] -> PCM16
    pcm16 = (
        np.clip(audio, -1.0, 1.0) * 32767.0
    ).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm16.tobytes())

    duration = len(audio) / SR

    record = {
        "segment": idx,
        "audio": str(wav_path.relative_to(DATA_DIR)),
        "duration_sec": round(duration, 3),
        "sample_rate": SR,
        "language": language or FORCE_LANGUAGE,
        "text": text,
        "created_at": datetime.now().isoformat(),
    }

    with TRANSCRIPT_FILE.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        )

    print(
        f"[SAVED] {wav_path} ({duration:.2f}s)",
        flush=True,
    )


def refine_segment(session, fallback_text):
    """
    Streaming 결과를 그대로 확정하지 않고,
    VAD가 모은 전체 발화를 Qwen3-ASR offline mode로
    한 번 더 인식한다.
    """
    audio = session.segment_audio

    if audio is None or len(audio) < int(SR * 0.25):
        return fallback_text

    try:
        duration = len(audio) / SR

        print(
            f"[REFINE] offline pass: {duration:.2f}s",
            flush=True,
        )

        result = asr.transcribe(
            audio=(audio, SR),
            context=DOMAIN_CONTEXT,
            language=FORCE_LANGUAGE,
            return_time_stamps=False,
        )[0]

        refined = (result.text or "").strip()

        if refined:
            session.language = result.language or FORCE_LANGUAGE

            print(
                "[REFINED]",
                refined,
                flush=True,
            )

            return refined

    except Exception as e:
        print(
            "[REFINE ERROR]",
            repr(e),
            flush=True,
        )

    return fallback_text


def finalize_segment(session, silence_end=True):
    """
    현재 Qwen streaming state를 확정하고
    committed transcript에 저장.
    """
    if session.active:
        asr.finish_streaming_transcribe(
            session.qwen_state
        )

        stream_text = (
            getattr(session.qwen_state, "text", "")
            or ""
        ).strip()

        text = refine_segment(
            session,
            fallback_text=stream_text,
        )

        language = (
            getattr(session.qwen_state, "language", "")
            or ""
        )

        if language:
            session.language = language

        if text:
            # 똑같은 segment가 실수로 두 번 commit되는 것 방지
            if (
                not session.committed
                or session.committed[-1] != text
            ):
                session.committed.append(text)

                save_segment(
                    session,
                    text=text,
                    language=session.language,
                )

            print(
                "[COMMIT]",
                text,
                flush=True,
            )

    # Qwen state는 항상 새로 만든다
    session.qwen_state = new_qwen_state()
    session.active_samples = 0
    session.segment_audio = np.empty(
        0,
        dtype=np.float32,
    )

    if silence_end:
        # 실제 발화가 끝난 경우 VAD까지 초기화
        session.active = False
        session.vad.reset_states()
        session.vad_buffer = np.empty(
            0,
            dtype=np.float32,
        )

    else:
        # 20초 강제 cut.
        # 사람은 계속 말하고 있으므로 VAD active 상태는 유지.
        session.active = True


def api_start():
    sid = uuid.uuid4().hex

    SESSIONS[sid] = Session(
        qwen_state=new_qwen_state(),
        vad=new_vad(),
    )

    print(f"[SESSION] start {sid}", flush=True)

    return jsonify({
        "session_id": sid
    })


def api_chunk():
    sid = request.args.get("session_id", "")

    session = SESSIONS.get(sid)

    if session is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

    raw = request.get_data(cache=False)

    if len(raw) % 4:
        return jsonify({
            "error": "bad float32 payload"
        }), 400

    wav = np.frombuffer(
        raw,
        dtype=np.float32,
    ).copy()

    with session.lock:

        speech_start, speech_end = feed_vad(
            session,
            wav,
        )

        #
        # 아직 발화 전
        #
        if not session.active:

            if speech_start:
                session.active = True

                # 문장 첫 음절이 잘리지 않게
                # 직전 0.5초를 함께 Qwen에 전달
                if len(session.preroll):
                    qwen_audio = np.concatenate(
                        [session.preroll, wav]
                    )
                else:
                    qwen_audio = wav

                session.preroll = np.empty(
                    0,
                    dtype=np.float32,
                )

                session.segment_audio = qwen_audio.copy()

                asr.streaming_transcribe(
                    qwen_audio,
                    session.qwen_state,
                )

                session.active_samples += len(
                    qwen_audio
                )

            else:
                #
                # 아직 silence.
                # 최대 0.5초만 pre-roll로 보관.
                #
                max_pre = int(
                    SR * PREROLL_SEC
                )

                session.preroll = np.concatenate(
                    [session.preroll, wav]
                )[-max_pre:]

        #
        # 이미 발화 중
        #
        else:
            session.segment_audio = np.concatenate(
                [session.segment_audio, wav]
            )

            asr.streaming_transcribe(
                wav,
                session.qwen_state,
            )

            session.active_samples += len(wav)

        #
        # silence로 발화 종료
        #
        if session.active and speech_end:

            finalize_segment(
                session,
                silence_end=True,
            )

            # 다음 speech의 자연스러운 시작을 위해
            # 현재 silence tail 일부 보존
            max_pre = int(
                SR * PREROLL_SEC
            )

            session.preroll = wav[-max_pre:].copy()

        #
        # 교수님이 쉬지 않고 계속 말하는 경우
        # 20초마다 ASR state만 강제로 분할
        #
        elif (
            session.active
            and session.active_samples
            >= int(SR * MAX_UTTERANCE_SEC)
        ):
            print(
                "[FORCED SPLIT] 20 sec",
                flush=True,
            )

            finalize_segment(
                session,
                silence_end=False,
            )

        return jsonify({
            "language": session.language
                or (
                    getattr(
                        session.qwen_state,
                        "language",
                        "",
                    )
                    or ""
                ),

            # 기존 공식 UI와 호환
            "text": full_text(session),

            # 앞으로 우리 UI에서 사용할 값
            "committed_text":
                "\n".join(session.committed),

            "unfixed_text":
                get_partial(session),

            "vad_active":
                session.active,
        })


def api_finish():
    sid = request.args.get("session_id", "")

    session = SESSIONS.get(sid)

    if session is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

    with session.lock:

        if session.active:
            finalize_segment(
                session,
                silence_end=True,
            )

        result = {
            "language": session.language,
            "text": "\n".join(
                session.committed
            ),
            "committed_text": "\n".join(
                session.committed
            ),
            "unfixed_text": "",
            "vad_active": False,
        }

    SESSIONS.pop(sid, None)

    print(
        f"[SESSION] finish {sid}",
        flush=True,
    )

    return jsonify(result)


def main():
    global asr

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        default="/workspace/Qwen3-ASR-1.7B",
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
    )

    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=0.15,
    )

    args = parser.parse_args()

    print(
        "[clova-note] MIOpen disabled:",
        not torch.backends.cudnn.enabled,
        flush=True,
    )

    print(
        "[clova-note] Loading Qwen3-ASR...",
        flush=True,
    )

    asr = Qwen3ASRModel.LLM(
        model=args.model,
        gpu_memory_utilization=
            args.gpu_memory_utilization,
        max_new_tokens=96,
        enforce_eager=True,
    )

    print(
        "[clova-note] Qwen loaded",
        flush=True,
    )

    # 공식 Qwen demo UI는 그대로 사용하고
    # backend endpoint만 교체한다.
    demo.app.view_functions[
        "api_start"
    ] = api_start

    demo.app.view_functions[
        "api_chunk"
    ] = api_chunk

    demo.app.view_functions[
        "api_finish"
    ] = api_finish

    demo.app.run(
        host=args.host,
        port=args.port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    main()
