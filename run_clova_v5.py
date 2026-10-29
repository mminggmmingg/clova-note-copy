import os
import json
import wave
import uuid
import threading
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import requests
import torch

# ---------------------------------------------------------
# gfx1151 / Strix Halo workaround
# ---------------------------------------------------------

torch.backends.cudnn.enabled = False

from flask import Response, jsonify, request
from silero_vad import load_silero_vad, VADIterator

from transformers import (
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
    pipeline,
)

from qwen_asr import Qwen3ASRModel
from qwen_asr.cli import demo_streaming as demo


# =========================================================
# CONFIG
# =========================================================

SR = 16000
VAD_FRAME = 512

VAD_THRESHOLD = 0.50
MIN_SILENCE_MS = 850
SPEECH_PAD_MS = 120

PREROLL_SEC = 0.35

# Qwen streaming state는 너무 길어지면 degeneration 가능
QWEN_MAX_STATE_SEC = 18.0

UNFIXED_CHUNK_NUM = 4
UNFIXED_TOKEN_NUM = 5
CHUNK_SIZE_SEC = 1.0

FORCE_LANGUAGE = "Korean"

QWEN_ASR_MODEL = "/workspace/Qwen3-ASR-1.7B"
WHISPER_MODEL = "/workspace/whisper-large-v3"

DATA_ROOT = Path("/workspace/data/sessions")
DATA_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# Large LLM
#
# 예:
#
# export LLM_BASE_URL=http://192.168.1.20:8100
# export LLM_MODEL=Qwen3.8-Flash-Next
# ---------------------------------------------------------

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "",
).rstrip("/")

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "Qwen3.8-Flash-Next",
)


DOMAIN_CONTEXT = """
This is a Korean university robotics lecture.

The lecturer primarily speaks Korean and frequently mixes
English robotics, mathematics, and engineering terminology.

Important terminology may include:

robotics
coordinate frame
reference frame
world frame
body frame
relative pose
absolute pose
representation
notation
rotation
rotation matrix
orientation
translation
transformation
homogeneous transformation
SE(3)
SO(3)
R theta
R p
W p
Peter Corke
affine

Preserve English technical terms when they were spoken in English.
""".strip()


# =========================================================
# GLOBAL MODELS
# =========================================================

qwen_asr = None
whisper_pipe = None

SESSIONS = {}


# =========================================================
# SESSION
# =========================================================

@dataclass
class Session:

    session_id: str
    title: str
    root: Path

    qwen_state: object
    vad: object

    vad_buffer: np.ndarray = field(
        default_factory=lambda:
        np.empty(0, dtype=np.float32)
    )

    preroll: np.ndarray = field(
        default_factory=lambda:
        np.empty(0, dtype=np.float32)
    )

    # Whisper에 보낼 "문장" 전체 오디오
    sentence_audio: np.ndarray = field(
        default_factory=lambda:
        np.empty(0, dtype=np.float32)
    )

    # Qwen은 긴 발화 중간에 state를 reset할 수 있으므로
    # 여러 조각을 보관
    qwen_parts: list = field(default_factory=list)

    committed: list = field(default_factory=list)

    # 전체 세션 후처리 상태
    # not_run / running / done / error
    postprocess_status: str = "not_run"

    # whole-session Qwen3.8 결과
    whole_reviewed_text: str = ""

    # 녹음 중인지 여부
    recording: bool = True

    active: bool = False
    qwen_samples: int = 0

    segment_index: int = 0

    lock: object = field(
        default_factory=threading.Lock
    )


# =========================================================
# QWEN
# =========================================================

def qwen_context(title):

    return (
        f"SESSION TITLE:\n{title}\n\n"
        f"{DOMAIN_CONTEXT}"
    )


def new_qwen_state(title):

    return qwen_asr.init_streaming_state(
        context=qwen_context(title),
        language=FORCE_LANGUAGE,
        unfixed_chunk_num=UNFIXED_CHUNK_NUM,
        unfixed_token_num=UNFIXED_TOKEN_NUM,
        chunk_size_sec=CHUNK_SIZE_SEC,
    )


def current_qwen_piece(s):

    return (
        getattr(
            s.qwen_state,
            "text",
            "",
        )
        or ""
    ).strip()


def current_qwen_text(s):

    pieces = list(s.qwen_parts)

    current = current_qwen_piece(s)

    if current:
        pieces.append(current)

    return " ".join(
        x for x in pieces if x
    ).strip()


def reset_qwen_state(s):

    s.qwen_state = new_qwen_state(
        s.title
    )

    s.qwen_samples = 0


def split_qwen_state(s):
    """
    교수님이 아주 오래 쉬지 않고 말할 경우
    Whisper sentence는 유지하면서
    Qwen streaming state만 끊는다.
    """

    qwen_asr.finish_streaming_transcribe(
        s.qwen_state
    )

    piece = current_qwen_piece(s)

    if piece:
        s.qwen_parts.append(piece)

    print(
        "[QWEN STATE SPLIT]",
        piece,
        flush=True,
    )

    reset_qwen_state(s)


# =========================================================
# VAD
# =========================================================

def new_vad():

    model = load_silero_vad(
        onnx=True
    )

    return VADIterator(
        model,
        threshold=VAD_THRESHOLD,
        sampling_rate=SR,
        min_silence_duration_ms=MIN_SILENCE_MS,
        speech_pad_ms=SPEECH_PAD_MS,
    )


def feed_vad(s, wav):

    s.vad_buffer = np.concatenate(
        [
            s.vad_buffer,
            wav,
        ]
    )

    start = False
    end = False

    while len(s.vad_buffer) >= VAD_FRAME:

        frame = s.vad_buffer[
            :VAD_FRAME
        ].copy()

        s.vad_buffer = s.vad_buffer[
            VAD_FRAME:
        ]

        event = s.vad(
            torch.from_numpy(frame),
            return_seconds=False,
        )

        if not event:
            continue

        if "start" in event:

            start = True

            print(
                "[VAD] start",
                event["start"],
                flush=True,
            )

        if "end" in event:

            end = True

            print(
                "[VAD] end",
                event["end"],
                flush=True,
            )

    return start, end


# =========================================================
# WHISPER
# =========================================================

def whisper_transcribe(audio):

    if audio is None or len(audio) == 0:
        return ""

    duration = len(audio) / SR

    print(
        f"[WHISPER] {duration:.2f}s",
        flush=True,
    )

    result = whisper_pipe(
        {
            "array": audio,
            "sampling_rate": SR,
        },
        generate_kwargs={
            "language": "korean",
            "task": "transcribe",
        },
    )

    text = (
        result.get(
            "text",
            "",
        )
        or ""
    ).strip()

    print(
        "[WHISPER RAW]",
        text,
        flush=True,
    )

    return text


# =========================================================
# LARGE LLM CORRECTION
# =========================================================

SYSTEM_PROMPT = """
You are an ASR transcription correction engine.

Your task is ONLY to correct speech recognition errors.

Allowed:
- fix obvious ASR mistakes
- restore technical terminology
- restore English words spoken in English
- normalize mathematical notation when strongly supported
- add punctuation

Forbidden:
- summarize
- explain
- add information
- remove substantive information
- rewrite into nicer prose
- guess facts that were not spoken

If uncertain, preserve the original wording.

Use the Qwen ASR hypothesis and Whisper hypothesis as two noisy
observations of the same audio.

Output ONLY the corrected transcript.
No explanation.
""".strip()


def llm_correct(
    s,
    qwen_raw,
    whisper_raw,
):

    if not LLM_BASE_URL:

        print(
            "[LLM] disabled -> Whisper final",
            flush=True,
        )

        return (
            whisper_raw or qwen_raw,
            "whisper",
        )

    previous = "\n".join(
        s.committed[-3:]
    )

    user_prompt = f"""
SESSION TITLE:
{s.title}

DOMAIN:
Korean university robotics lecture

PREVIOUS CONFIRMED TRANSCRIPT:
{previous if previous else "(none)"}

QWEN ASR:
{qwen_raw}

WHISPER ASR:
{whisper_raw}

Correct the CURRENT utterance only.
""".strip()

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }

    try:

        print(
            "[LLM] correcting...",
            flush=True,
        )

        r = requests.post(
            f"{LLM_BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=90,
        )

        r.raise_for_status()

        corrected = (
            r.json()
            ["choices"][0]
            ["message"]
            ["content"]
        ).strip()

        base = (
            whisper_raw
            or qwen_raw
        ).strip()

        if not corrected:
            raise RuntimeError(
                "empty LLM output"
            )

        # -------------------------------------------------
        # 아주 단순하지만 중요한 hallucination guard.
        #
        # ASR 교정인데 길이가 갑자기 절반 이하가 되거나
        # 1.7배 이상 늘어나면 일단 reject.
        # -------------------------------------------------

        if base:

            ratio = (
                len(corrected)
                / max(1, len(base))
            )

            if (
                ratio < 0.50
                or ratio > 1.70
            ):

                print(
                    "[LLM REJECT] length ratio:",
                    round(ratio, 2),
                    flush=True,
                )

                return (
                    base,
                    "whisper",
                )

        print(
            "[LLM CORRECTED]",
            corrected,
            flush=True,
        )

        return (
            corrected,
            "llm",
        )

    except Exception as e:

        print(
            "[LLM ERROR]",
            repr(e),
            flush=True,
        )

        return (
            whisper_raw or qwen_raw,
            "whisper",
        )


# =========================================================
# WHOLE-SESSION POSTPROCESS
# =========================================================

WHOLE_SESSION_SYSTEM_PROMPT = """
You are performing the FINAL review of an ASR transcript.

The transcript is from one recording session.

Your ONLY task is to correct transcription errors using the
full-session context.

Allowed:
- correct obvious ASR errors
- restore technical terminology
- restore English terms spoken in English
- normalize mathematical notation such as SO(3), SE(3), R, T
- correct Korean/English mixed transcription
- add punctuation
- use earlier/later sentences to resolve ambiguous ASR words

Forbidden:
- summarize
- explain
- add new information
- remove substantive information
- rewrite into polished prose
- change the lecturer's meaning
- invent material

If uncertain, preserve the existing transcript.

Output ONLY the complete corrected transcript.
No markdown.
No explanation.
""".strip()


def whole_session_review(title, transcript):

    if not transcript.strip():
        return transcript, "sentence-pass"

    if not LLM_BASE_URL:
        raise RuntimeError(
            "LLM_BASE_URL is not configured"
        )

    prompt = f"""
SESSION TITLE:
{title}

FULL TRANSCRIPT:
{transcript}

Review the complete transcript using the session title and
surrounding sentences only to resolve ASR errors and technical
terminology.

Return the COMPLETE corrected transcript only.
""".strip()

    payload = {
        "model": LLM_MODEL,

        "messages": [
            {
                "role": "system",
                "content": WHOLE_SESSION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],

        "temperature": 0.0,
        "max_tokens": 4096,
        "stream": False,
    }

    print()
    print(
        "[WHOLE REVIEW] starting...",
        flush=True,
    )

    r = requests.post(
        f"{LLM_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=300,
    )

    r.raise_for_status()

    corrected = (
        r.json()
        ["choices"][0]
        ["message"]
        ["content"]
    ).strip()

    if not corrected:
        raise RuntimeError(
            "empty whole-session LLM response"
        )

    # -----------------------------------------------
    # hallucination / summarization guard
    # -----------------------------------------------

    ratio = (
        len(corrected)
        / max(1, len(transcript))
    )

    print(
        "[WHOLE REVIEW] length ratio:",
        round(ratio, 3),
        flush=True,
    )

    if ratio < 0.65 or ratio > 1.45:

        print(
            "[WHOLE REVIEW REJECT]"
            " suspicious length change",
            flush=True,
        )

        return (
            transcript,
            "sentence-pass",
        )

    print(
        "[WHOLE REVIEWED]",
        corrected,
        flush=True,
    )

    return (
        corrected,
        "whole-session-llm",
    )


def update_session_metadata(s, **extra):

    path = s.root / "session.json"

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        data = {}

    data.update({
        "session_id":
            s.session_id,

        "title":
            s.title,

        "recording":
            s.recording,

        "postprocess_status":
            s.postprocess_status,
    })

    data.update(extra)

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# =========================================================
# STORAGE
# =========================================================

def save_wav(
    path,
    audio,
):

    pcm16 = (
        np.clip(
            audio,
            -1.0,
            1.0,
        )
        * 32767.0
    ).astype(np.int16)

    with wave.open(
        str(path),
        "wb",
    ) as wf:

        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)

        wf.writeframes(
            pcm16.tobytes()
        )


def save_segment(
    s,
    audio,
    qwen_raw,
    whisper_raw,
    llm_corrected,
    final_source,
):

    s.segment_index += 1

    index = s.segment_index

    wav_name = (
        f"{index:06d}.wav"
    )

    wav_path = (
        s.root
        / "segments"
        / wav_name
    )

    save_wav(
        wav_path,
        audio,
    )

    record = {
        "segment": index,

        "session_id":
            s.session_id,

        "title":
            s.title,

        "audio":
            f"segments/{wav_name}",

        "duration_sec":
            round(
                len(audio) / SR,
                3,
            ),

        "qwen_raw":
            qwen_raw,

        "whisper_raw":
            whisper_raw,

        "llm_corrected":
            llm_corrected
            if final_source == "llm"
            else None,

        "final_text":
            llm_corrected,

        "final_source":
            final_source,

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),
    }

    transcript_file = (
        s.root
        / "transcript.jsonl"
    )

    with transcript_file.open(
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
        "[SAVED]",
        wav_path,
        flush=True,
    )


# =========================================================
# SENTENCE FINALIZATION
# =========================================================

def finalize_sentence(s):

    if not s.active:
        return

    # 마지막 Qwen tail flush
    qwen_asr.finish_streaming_transcribe(
        s.qwen_state
    )

    last_piece = current_qwen_piece(s)

    if last_piece:
        s.qwen_parts.append(
            last_piece
        )

    qwen_raw = " ".join(
        s.qwen_parts
    ).strip()

    audio = s.sentence_audio.copy()

    # -----------------------------------------------------
    # pass 2
    # -----------------------------------------------------

    whisper_raw = whisper_transcribe(
        audio
    )

    # -----------------------------------------------------
    # pass 3
    # -----------------------------------------------------

    final_text, final_source = llm_correct(
        s,
        qwen_raw=qwen_raw,
        whisper_raw=whisper_raw,
    )

    if final_text:

        save_segment(
            s,
            audio=audio,
            qwen_raw=qwen_raw,
            whisper_raw=whisper_raw,
            llm_corrected=final_text,
            final_source=final_source,
        )

        s.committed.append(
            final_text
        )

        print(
            "[FINAL]",
            final_text,
            flush=True,
        )

    # -----------------------------------------------------
    # reset sentence
    # -----------------------------------------------------

    s.active = False

    s.sentence_audio = np.empty(
        0,
        dtype=np.float32,
    )

    s.qwen_parts = []

    reset_qwen_state(s)

    s.vad.reset_states()

    s.vad_buffer = np.empty(
        0,
        dtype=np.float32,
    )


# =========================================================
# API
# =========================================================

def api_start():

    body = request.get_json(
        silent=True
    ) or {}

    title = (
        body.get(
            "title",
            "",
        )
        or ""
    ).strip()

    if not title:

        return jsonify({
            "error":
                "session title is required"
        }), 400

    timestamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    sid = (
        f"{timestamp}-"
        f"{uuid.uuid4().hex[:8]}"
    )

    root = DATA_ROOT / sid

    (root / "segments").mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {
        "session_id": sid,
        "title": title,

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "recording": True,

        "postprocess_status":
            "not_run",
    }

    (
        root
        / "session.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    s = Session(
        session_id=sid,
        title=title,
        root=root,
        qwen_state=
            new_qwen_state(title),
        vad=new_vad(),
    )

    SESSIONS[sid] = s

    print(
        "[SESSION]",
        sid,
        title,
        flush=True,
    )

    return jsonify({
        "session_id": sid,
        "title": title,
        "postprocess_status":
            "not_run",
    })


def api_chunk():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = SESSIONS.get(sid)

    if s is None:

        return jsonify({
            "error":
                "invalid session_id"
        }), 400

    raw = request.get_data(
        cache=False
    )

    if len(raw) % 4:

        return jsonify({
            "error":
                "invalid float32 audio"
        }), 400

    wav = np.frombuffer(
        raw,
        dtype=np.float32,
    ).copy()

    with s.lock:

        speech_start, speech_end = (
            feed_vad(
                s,
                wav,
            )
        )

        # -------------------------------------------------
        # not in speech
        # -------------------------------------------------

        if not s.active:

            if speech_start:

                s.active = True

                if len(s.preroll):

                    audio = np.concatenate(
                        [
                            s.preroll,
                            wav,
                        ]
                    )

                else:
                    audio = wav

                s.preroll = np.empty(
                    0,
                    dtype=np.float32,
                )

                s.sentence_audio = (
                    audio.copy()
                )

                qwen_asr.streaming_transcribe(
                    audio,
                    s.qwen_state,
                )

                s.qwen_samples += len(
                    audio
                )

            else:

                max_pre = int(
                    SR * PREROLL_SEC
                )

                s.preroll = np.concatenate(
                    [
                        s.preroll,
                        wav,
                    ]
                )[-max_pre:]

        # -------------------------------------------------
        # active speech
        # -------------------------------------------------

        else:

            s.sentence_audio = np.concatenate(
                [
                    s.sentence_audio,
                    wav,
                ]
            )

            qwen_asr.streaming_transcribe(
                wav,
                s.qwen_state,
            )

            s.qwen_samples += len(
                wav
            )

        # -------------------------------------------------
        # sentence boundary
        # -------------------------------------------------

        if (
            s.active
            and speech_end
        ):

            finalize_sentence(s)

            max_pre = int(
                SR * PREROLL_SEC
            )

            s.preroll = (
                wav[-max_pre:].copy()
            )

        # -------------------------------------------------
        # Qwen-only split.
        #
        # Whisper sentence buffer는 절대 끊지 않는다.
        # -------------------------------------------------

        elif (
            s.active
            and s.qwen_samples
            >= int(
                SR
                * QWEN_MAX_STATE_SEC
            )
        ):

            split_qwen_state(s)

        committed = "\n".join(
            s.committed
        )

        unfixed = (
            current_qwen_text(s)
            if s.active
            else ""
        )

        return jsonify({
            "title":
                s.title,

            "language":
                FORCE_LANGUAGE,

            "committed_text":
                committed,

            "unfixed_text":
                unfixed,

            "text":
                (
                    committed
                    + (
                        "\n"
                        if committed and unfixed
                        else ""
                    )
                    + unfixed
                ),

            "vad_active":
                s.active,

            "postprocess_status":
                s.postprocess_status,
        })


def api_finish():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = SESSIONS.get(sid)

    if s is None:

        return jsonify({
            "error":
                "invalid session_id"
        }), 400


    with s.lock:

        # 마지막 발화가 남아 있다면
        # Whisper + sentence LLM까지만 수행
        if s.active:
            finalize_sentence(s)

        s.recording = False

        sentence_text = (
            effective_transcript(s)
        )

        update_session_metadata(
            s,
            stopped_at=
                datetime.now()
                .astimezone()
                .isoformat(),
        )


    # 중요:
    # 여기서 SESSIONS.pop() 하지 않는다.
    # 후처리 버튼이 같은 세션을 다시 사용해야 함.

    print(
        "[SESSION STOPPED]",
        sid,
        flush=True,
    )


    return jsonify({
        "session_id":
            sid,

        "title":
            s.title,

        "language":
            FORCE_LANGUAGE,

        "committed_text":
            sentence_text,

        "unfixed_text":
            "",

        "text":
            sentence_text,

        "postprocess_status":
            s.postprocess_status,

        "whole_reviewed_text":
            s.whole_reviewed_text,
    })


# =========================================================
# LAZY POSTPROCESS API
# =========================================================

def api_postprocess():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = SESSIONS.get(sid)

    if s is None:

        return jsonify({
            "error":
                "invalid session_id"
        }), 400


    # -----------------------------------------------
    # 상태 확인
    # -----------------------------------------------

    with s.lock:

        if s.recording:

            return jsonify({
                "error":
                    "stop recording before postprocessing",

                "postprocess_status":
                    s.postprocess_status,
            }), 409


        if s.postprocess_status == "running":

            return jsonify({
                "error":
                    "postprocessing already running",

                "postprocess_status":
                    "running",
            }), 409


        effective_segments = (
            get_effective_segments(
                s,
                include_final=False,
            )
        )

        sentence_text = "\n".join(
            x["text"]
            for x in effective_segments
        ).strip()


        if not sentence_text:

            return jsonify({
                "error":
                    "transcript is empty"
            }), 400


        s.postprocess_status = "running"

        update_session_metadata(s)


    print()
    print(
        "==================================",
        flush=True,
    )

    print(
        "[POSTPROCESS START]",
        s.title,
        flush=True,
    )


    try:

        final_text, source, final_segment_map = (
            whole_session_review_segments(
                title=s.title,
                segments=
                    effective_segments,
            )
        )


        with s.lock:

            s.whole_reviewed_text = (
                final_text
            )

            s.postprocess_status = "done"

            update_session_metadata(
                s,
                postprocessed_at=
                    datetime.now()
                    .astimezone()
                    .isoformat(),

                final_source=
                    source,
            )


        # -------------------------------------------
        # final segment results
        # -------------------------------------------

        _write_json_file(
            s.root
            / "final_segments.json",

            {
                "segments":
                    final_segment_map
            },
        )


        # -------------------------------------------
        # final.json 저장
        # -------------------------------------------

        final_data = {

            "session_id":
                s.session_id,

            "title":
                s.title,

            "sentence_corrected_text":
                sentence_text,

            "whole_reviewed_text":
                final_text,

            "postprocess_status":
                "done",

            "final_source":
                source,

            "postprocessed_at":
                datetime.now()
                .astimezone()
                .isoformat(),
        }


        (
            s.root
            / "final.json"
        ).write_text(
            json.dumps(
                final_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


        print()
        print(
            "[POSTPROCESS DONE]",
            flush=True,
        )

        print(
            "[FINAL]",
            final_text,
            flush=True,
        )


        return jsonify({

            "session_id":
                s.session_id,

            "title":
                s.title,

            "sentence_corrected_text":
                sentence_text,

            "whole_reviewed_text":
                final_text,

            "text":
                final_text,

            "postprocess_status":
                "done",

            "source":
                source,
        })


    except Exception as e:

        with s.lock:

            s.postprocess_status = "error"

            update_session_metadata(
                s,
                postprocess_error=
                    repr(e),
            )


        print(
            "[POSTPROCESS ERROR]",
            repr(e),
            flush=True,
        )


        return jsonify({

            "error":
                str(e),

            "postprocess_status":
                "error",
        }), 500



# =========================================================
# SEGMENT EDIT / AUDIO / LOCKED TRANSCRIPT
# =========================================================

def _read_json_file(path, default):

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return default


def _write_json_file(path, data):

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def load_manual_edits(s):

    data = _read_json_file(
        s.root / "manual_edits.json",
        {
            "segments": {}
        },
    )

    return data.get(
        "segments",
        {},
    )


def save_manual_edits(s, edits):

    _write_json_file(
        s.root / "manual_edits.json",
        {
            "segments": edits
        },
    )


def load_final_segments(s):

    data = _read_json_file(
        s.root / "final_segments.json",
        {
            "segments": {}
        },
    )

    return data.get(
        "segments",
        {},
    )


def load_transcript_records(s):

    path = (
        s.root
        / "transcript.jsonl"
    )

    if not path.exists():
        return []

    result = []

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        try:
            obj = json.loads(line)

            if isinstance(obj, dict):
                result.append(obj)

        except Exception:
            pass

    return result


def get_effective_segments(
    s,
    include_final=True,
):

    manual = load_manual_edits(s)

    final_segments = (
        load_final_segments(s)
        if (
            include_final
            and s.postprocess_status
            == "done"
        )
        else {}
    )

    records = (
        load_transcript_records(s)
    )

    result = []

    for i, base_text in enumerate(
        s.committed,
        start=1,
    ):

        key = str(i)

        record = (
            records[i - 1]
            if i - 1 < len(records)
            else {}
        )

        edit = manual.get(
            key,
            {},
        )

        manually_edited = bool(edit)

        text = base_text

        # ---------------------------------------------
        # Whole-session result
        # ---------------------------------------------

        if (
            not manually_edited
            and key in final_segments
        ):
            text = final_segments[key]


        # ---------------------------------------------
        # Human edit always wins
        # ---------------------------------------------

        if manually_edited:

            text = (
                edit.get("text")
                or text
            )


        audio_path = (
            s.root
            / "segments"
            / f"{i:06d}.wav"
        )


        result.append({

            "segment":
                i,

            "text":
                text,

            "sentence_corrected":
                base_text,

            "manual_corrected":
                (
                    edit.get("text")
                    if manually_edited
                    else None
                ),

            "manually_edited":
                manually_edited,

            "locked":
                manually_edited,

            "whisper_raw":
                record.get(
                    "whisper_raw"
                ),

            "llm_corrected":
                record.get(
                    "llm_corrected"
                ),

            "start":
                record.get(
                    "start"
                ),

            "end":
                record.get(
                    "end"
                ),

            "audio_available":
                audio_path.exists(),

            "audio_url":
                (
                    "/api/segment/audio"
                    f"?session_id={s.session_id}"
                    f"&segment={i}"
                ),
        })

    return result


def effective_transcript(s):

    return "\n".join(
        x["text"]
        for x in get_effective_segments(
            s,
            include_final=False,
        )
    )


# =========================================================
# STRUCTURED WHOLE-SESSION REVIEW
# Human edited segments are LOCKED.
# =========================================================

def whole_session_review_segments(
    title,
    segments,
):

    if not segments:

        return (
            "",
            "sentence-pass",
            {},
        )


    blocks = []

    for seg in segments:

        idx = seg["segment"]

        state = (
            "LOCKED"
            if seg["locked"]
            else "AUTO"
        )

        blocks.append(
            f"<<<SEGMENT {idx} {state}>>>\n"
            f"{seg['text']}\n"
            f"<<<END {idx}>>>"
        )


    marked_transcript = (
        "\n\n".join(blocks)
    )


    system_prompt = """
You are performing the FINAL review of an ASR transcript.

The transcript is divided into numbered segments.

Each segment is marked either AUTO or LOCKED.

LOCKED means the user manually corrected that segment.

CRITICAL RULE:
Never change the text inside a LOCKED segment.

AUTO segments may only be corrected for:
- obvious ASR transcription errors
- technical terminology
- Korean/English mixed terms
- mathematical notation such as SO(3), SE(3)
- punctuation
- errors resolvable from surrounding lecture context

Do NOT:
- summarize
- add information
- remove spoken information
- rewrite stylistically
- change meaning

Keep every SEGMENT and END marker exactly as provided.

Return all segments in the same order.

No commentary.
No markdown outside the segment markers.
""".strip()


    user_prompt = f"""
SESSION TITLE:
{title}

TRANSCRIPT:
{marked_transcript}

Perform the final ASR correction.

Remember:
LOCKED segments must remain unchanged.
""".strip()


    payload = {

        "model":
            LLM_MODEL,

        "messages": [

            {
                "role":
                    "system",

                "content":
                    system_prompt,
            },

            {
                "role":
                    "user",

                "content":
                    user_prompt,
            },
        ],

        "temperature":
            0.0,

        "max_tokens":
            4096,

        "stream":
            False,
    }


    print()
    print(
        "[WHOLE REVIEW / LOCK-AWARE]",
        flush=True,
    )


    r = requests.post(

        f"{LLM_BASE_URL}"
        "/v1/chat/completions",

        json=payload,

        timeout=300,
    )

    r.raise_for_status()


    output = (
        r.json()
        ["choices"][0]
        ["message"]
        ["content"]
    ).strip()


    import re


    final_map = {}


    for seg in segments:

        idx = seg["segment"]

        original = seg["text"]


        # Human text ALWAYS wins.
        if seg["locked"]:

            final_map[
                str(idx)
            ] = original

            continue


        pattern = (
            rf"<<<SEGMENT {idx} AUTO>>>"
            rf"\s*(.*?)\s*"
            rf"<<<END {idx}>>>"
        )


        m = re.search(
            pattern,
            output,
            flags=re.S,
        )


        if not m:

            print(
                "[WHOLE REVIEW FALLBACK]"
                f" segment={idx}"
                " marker missing",
                flush=True,
            )

            final_map[
                str(idx)
            ] = original

            continue


        corrected = (
            m.group(1).strip()
        )


        ratio = (
            len(corrected)
            / max(
                1,
                len(original),
            )
        )


        if (
            ratio < 0.45
            or ratio > 1.80
        ):

            print(
                "[WHOLE REVIEW REJECT]"
                f" segment={idx}"
                f" ratio={ratio:.2f}",
                flush=True,
            )

            corrected = original


        final_map[
            str(idx)
        ] = corrected


    final_text = "\n".join(

        final_map[
            str(seg["segment"])
        ]

        for seg in segments
    )


    return (
        final_text,
        "whole-session-llm",
        final_map,
    )


# =========================================================
# API: segment list
# =========================================================

def api_segments():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = SESSIONS.get(sid)

    if s is None:

        return jsonify({
            "error":
                "invalid session_id"
        }), 400


    with s.lock:

        segments = (
            get_effective_segments(s)
        )


        text = "\n".join(
            x["text"]
            for x in segments
        )


        return jsonify({

            "session_id":
                sid,

            "title":
                s.title,

            "recording":
                s.recording,

            "postprocess_status":
                s.postprocess_status,

            "segments":
                segments,

            "text":
                text,
        })


# =========================================================
# API: play original segment WAV
# =========================================================

def api_segment_audio():

    from flask import send_file


    sid = request.args.get(
        "session_id",
        "",
    )


    try:

        segment = int(
            request.args.get(
                "segment",
                "0",
            )
        )

    except ValueError:

        segment = 0


    s = SESSIONS.get(sid)

    if s is None:

        return jsonify({
            "error":
                "invalid session_id"
        }), 400


    if segment < 1:

        return jsonify({
            "error":
                "invalid segment"
        }), 400


    path = (
        s.root
        / "segments"
        / f"{segment:06d}.wav"
    )


    if not path.exists():

        return jsonify({
            "error":
                "audio segment not found"
        }), 404


    return send_file(
        str(path),
        mimetype="audio/wav",
        conditional=True,
    )


# =========================================================
# API: human edit
# =========================================================

def api_edit_segment():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = SESSIONS.get(sid)

    if s is None:

        return jsonify({
            "error":
                "invalid session_id"
        }), 400


    body = request.get_json(
        silent=True
    ) or {}


    try:

        segment = int(
            body.get(
                "segment",
                0,
            )
        )

    except Exception:

        segment = 0


    text = (
        body.get(
            "text",
            "",
        )
        or ""
    ).strip()


    if (
        segment < 1
        or segment
        > len(s.committed)
    ):

        return jsonify({
            "error":
                "invalid segment"
        }), 400


    if not text:

        return jsonify({
            "error":
                "text cannot be empty"
        }), 400


    with s.lock:

        edits = (
            load_manual_edits(s)
        )


        edits[
            str(segment)
        ] = {

            "text":
                text,

            "updated_at":
                datetime.now()
                .astimezone()
                .isoformat(),
        }


        save_manual_edits(
            s,
            edits,
        )


        # -------------------------------------------------
        # Human edit invalidates previous whole review.
        # -------------------------------------------------

        s.postprocess_status = (
            "not_run"
        )

        s.whole_reviewed_text = ""


        for stale in [

            s.root
            / "final.json",

            s.root
            / "final_segments.json",
        ]:

            try:
                stale.unlink()
            except FileNotFoundError:
                pass


        update_session_metadata(
            s,
            postprocess_status=
                "not_run",

            last_manual_edit=
                datetime.now()
                .astimezone()
                .isoformat(),
        )


        segments = (
            get_effective_segments(
                s,
                include_final=False,
            )
        )


        committed_text = "\n".join(
            x["text"]
            for x in segments
        )


    print(
        "[MANUAL EDIT]"
        f" segment={segment}",
        flush=True,
    )


    return jsonify({

        "ok":
            True,

        "segment":
            segment,

        "text":
            text,

        "manually_edited":
            True,

        "postprocess_status":
            "not_run",

        "committed_text":
            committed_text,
    })


# =========================================================
# APP SHUTDOWN
# =========================================================

def api_app_shutdown():

    import os

    control_url = os.environ.get(
        "HOST_CONTROL_URL",
        "http://host.docker.internal:8765",
    ).rstrip("/")

    token = os.environ.get(
        "CLOVA_CONTROL_TOKEN",
        "",
    )

    if not token:
        return jsonify({
            "error": "host control token is not configured"
        }), 500

    try:
        r = requests.post(
            control_url + "/shutdown",
            headers={
                "X-Clova-Token": token
            },
            timeout=5,
        )

        if r.status_code not in (200, 202):
            return jsonify({
                "error": "host shutdown controller rejected request",
                "status_code": r.status_code,
            }), 502

        return jsonify({
            "ok": True,
            "status": "shutting_down",
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 502


# =========================================================
# UI
# =========================================================

INDEX_HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Clova Note Local</title>

<style>

body {
    font-family: system-ui, sans-serif;
    max-width: 1000px;
    margin: 40px auto;
    padding: 0 20px;
}

input {
    width: 100%;
    box-sizing: border-box;
    font-size: 18px;
    padding: 12px;
    margin-bottom: 12px;
}

button {
    padding: 10px 18px;
    font-size: 16px;
    margin-right: 8px;
}

#committed {
    white-space: pre-wrap;
    line-height: 1.7;
    font-size: 18px;
    margin-top: 24px;
}

#unfixed {
    white-space: pre-wrap;
    line-height: 1.7;
    font-size: 18px;
    color: #888;
    margin-top: 8px;
}

#status {
    margin-left: 12px;
}

#postStatus {
    margin-left: 16px;
    font-weight: 600;
}

.post-not-run {
    color: #b7791f;
}

.post-running {
    color: #2563eb;
}

.post-done {
    color: #15803d;
}

.post-error {
    color: #dc2626;
}



/* ==============================================
   V5 transcript editor
   ============================================== */

#segmentEditor {
    margin-top: 24px;
}

.segment-editor-title {
    font-weight: 700;
    margin-bottom: 12px;
}

.segment-card {
    border: 1px solid #ddd;
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 10px;
    background: rgba(255,255,255,.03);
}

.segment-card.locked {
    border-left: 4px solid #b7791f;
}

.segment-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
}

.segment-meta {
    font-size: 12px;
    opacity: .65;
}

.segment-lock {
    font-size: 12px;
    font-weight: 700;
}

.segment-text-button {
    display: block;
    width: 100%;
    padding: 8px 4px;
    border: 0;
    background: transparent;
    text-align: left;
    font: inherit;
    line-height: 1.65;
    cursor: pointer;
}

.segment-text-button:hover {
    background: rgba(127,127,127,.08);
}

.segment-actions {
    margin-top: 8px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.segment-actions button {
    min-height: 36px;
}

.segment-edit-area {
    width: 100%;
    box-sizing: border-box;
    min-height: 100px;
    resize: vertical;
    padding: 10px;
    font: inherit;
    line-height: 1.5;
}

#segmentPlayer {
    width: 100%;
    margin: 12px 0 16px;
}

.segment-empty {
    opacity: .6;
    padding: 16px 0;
}

</style>
</head>

<body>

<h2>Local Clova Note</h2>

<input
    id="title"
    placeholder="세션 제목 — 예: 로보틱스 9/2 Relative Pose"
/>

<button id="start">Start</button>
<button id="stop" disabled>Stop</button>
<button id="postprocess" disabled>후처리</button>

<span id="status">Idle</span>
<span id="postStatus" class="post-not-run">
🟡 후처리 안 됨
</span>

<hr>

<div id="committed"></div>
<div id="unfixed"></div>

<script>

const SR = 16000;
const CHUNK_MS = 500;

let sessionId = null;
let running = false;

let stream = null;
let ctx = null;
let source = null;
let processor = null;

let buffer = new Float32Array(0);
let pushing = false;


function concat(a, b) {

    const out = new Float32Array(
        a.length + b.length
    );

    out.set(a, 0);
    out.set(b, a.length);

    return out;
}


function resample(
    input,
    srcRate,
    dstRate
) {

    if (srcRate === dstRate)
        return input;

    const ratio =
        dstRate / srcRate;

    const len =
        Math.round(
            input.length * ratio
        );

    const out =
        new Float32Array(len);

    for (
        let i = 0;
        i < len;
        i++
    ) {

        const x =
            i / ratio;

        const x0 =
            Math.floor(x);

        const x1 =
            Math.min(
                x0 + 1,
                input.length - 1
            );

        const t =
            x - x0;

        out[i] =
            input[x0] * (1 - t)
            + input[x1] * t;
    }

    return out;
}


function setPostStatus(status) {

    const el =
        document.getElementById(
            "postStatus"
        );

    el.className = "";

    if (status === "not_run") {

        el.textContent =
            "🟡 후처리 안 됨";

        el.classList.add(
            "post-not-run"
        );

    } else if (status === "running") {

        el.textContent =
            "🔵 후처리 중...";

        el.classList.add(
            "post-running"
        );

    } else if (status === "done") {

        el.textContent =
            "🟢 후처리 완료";

        el.classList.add(
            "post-done"
        );

    } else {

        el.textContent =
            "🔴 후처리 실패";

        el.classList.add(
            "post-error"
        );
    }
}


async function startSession() {

    const title =
        document
        .getElementById("title")
        .value
        .trim();

    if (!title) {
        alert("제목을 입력해줘.");
        return;
    }

    const r = await fetch(
        "/api/start",
        {
            method: "POST",
            headers: {
                "Content-Type":
                    "application/json"
            },
            body: JSON.stringify({
                title
            })
        }
    );

    if (!r.ok)
        throw new Error(
            await r.text()
        );

    const j =
        await r.json();

    sessionId =
        j.session_id;

    setPostStatus(
        "not_run"
    );

    document
    .getElementById(
        "postprocess"
    )
    .disabled = true;

    document
    .getElementById(
        "committed"
    )
    .textContent = "";

    document
    .getElementById(
        "unfixed"
    )
    .textContent = "";


    stream =
        await navigator
        .mediaDevices
        .getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: false,
                noiseSuppression: true,
                autoGainControl: true
            }
        });


    ctx =
        new AudioContext();

    source =
        ctx.createMediaStreamSource(
            stream
        );

    processor =
        ctx.createScriptProcessor(
            4096,
            1,
            1
        );


    processor.onaudioprocess =
        e => {

            if (!running)
                return;

            const input =
                e.inputBuffer
                .getChannelData(0);

            const audio =
                resample(
                    input,
                    ctx.sampleRate,
                    SR
                );

            buffer =
                concat(
                    buffer,
                    audio
                );

            pump();
        };


    source.connect(
        processor
    );

    processor.connect(
        ctx.destination
    );


    running = true;

    document
    .getElementById("start")
    .disabled = true;

    document
    .getElementById("stop")
    .disabled = false;

    document
    .getElementById("title")
    .disabled = true;

    document
    .getElementById("status")
    .textContent =
        "Listening";
}


async function pump() {

    if (pushing)
        return;

    pushing = true;

    const chunkSamples =
        SR * CHUNK_MS / 1000;

    try {

        while (
            running
            && buffer.length
            >= chunkSamples
        ) {

            const chunk =
                buffer.slice(
                    0,
                    chunkSamples
                );

            buffer =
                buffer.slice(
                    chunkSamples
                );


            const r =
                await fetch(
                    "/api/chunk?session_id="
                    + encodeURIComponent(
                        sessionId
                    ),
                    {
                        method: "POST",
                        headers: {
                            "Content-Type":
                            "application/octet-stream"
                        },
                        body: chunk.buffer
                    }
                );


            const j =
                await r.json();


            document
            .getElementById(
                "committed"
            )
            .textContent =
                j.committed_text
                || "";


            document
            .getElementById(
                "unfixed"
            )
            .textContent =
                j.unfixed_text
                || "";
        }

    } finally {

        pushing = false;
    }
}


async function stopSession() {

    running = false;

    if (processor)
        processor.disconnect();

    if (source)
        source.disconnect();

    if (ctx)
        await ctx.close();

    if (stream)
        stream
        .getTracks()
        .forEach(
            x => x.stop()
        );


    const r =
        await fetch(
            "/api/finish?session_id="
            + encodeURIComponent(
                sessionId
            ),
            {
                method: "POST"
            }
        );

    const j =
        await r.json();


    document
    .getElementById(
        "committed"
    )
    .textContent =
        j.committed_text
        || "";


    document
    .getElementById(
        "unfixed"
    )
    .textContent = "";


    document
    .getElementById(
        "status"
    )
    .textContent =
        "Stopped";


    document
    .getElementById(
        "start"
    )
    .disabled = false;


    document
    .getElementById(
        "stop"
    )
    .disabled = true;


    document
    .getElementById(
        "title"
    )
    .disabled = false;


    document
    .getElementById(
        "postprocess"
    )
    .disabled = false;


    setPostStatus(
        j.postprocess_status
        || "not_run"
    );

    // sessionId는 유지한다.
    // 후처리 API에서 동일 세션을 사용해야 함.
}


async function postprocessSession() {

    if (!sessionId)
        return;

    const button =
        document.getElementById(
            "postprocess"
        );

    button.disabled = true;

    setPostStatus(
        "running"
    );

    try {

        const r =
            await fetch(
                "/api/postprocess?session_id="
                + encodeURIComponent(
                    sessionId
                ),
                {
                    method: "POST"
                }
            );

        const j =
            await r.json();

        if (!r.ok) {

            throw new Error(
                j.error
                || "postprocess failed"
            );
        }


        // 전체 검수본으로 화면 교체
        document
        .getElementById(
            "committed"
        )
        .textContent =
            j.whole_reviewed_text
            || j.text
            || "";


        document
        .getElementById(
            "unfixed"
        )
        .textContent = "";


        setPostStatus(
            "done"
        );


        document
        .getElementById(
            "status"
        )
        .textContent =
            "Postprocessed";


    } catch (e) {

        console.error(e);

        setPostStatus(
            "error"
        );

        button.disabled = false;

        alert(
            "후처리 실패: "
            + e.message
        );
    }
}


document
.getElementById(
    "postprocess"
)
.onclick =
    postprocessSession;


document
.getElementById("start")
.onclick =
    startSession;


document
.getElementById("stop")
.onclick =
    stopSession;



// =========================================================
// V5 segment transcript editor
// =========================================================

function ensureSegmentEditorUI() {

    if (
        document.getElementById(
            "segmentEditor"
        )
    )
        return;


    const committed =
        document.getElementById(
            "committed"
        );


    if (!committed)
        return;


    const panel =
        document.createElement(
            "section"
        );

    panel.id =
        "segmentEditor";


    const heading =
        document.createElement(
            "div"
        );

    heading.className =
        "segment-editor-title";

    heading.textContent =
        "문장별 기록";


    const player =
        document.createElement(
            "audio"
        );

    player.id =
        "segmentPlayer";

    player.controls = true;


    const list =
        document.createElement(
            "div"
        );

    list.id =
        "segmentList";


    panel.appendChild(
        heading
    );

    panel.appendChild(
        player
    );

    panel.appendChild(
        list
    );


    committed.insertAdjacentElement(
        "afterend",
        panel
    );
}


async function playSegment(seg) {

    if (
        !seg.audio_available
    )
        return;


    const player =
        document.getElementById(
            "segmentPlayer"
        );


    player.src =
        seg.audio_url
        + "&cache="
        + Date.now();


    try {

        await player.play();

    } catch (e) {

        console.error(
            "audio playback failed",
            e
        );
    }
}


function beginSegmentEdit(
    card,
    seg
) {

    const oldText =
        card.querySelector(
            ".segment-text-button"
        );


    const actions =
        card.querySelector(
            ".segment-actions"
        );


    const textarea =
        document.createElement(
            "textarea"
        );

    textarea.className =
        "segment-edit-area";

    textarea.value =
        seg.text;


    oldText.replaceWith(
        textarea
    );


    actions.innerHTML = "";


    const save =
        document.createElement(
            "button"
        );

    save.type =
        "button";

    save.textContent =
        "저장";


    const cancel =
        document.createElement(
            "button"
        );

    cancel.type =
        "button";

    cancel.textContent =
        "취소";


    save.addEventListener(
        "click",
        async () => {

            const text =
                textarea.value.trim();


            if (!text)
                return;


            save.disabled =
                true;


            try {

                const r =
                    await fetch(
                        "/api/segment/edit"
                        + "?session_id="
                        + encodeURIComponent(
                            sessionId
                        ),
                        {
                            method:
                                "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify({
                                    segment:
                                        seg.segment,

                                    text:
                                        text
                                })
                        }
                    );


                const j =
                    await r.json();


                if (!r.ok)
                    throw new Error(
                        j.error
                        || "edit failed"
                    );


                document
                .getElementById(
                    "committed"
                )
                .textContent =
                    j.committed_text
                    || "";


                setPostStatus(
                    j.postprocess_status
                    || "not_run"
                );


                document
                .getElementById(
                    "postprocess"
                )
                .disabled = false;


                await refreshSegments();


            } catch (e) {

                alert(
                    "수정 저장 실패: "
                    + e.message
                );

                save.disabled =
                    false;
            }
        }
    );


    cancel.addEventListener(
        "click",
        () => {
            refreshSegments();
        }
    );


    actions.appendChild(
        save
    );

    actions.appendChild(
        cancel
    );


    textarea.focus();
}


function renderSegments(data) {

    ensureSegmentEditorUI();


    const list =
        document.getElementById(
            "segmentList"
        );


    if (!list)
        return;


    list.innerHTML = "";


    const segments =
        data.segments || [];


    if (!segments.length) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "segment-empty";

        empty.textContent =
            "아직 확정된 문장이 없습니다.";

        list.appendChild(
            empty
        );

        return;
    }


    for (const seg of segments) {

        const card =
            document.createElement(
                "article"
            );

        card.className =
            "segment-card"
            + (
                seg.manually_edited
                ? " locked"
                : ""
            );


        const head =
            document.createElement(
                "div"
            );

        head.className =
            "segment-head";


        const meta =
            document.createElement(
                "div"
            );

        meta.className =
            "segment-meta";


        let metaText =
            "문장 "
            + seg.segment;


        if (
            seg.start != null
            && seg.end != null
        ) {

            metaText +=
                " · "
                + Number(
                    seg.start
                ).toFixed(1)
                + "–"
                + Number(
                    seg.end
                ).toFixed(1)
                + "초";
        }


        meta.textContent =
            metaText;


        const lock =
            document.createElement(
                "div"
            );

        lock.className =
            "segment-lock";


        lock.textContent =
            seg.manually_edited
            ? "✏️ 사람이 수정함"
            : "AI";


        head.appendChild(
            meta
        );

        head.appendChild(
            lock
        );


        const textButton =
            document.createElement(
                "button"
            );

        textButton.type =
            "button";

        textButton.className =
            "segment-text-button";

        textButton.textContent =
            seg.text;


        if (
            seg.audio_available
        ) {

            textButton.title =
                "클릭하면 실제 음성을 재생합니다.";

            textButton.addEventListener(
                "click",
                () => playSegment(seg)
            );

        } else {

            textButton.disabled =
                true;
        }


        const actions =
            document.createElement(
                "div"
            );

        actions.className =
            "segment-actions";


        if (
            seg.audio_available
        ) {

            const play =
                document.createElement(
                    "button"
                );

            play.type =
                "button";

            play.textContent =
                "▶ 듣기";

            play.addEventListener(
                "click",
                () => playSegment(seg)
            );

            actions.appendChild(
                play
            );
        }


        const edit =
            document.createElement(
                "button"
            );

        edit.type =
            "button";

        edit.textContent =
            "수정";


        edit.addEventListener(
            "click",
            () => beginSegmentEdit(
                card,
                seg
            )
        );


        actions.appendChild(
            edit
        );


        card.appendChild(
            head
        );

        card.appendChild(
            textButton
        );

        card.appendChild(
            actions
        );


        list.appendChild(
            card
        );
    }
}


async function refreshSegments() {

    ensureSegmentEditorUI();


    if (!sessionId)
        return;


    try {

        const r =
            await fetch(
                "/api/segments"
                + "?session_id="
                + encodeURIComponent(
                    sessionId
                )
            );


        if (!r.ok)
            return;


        const j =
            await r.json();


        renderSegments(
            j
        );


        if (
            j.postprocess_status
        ) {

            setPostStatus(
                j.postprocess_status
            );
        }


    } catch (e) {

        console.debug(
            "segment refresh skipped",
            e
        );
    }
}


// Keep cards synchronized while recording
ensureSegmentEditorUI();

setInterval(
    refreshSegments,
    1200
);



// =========================================================
// APP SHUTDOWN BUTTON
// =========================================================

function ensureShutdownButton() {

    if (document.getElementById("shutdownApp"))
        return;

    const stop = document.getElementById("stop");

    if (!stop)
        return;

    const button = document.createElement("button");

    button.id = "shutdownApp";
    button.type = "button";
    button.textContent = "앱 종료";
    button.style.marginLeft = "8px";
    button.style.borderColor = "#b91c1c";
    button.style.color = "#b91c1c";

    button.addEventListener("click", async () => {

        const ok = window.confirm(
            "Local Clova와 Qwen3.8을 모두 종료할까요?"
        );

        if (!ok)
            return;

        button.disabled = true;
        button.textContent = "종료 중...";

        const status = document.getElementById("status");
        if (status)
            status.textContent = "Shutting down";

        try {
            const r = await fetch(
                "/api/app/shutdown",
                { method: "POST" }
            );

            if (!r.ok) {
                const j = await r.json();
                throw new Error(j.error || "shutdown failed");
            }
        } catch (e) {
            console.debug("shutdown request ended:", e);
        }

        const msg = document.createElement("div");
        msg.style.marginTop = "16px";
        msg.style.fontWeight = "700";
        msg.textContent = "앱 종료 요청 완료. 이 탭을 닫아도 됩니다.";

        const editor = document.getElementById("segmentEditor");
        if (editor)
            editor.prepend(msg);
    });

    stop.insertAdjacentElement("afterend", button);
}

ensureShutdownButton();
</script>

</body>
</html>
"""


def index():

    return Response(
        INDEX_HTML,
        mimetype=
            "text/html; charset=utf-8",
    )


# =========================================================
# MAIN
# =========================================================

def main():

    global qwen_asr
    global whisper_pipe

    print(
        "[1/2] Loading Qwen3-ASR...",
        flush=True,
    )

    qwen_asr = Qwen3ASRModel.LLM(
        model=QWEN_ASR_MODEL,
        gpu_memory_utilization=0.15,
        max_new_tokens=96,
        enforce_eager=True,
    )

    print(
        "[2/2] Loading Whisper large-v3...",
        flush=True,
    )

    whisper_model = (
        AutoModelForSpeechSeq2Seq
        .from_pretrained(
            WHISPER_MODEL,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        )
    )

    whisper_model.to(
        "cuda:0"
    )

    processor = (
        AutoProcessor
        .from_pretrained(
            WHISPER_MODEL
        )
    )

    whisper_pipe = pipeline(
        "automatic-speech-recognition",
        model=whisper_model,
        tokenizer=
            processor.tokenizer,
        feature_extractor=
            processor.feature_extractor,
        torch_dtype=torch.float16,
        device=0,
    )

    print(
        "[READY] Qwen + Whisper",
        flush=True,
    )

    if LLM_BASE_URL:

        print(
            "[LLM]",
            LLM_BASE_URL,
            LLM_MODEL,
            flush=True,
        )

    else:

        print(
            "[LLM] disabled",
            flush=True,
        )

    demo.app.view_functions[
        "index"
    ] = index

    demo.app.view_functions[
        "api_start"
    ] = api_start

    demo.app.view_functions[
        "api_chunk"
    ] = api_chunk

    demo.app.view_functions[
        "api_finish"
    ] = api_finish

    # Lazy whole-session review
    demo.app.add_url_rule(
        "/api/postprocess",
        "api_postprocess",
        api_postprocess,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/segments",
        "api_segments",
        api_segments,
        methods=["GET"],
    )

    demo.app.add_url_rule(
        "/api/segment/audio",
        "api_segment_audio",
        api_segment_audio,
        methods=["GET"],
    )

    demo.app.add_url_rule(
        "/api/segment/edit",
        "api_edit_segment",
        api_edit_segment,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/app/shutdown",
        "api_app_shutdown",
        api_app_shutdown,
        methods=["POST"],
    )

    demo.app.run(
        host="0.0.0.0",
        port=8000,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":

    from multiprocessing import (
        freeze_support
    )

    freeze_support()

    main()
