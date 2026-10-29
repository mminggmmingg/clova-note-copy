import os
import json
import wave
import uuid
import threading
import queue
import re
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
MIN_SILENCE_MS = 600
SPEECH_PAD_MS = 120

PREROLL_SEC = 0.35

# Qwen streaming state는 너무 길어지면 degeneration 가능
QWEN_MAX_STATE_SEC = 18.0

# Hard safety boundary: a lecturer can speak without a 600 ms pause.
# Do not let one Whisper segment grow forever.
MAX_SENTENCE_SEC = 28.0

UNFIXED_CHUNK_NUM = 4
UNFIXED_TOKEN_NUM = 5
CHUNK_SIZE_SEC = 1.0

FORCE_LANGUAGE = "Korean"

QWEN_ASR_MODEL = "/workspace/Qwen3-ASR-1.7B"
WHISPER_MODEL = "/workspace/whisper-large-v3"

APP_DATA_ROOT = Path("/workspace/data")
DATA_ROOT = APP_DATA_ROOT / "sessions"
SUBJECTS_FILE = APP_DATA_ROOT / "subjects.json"
UI_ROOT = Path("/workspace/web")

APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
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
This is a Korean university lecture.

The lecturer primarily speaks Korean and may mix English technical,
mathematical, scientific, and engineering terminology.

Preserve English technical terms when they were spoken in English.
Preserve symbols, equations, acronyms, proper nouns, and course-specific
terminology when strongly supported by the audio and surrounding context.

Do not assume a specific academic subject unless the selected course or
session title provides that information.
""".strip()


# =========================================================
# GLOBAL MODELS
# =========================================================

qwen_asr = None
whisper_pipe = None

SESSIONS = {}
SUBJECTS_LOCK = threading.Lock()


def _now_iso():

    return (
        datetime.now()
        .astimezone()
        .isoformat()
    )


def _read_json_path(path, default):

    try:
        return json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return default


def _write_json_path(path, data):

    path = Path(path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def load_subjects():

    data = _read_json_path(
        SUBJECTS_FILE,
        {"subjects": []},
    )

    subjects = data.get(
        "subjects",
        [],
    )

    if not isinstance(subjects, list):
        return []

    return [
        x for x in subjects
        if isinstance(x, dict)
        and x.get("id")
        and x.get("name")
    ]


def save_subjects(subjects):

    _write_json_path(
        SUBJECTS_FILE,
        {"subjects": subjects},
    )


def subject_by_id(subject_id):

    if not subject_id:
        return None

    for subject in load_subjects():
        if subject.get("id") == subject_id:
            return subject

    return None


def subject_name_for_id(subject_id):

    subject = subject_by_id(subject_id)

    if not subject:
        return ""

    semester = (
        subject.get("semester")
        or ""
    ).strip()

    name = (
        subject.get("name")
        or ""
    ).strip()

    if semester:
        return f"{semester} {name}".strip()

    return name


def normalize_tag_entries(raw_tags):

    result = []
    seen = set()

    if not isinstance(raw_tags, list):
        return result

    for item in raw_tags:

        if isinstance(item, str):
            name = item.strip()
            source = "ai"

        elif isinstance(item, dict):
            name = str(
                item.get("name")
                or ""
            ).strip()

            source = str(
                item.get("source")
                or "ai"
            ).strip().lower()

            if source not in {
                "ai",
                "manual",
            }:
                source = "ai"

        else:
            continue

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        result.append({
            "name": name,
            "source": source,
        })

    return result


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
    subject_id: str = ""

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

    # V6.2: sentence boundaries are detached from heavy Whisper/LLM work.
    # The HTTP audio-ingest path only queues jobs; one background worker
    # processes them in order.
    pending_segments: dict = field(default_factory=dict)
    sentence_queue: object = field(default_factory=queue.Queue)
    sentence_worker: object = None

    lock: object = field(
        default_factory=threading.Lock
    )


# =========================================================
# QWEN
# =========================================================

def qwen_context(title, subject_id=""):
    """Short plain-language hint for Qwen3-ASR.

    V6.1 used a long, role-like context block containing labels such as
    "SESSION TITLE" and "COURSE / SUBJECT".  On rare streaming decode failures
    Qwen3-ASR could echo its serialized prompt into ``state.text``.  Keep the
    ASR context deliberately short and non-chat-like; the sentence/whole
    Qwen3.8 passes still have the richer metadata.
    """

    subject = subject_name_for_id(subject_id)

    parts = [
        "Korean university lecture audio.",
    ]

    if subject:
        parts.append(
            f"Course is {subject}."
        )

    if title:
        parts.append(
            f"Session topic is {title}."
        )

    parts.append(
        "Korean speech may contain English technical terms, symbols, acronyms, and proper nouns."
    )

    return " ".join(parts)


_QWEN_ASR_TRAILING_TOKENS = (
    "<|im_end|>",
    "<|endoftext|>",
    "<|eot_id|>",
    "</s>",
)


def sanitize_qwen_asr_text(raw):
    """Return only spoken ASR text, never Qwen's prompt/chat serialization.

    Observed failure example:
        system
        SESSION TITLE:
        ...
        user
        assistant
        language Korean<asr_text>실제 발화

    The strongest delimiter is ``<asr_text>``.  If a malformed prompt leak is
    detected without that delimiter, discard the leaked hypothesis instead of
    ever exposing metadata/system text to the transcript.
    """

    text = str(raw or "")
    text = text.replace("\\x00", "").strip()

    if not text:
        return ""

    # Qwen-ASR's serialized assistant answer places speech after this marker.
    marker = "<asr_text>"
    if marker in text:
        text = text.rsplit(marker, 1)[1].strip()

    # Defensive handling for alternate serialized role formats.
    if marker not in str(raw or ""):
        role_matches = list(
            re.finditer(
                r"(?:^|\\n)assistant\\s*(?:\\n|:)"
                r"(?:\\s*language\\s+[A-Za-z_-]+\\s*)?",
                text,
                flags=re.I,
            )
        )
        if role_matches:
            text = text[
                role_matches[-1].end():
            ].strip()

    text = re.sub(
        r"^\\s*language\\s+[A-Za-z_-]+\\s*",
        "",
        text,
        flags=re.I,
    )

    for token in _QWEN_ASR_TRAILING_TOKENS:
        text = text.replace(token, "")

    text = text.strip()

    # If role/context material survived but no reliable ASR delimiter existed,
    # reject it.  An empty live hypothesis is preferable to contaminating the
    # permanent transcript with system metadata.
    leak_signatures = (
        "SESSION TITLE:",
        "COURSE / SUBJECT:",
        "\\nsystem\\n",
        "\\nuser\\n",
    )

    if any(
        signature.lower() in text.lower()
        for signature in leak_signatures
    ):
        print(
            "[QWEN ASR SANITIZER] rejected prompt leak",
            repr(text[:180]),
            flush=True,
        )
        return ""

    return text


def new_qwen_state(title, subject_id=""):

    return qwen_asr.init_streaming_state(
        context=qwen_context(title, subject_id),
        language=FORCE_LANGUAGE,
        unfixed_chunk_num=UNFIXED_CHUNK_NUM,
        unfixed_token_num=UNFIXED_TOKEN_NUM,
        chunk_size_sec=CHUNK_SIZE_SEC,
    )


def current_qwen_piece(s):

    raw = (
        getattr(
            s.qwen_state,
            "text",
            "",
        )
        or ""
    )

    clean = sanitize_qwen_asr_text(
        raw
    )

    if clean != str(raw).strip():
        print(
            "[QWEN ASR SANITIZED]",
            f"raw_chars={len(str(raw))}",
            f"clean_chars={len(clean)}",
            flush=True,
        )

    return clean


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
        s.title,
        s.subject_id,
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

def _repetition_tokens(text):

    return re.findall(
        r"[가-힣]+|[A-Za-z0-9]+(?:[._+\-/][A-Za-z0-9]+)*|[^\s]",
        str(text or "").casefold(),
    )


def detect_repetition_loop(text):
    """Return (is_degenerate, reason) for obvious ASR repetition loops."""

    tokens = _repetition_tokens(text)

    if len(tokens) < 8:
        return False, ""

    # 1) One token repeated many times in a row: "인류 인류 인류 ..."
    run = 1
    max_run = 1

    for i in range(1, len(tokens)):
        if tokens[i] == tokens[i - 1]:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1

    if max_run >= 5:
        return True, f"same-token-run:{max_run}"

    # 2) A single token dominates an implausibly large portion of output.
    counts = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1

    dominant_token, dominant_count = max(
        counts.items(),
        key=lambda item: item[1],
    )

    if (
        dominant_count >= 10
        and dominant_count / len(tokens) >= 0.34
    ):
        return True, (
            f"dominant-token:{dominant_token}:"
            f"{dominant_count}/{len(tokens)}"
        )

    # 3) Repeated short phrase (1-6 tokens), four or more times consecutively.
    n_tokens = len(tokens)

    for width in range(1, min(6, n_tokens // 4) + 1):
        for i in range(0, n_tokens - width * 4 + 1):
            phrase = tokens[i:i + width]
            reps = 1
            pos = i + width

            while (
                pos + width <= n_tokens
                and tokens[pos:pos + width] == phrase
            ):
                reps += 1
                pos += width

            covered = reps * width

            if (
                reps >= 4
                and covered >= 8
                and covered / n_tokens >= 0.30
            ):
                return True, (
                    f"phrase-loop:{width}x{reps}"
                )

    return False, ""


def _whisper_once(audio, *, anti_loop=False):

    generate_kwargs = {
        "language": "korean",
        "task": "transcribe",
    }

    # Only used on a retry after the detector catches degeneration.
    # These are standard generation controls and do not change the first pass.
    if anti_loop:
        generate_kwargs.update({
            "repetition_penalty": 1.12,
            "no_repeat_ngram_size": 4,
        })

    result = whisper_pipe(
        {
            "array": audio,
            "sampling_rate": SR,
        },
        generate_kwargs=generate_kwargs,
    )

    return (
        result.get("text", "")
        or ""
    ).strip()


def whisper_transcribe(audio):

    if audio is None or len(audio) == 0:
        return "", False, ""

    duration = len(audio) / SR

    print(
        f"[WHISPER] {duration:.2f}s",
        flush=True,
    )

    text = _whisper_once(
        audio,
        anti_loop=False,
    )

    print(
        "[WHISPER RAW]",
        text,
        flush=True,
    )

    bad, reason = detect_repetition_loop(text)

    if not bad:
        return text, False, ""

    print(
        "[WHISPER LOOP DETECTED]",
        reason,
        flush=True,
    )

    # Retry once with stronger generation anti-repeat controls. If the
    # installed Transformers build rejects one of these kwargs, keep the
    # original output marked as rejected and fall back to Qwen-ASR.
    try:
        retry = _whisper_once(
            audio,
            anti_loop=True,
        )

        retry_bad, retry_reason = (
            detect_repetition_loop(retry)
        )

        print(
            "[WHISPER RETRY]",
            retry,
            flush=True,
        )

        if retry and not retry_bad:
            print(
                "[WHISPER RETRY RECOVERED]",
                flush=True,
            )
            return retry, False, (
                f"recovered-from:{reason}"
            )

        if retry_reason:
            reason = (
                f"{reason};retry={retry_reason}"
            )

    except Exception as e:
        print(
            "[WHISPER RETRY ERROR]",
            repr(e),
            flush=True,
        )

    # The raw Whisper text is still kept for audit, but callers must not use
    # it as the sentence-final fallback.
    return text, True, reason


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
    *,
    whisper_rejected=False,
):

    usable_whisper = (
        ""
        if whisper_rejected
        else str(whisper_raw or "").strip()
    )

    qwen_raw = str(qwen_raw or "").strip()

    fallback = (
        usable_whisper
        or qwen_raw
    )

    fallback_source = (
        "whisper"
        if usable_whisper
        else "qwen"
    )

    if not LLM_BASE_URL:

        print(
            "[LLM] disabled -> safe ASR fallback",
            flush=True,
        )

        return (
            fallback,
            fallback_source,
        )

    # Single background worker preserves ordering, but future segments may
    # already exist as empty placeholders. Use only completed prior text.
    with s.lock:
        previous_items = [
            str(x).strip()
            for x in s.committed
            if str(x or "").strip()
        ][-3:]

    previous = "\n".join(
        previous_items
    )

    subject_name = subject_name_for_id(
        s.subject_id
    )

    whisper_prompt = (
        usable_whisper
        if usable_whisper
        else "(discarded: repetition loop detected)"
    )

    user_prompt = f"""
SESSION TITLE:
{s.title}

COURSE / SUBJECT:
{subject_name if subject_name else "(not assigned)"}

DOMAIN:
Korean university lecture

PREVIOUS CONFIRMED TRANSCRIPT:
{previous if previous else "(none)"}

QWEN ASR:
{qwen_raw}

WHISPER ASR:
{whisper_prompt}

Correct the CURRENT utterance only.
If one ASR source is marked discarded, rely on the other source and context.
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

        if not corrected:
            raise RuntimeError(
                "empty LLM output"
            )

        corrected_bad, corrected_reason = (
            detect_repetition_loop(corrected)
        )

        if corrected_bad:
            print(
                "[LLM REJECT] repetition:",
                corrected_reason,
                flush=True,
            )
            return (
                fallback,
                fallback_source,
            )

        # Normal hallucination/summarization guard. Crucially, when Whisper
        # was rejected, `fallback` is Qwen-ASR rather than the broken Whisper
        # loop, so a short correct answer is no longer rejected against a
        # gigantic degenerate base string.
        if fallback:

            ratio = (
                len(corrected)
                / max(1, len(fallback))
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
                    fallback,
                    fallback_source,
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
            fallback,
            fallback_source,
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

        "subject_id":
            s.subject_id,

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
    *,
    index,
    audio,
    qwen_raw,
    whisper_raw,
    llm_corrected,
    final_source,
    whisper_rejected=False,
    whisper_reject_reason="",
    processing_error="",
):

    wav_name = (
        f"{index:06d}.wav"
    )

    wav_path = (
        s.root
        / "segments"
        / wav_name
    )

    # V6.2 saves WAV immediately at the boundary, before background ASR.
    # Keep this fallback for recovery/tests.
    if not wav_path.exists():
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

        "whisper_rejected":
            bool(whisper_rejected),

        "whisper_reject_reason":
            whisper_reject_reason or None,

        "llm_corrected":
            llm_corrected
            if final_source == "llm"
            else None,

        "final_text":
            llm_corrected,

        "final_source":
            final_source,

        "processing_status":
            "done",

        "processing_error":
            processing_error or None,

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


def _reset_live_sentence_state(s):

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


def start_sentence_worker(s):

    worker = s.sentence_worker

    if (
        worker is not None
        and worker.is_alive()
    ):
        return

    worker = threading.Thread(
        target=_sentence_worker_loop,
        args=(s,),
        daemon=True,
        name=(
            "clova-sentence-"
            + s.session_id[-8:]
        ),
    )

    s.sentence_worker = worker
    worker.start()


def enqueue_sentence(s, *, boundary_reason="vad"):
    """Detach the current sentence and return immediately.

    Caller holds s.lock. Only the cheap Qwen tail flush, WAV save and state
    reset happen synchronously. Whisper + sentence Qwen3.8 run in a worker.
    """

    if not s.active:
        return None

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

    if len(audio) == 0:
        _reset_live_sentence_state(s)
        return None

    s.segment_index += 1
    index = s.segment_index

    # Reserve the segment position immediately. The worker fills this slot.
    while len(s.committed) < index:
        s.committed.append("")

    wav_path = (
        s.root
        / "segments"
        / f"{index:06d}.wav"
    )

    save_wav(
        wav_path,
        audio,
    )

    pending = {
        "segment": index,
        "status": "queued",
        "boundary_reason": boundary_reason,
        "qwen_raw": qwen_raw,
        "whisper_raw": "",
        "whisper_rejected": False,
        "whisper_reject_reason": "",
        "duration_sec": round(
            len(audio) / SR,
            3,
        ),
        "created_at": _now_iso(),
    }

    s.pending_segments[index] = pending

    s.sentence_queue.put({
        "segment": index,
        "audio": audio,
        "qwen_raw": qwen_raw,
        "boundary_reason": boundary_reason,
    })

    print(
        "[SENTENCE QUEUED]",
        f"segment={index}",
        f"reason={boundary_reason}",
        f"duration={len(audio) / SR:.2f}s",
        flush=True,
    )

    _reset_live_sentence_state(s)

    update_session_metadata(
        s,
        pending_count=len(
            s.pending_segments
        ),
    )

    return index


def _sentence_worker_loop(s):

    print(
        "[SENTENCE WORKER] started",
        s.session_id,
        flush=True,
    )

    while True:

        job = s.sentence_queue.get()

        if job is None:
            s.sentence_queue.task_done()
            return

        index = int(job["segment"])
        audio = job["audio"]
        qwen_raw = str(
            job.get("qwen_raw")
            or ""
        ).strip()

        whisper_raw = ""
        whisper_rejected = False
        whisper_reason = ""
        processing_error = ""

        try:

            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending["status"] = "whisper"

            (
                whisper_raw,
                whisper_rejected,
                whisper_reason,
            ) = whisper_transcribe(
                audio
            )

            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending.update({
                        "status": "sentence_llm",
                        "whisper_raw": whisper_raw,
                        "whisper_rejected": whisper_rejected,
                        "whisper_reject_reason": whisper_reason,
                    })

            final_text, final_source = llm_correct(
                s,
                qwen_raw=qwen_raw,
                whisper_raw=whisper_raw,
                whisper_rejected=whisper_rejected,
            )

            final_text = str(
                final_text or ""
            ).strip()

            if not final_text:
                final_text = (
                    qwen_raw
                    or (
                        whisper_raw
                        if not whisper_rejected
                        else ""
                    )
                    or "[ASR 실패 — 원본 음성을 확인하세요]"
                )

                if final_source == "llm":
                    final_source = (
                        "qwen"
                        if qwen_raw
                        else "whisper"
                    )

        except Exception as e:

            processing_error = repr(e)

            print(
                "[SENTENCE WORKER ERROR]",
                f"segment={index}",
                processing_error,
                flush=True,
            )

            final_text = (
                qwen_raw
                or (
                    whisper_raw
                    if not whisper_rejected
                    else ""
                )
                or "[ASR 처리 실패 — 원본 음성을 확인하세요]"
            )

            final_source = (
                "qwen"
                if qwen_raw
                else "whisper"
            )

        try:
            with s.lock:

                save_segment(
                    s,
                    index=index,
                    audio=audio,
                    qwen_raw=qwen_raw,
                    whisper_raw=whisper_raw,
                    llm_corrected=final_text,
                    final_source=final_source,
                    whisper_rejected=whisper_rejected,
                    whisper_reject_reason=whisper_reason,
                    processing_error=processing_error,
                )

                if index - 1 < len(s.committed):
                    s.committed[index - 1] = final_text

                s.pending_segments.pop(
                    index,
                    None,
                )

                update_session_metadata(
                    s,
                    pending_count=len(
                        s.pending_segments
                    ),
                )

            print(
                "[SENTENCE DONE]",
                f"segment={index}",
                f"source={final_source}",
                flush=True,
            )

        finally:
            s.sentence_queue.task_done()


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

    subject_id = (
        body.get(
            "subject_id",
            "",
        )
        or ""
    ).strip()

    if (
        subject_id
        and subject_by_id(subject_id) is None
    ):

        return jsonify({
            "error":
                "invalid subject_id"
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

        "subject_id":
            subject_id,

        "tags": [],

        "description": "",

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
            new_qwen_state(
                title,
                subject_id,
            ),
        vad=new_vad(),
        subject_id=subject_id,
    )

    SESSIONS[sid] = s
    start_sentence_worker(s)

    print(
        "[SESSION]",
        sid,
        title,
        flush=True,
    )

    return jsonify({
        "session_id": sid,
        "title": title,
        "subject_id": subject_id,
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

    boundary_index = None
    boundary_reason = ""

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
        # V6.2: detach immediately; never wait for Whisper/LLM here.
        # -------------------------------------------------

        if (
            s.active
            and speech_end
        ):

            boundary_reason = "vad"
            boundary_index = enqueue_sentence(
                s,
                boundary_reason=boundary_reason,
            )

            max_pre = int(
                SR * PREROLL_SEC
            )

            s.preroll = (
                wav[-max_pre:].copy()
            )

        # If the lecturer never pauses long enough, force a safe boundary so
        # Whisper never receives an unbounded 30s+ sentence.
        elif (
            s.active
            and len(s.sentence_audio)
            >= int(SR * MAX_SENTENCE_SEC)
        ):

            boundary_reason = "max_duration"
            boundary_index = enqueue_sentence(
                s,
                boundary_reason=boundary_reason,
            )

            max_pre = int(
                SR * PREROLL_SEC
            )

            s.preroll = (
                wav[-max_pre:].copy()
            )

        # -------------------------------------------------
        # Qwen-only split.
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
            str(x)
            for x in s.committed
            if str(x or "").strip()
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

            "segment_boundary":
                boundary_index is not None,

            "boundary_segment":
                boundary_index,

            "boundary_reason":
                boundary_reason or None,

            "segment_count":
                len(s.committed),

            "pending_count":
                len(s.pending_segments),

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

        # Detach the last partial utterance, but do not wait for heavy ASR.
        if s.active:
            enqueue_sentence(
                s,
                boundary_reason="user_stop",
            )

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
            pending_count=len(
                s.pending_segments
            ),
        )

    print(
        "[SESSION STOPPED]",
        sid,
        f"pending={len(s.pending_segments)}",
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

        "pending_count":
            len(s.pending_segments),

        "postprocess_status":
            s.postprocess_status,

        "whole_reviewed_text":
            s.whole_reviewed_text,
    })


# =========================================================
# V6 AI SESSION METADATA
# =========================================================

SESSION_METADATA_SYSTEM_PROMPT = """
You create navigation metadata for a university lecture transcript.

Return ONLY one valid JSON object with exactly these fields:
{
  "tags": ["tag 1", "tag 2", "tag 3"],
  "description": "one concise Korean description"
}

TAG RULES:
- produce 3 to 8 concise tags
- prefer technical concepts, algorithms, mathematical objects,
  named methods, standards, protocols, theories, and major lecture topics
- preserve standard English technical names when appropriate
- do not produce generic tags such as 수업, 강의, 교수님, 설명, 대학
- do not duplicate near-identical tags
- do not invent topics that are not supported by the transcript

DESCRIPTION RULES:
- Korean, one or two short sentences
- describe what this session actually covered
- suitable for a sidebar/search preview
- do not add facts absent from the transcript

No markdown. No commentary. JSON only.
""".strip()


def _extract_json_object(text):

    raw = (text or "").strip()

    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")

    if start >= 0 and end > start:
        obj = json.loads(raw[start:end + 1])
        if isinstance(obj, dict):
            return obj

    raise ValueError("LLM metadata response did not contain a JSON object")


def generate_ai_session_metadata(
    title,
    subject_name,
    transcript,
):

    if not LLM_BASE_URL:
        return [], ""

    prompt = f"""
SESSION TITLE:
{title}

COURSE / SUBJECT:
{subject_name if subject_name else "(not assigned)"}

FINAL TRANSCRIPT:
{transcript}

Generate search/navigation metadata for this exact session.
""".strip()

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SESSION_METADATA_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "stream": False,
    }

    print(
        "[SESSION METADATA] generating tags/description...",
        flush=True,
    )

    r = requests.post(
        f"{LLM_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=120,
    )

    r.raise_for_status()

    content = (
        r.json()
        ["choices"][0]
        ["message"]
        ["content"]
    )

    obj = _extract_json_object(content)

    raw_tags = obj.get("tags", [])
    cleaned = []
    seen = set()

    generic = {
        "수업",
        "강의",
        "교수님",
        "설명",
        "대학",
        "lecture",
        "class",
    }

    if isinstance(raw_tags, list):
        for item in raw_tags:
            name = str(item or "").strip()

            if not name:
                continue

            key = name.casefold()

            if key in seen or key in generic:
                continue

            seen.add(key)
            cleaned.append(name)

            if len(cleaned) >= 8:
                break

    description = str(
        obj.get("description")
        or ""
    ).strip()

    if len(description) > 400:
        description = description[:397].rstrip() + "..."

    return cleaned, description


def merge_ai_session_metadata(
    s,
    ai_tags,
    description,
):

    path = s.root / "session.json"
    data = _read_json_path(path, {})

    existing = normalize_tag_entries(
        data.get("tags", [])
    )

    manual = [
        item
        for item in existing
        if item.get("source") == "manual"
    ]

    manual_keys = {
        item["name"].casefold()
        for item in manual
    }

    blocklist = {
        str(x).casefold()
        for x in data.get(
            "tag_blocklist",
            [],
        )
        if str(x).strip()
    }

    merged = list(manual)

    for name in ai_tags:
        key = name.casefold()

        if key in manual_keys:
            continue

        if key in blocklist:
            continue

        merged.append({
            "name": name,
            "source": "ai",
        })

    data["tags"] = merged
    data["description"] = description
    data["ai_metadata_generated_at"] = _now_iso()

    _write_json_path(
        path,
        data,
    )

    return merged


# =========================================================
# LAZY POSTPROCESS API
# =========================================================

def api_postprocess():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = get_session_or_load(sid)

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

        if s.pending_segments:

            return jsonify({
                "error":
                    "sentence processing is still running",

                "pending_count":
                    len(s.pending_segments),

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
                subject_name=
                    subject_name_for_id(
                        s.subject_id
                    ),
            )
        )


        ai_tags = []
        description = ""
        metadata_error = ""

        try:

            ai_tags, description = (
                generate_ai_session_metadata(
                    title=s.title,
                    subject_name=
                        subject_name_for_id(
                            s.subject_id
                        ),
                    transcript=final_text,
                )
            )

        except Exception as meta_error:

            metadata_error = repr(
                meta_error
            )

            print(
                "[SESSION METADATA ERROR]",
                metadata_error,
                flush=True,
            )


        with s.lock:

            s.whole_reviewed_text = (
                final_text
            )

            if not metadata_error:
                tags = merge_ai_session_metadata(
                    s,
                    ai_tags,
                    description,
                )
            else:
                session_meta = _read_json_path(
                    s.root / "session.json",
                    {},
                )
                tags = normalize_tag_entries(
                    session_meta.get(
                        "tags",
                        [],
                    )
                )
                description = str(
                    session_meta.get(
                        "description",
                        "",
                    )
                    or ""
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

                metadata_ai_error=
                    metadata_error
                    if metadata_error
                    else None,
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

            "subject_id":
                s.subject_id,

            "tags":
                tags,

            "description":
                description,

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

            "subject_id":
                s.subject_id,

            "tags":
                tags,

            "description":
                description,

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

    record_map = {}

    for pos, record in enumerate(
        records,
        start=1,
    ):
        try:
            idx = int(
                record.get("segment")
                or pos
            )
        except Exception:
            idx = pos

        record_map[idx] = record

    result = []
    elapsed = 0.0

    for i, base_text in enumerate(
        s.committed,
        start=1,
    ):

        key = str(i)
        record = record_map.get(i, {})
        pending = s.pending_segments.get(i)

        edit = manual.get(
            key,
            {},
        )

        manually_edited = bool(edit)

        whole_corrected = (
            final_segments.get(key)
            if key in final_segments
            else None
        )

        processing_status = (
            str(pending.get("status") or "queued")
            if pending
            else "done"
        )

        qwen_raw = (
            pending.get("qwen_raw")
            if pending
            else record.get("qwen_raw")
        )

        whisper_raw = (
            pending.get("whisper_raw")
            if pending
            else record.get("whisper_raw")
        )

        whisper_rejected = bool(
            (
                pending.get("whisper_rejected")
                if pending
                else record.get("whisper_rejected")
            )
            or False
        )

        whisper_reject_reason = (
            pending.get("whisper_reject_reason")
            if pending
            else record.get("whisper_reject_reason")
        )

        text = str(base_text or "").strip()

        # While heavy processing is pending, show the already-available Qwen
        # hypothesis immediately instead of waiting for a blank box.
        if pending and not text:
            text = (
                str(qwen_raw or "").strip()
                or "문장 처리 중…"
            )

        if (
            not pending
            and not manually_edited
            and whole_corrected
        ):
            text = whole_corrected

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

        duration = float(
            (
                pending.get("duration_sec")
                if pending
                else record.get("duration_sec")
            )
            or 0.0
        )

        raw_start = record.get("start")
        raw_end = record.get("end")

        if raw_start is None:
            start_sec = elapsed
        else:
            try:
                start_sec = float(raw_start)
            except Exception:
                start_sec = elapsed

        if raw_end is None:
            end_sec = start_sec + duration
        else:
            try:
                end_sec = float(raw_end)
            except Exception:
                end_sec = start_sec + duration

        elapsed = max(
            elapsed,
            end_sec,
        )

        result.append({

            "segment": i,
            "text": text,

            "qwen_raw": qwen_raw,
            "whisper_raw": whisper_raw,
            "whisper_rejected": whisper_rejected,
            "whisper_reject_reason": whisper_reject_reason,

            "llm_corrected":
                record.get("llm_corrected"),

            "sentence_corrected":
                (str(base_text).strip() if str(base_text or "").strip() else None),

            "whole_corrected":
                whole_corrected,

            "manual_corrected":
                (
                    edit.get("text")
                    if manually_edited
                    else None
                ),

            "final_source":
                record.get("final_source"),

            "processing_status":
                processing_status,

            "pending":
                bool(pending),

            "processing_error":
                record.get("processing_error"),

            "manually_edited":
                manually_edited,

            "locked":
                manually_edited,

            "duration_sec":
                duration,

            "start":
                start_sec,

            "end":
                end_sec,

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
# V6 LIBRARY / ARCHIVED SESSIONS
# =========================================================

def _base_texts_from_records(records):

    result = []

    for record in records:

        text = (
            record.get("final_text")
            or record.get("llm_corrected")
            or record.get("whisper_raw")
            or record.get("qwen_raw")
            or ""
        )

        text = str(text).strip()

        if text:
            result.append(text)

    return result


def load_session_from_disk(session_id):

    root = DATA_ROOT / session_id

    if not root.is_dir():
        return None

    meta = _read_json_path(
        root / "session.json",
        {},
    )

    if not meta:
        return None

    title = str(
        meta.get("title")
        or session_id
    ).strip()

    subject_id = str(
        meta.get("subject_id")
        or ""
    ).strip()

    records = []
    path = root / "transcript.jsonl"

    if path.exists():
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines():
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except Exception:
                pass

    committed = _base_texts_from_records(
        records
    )

    final_data = _read_json_path(
        root / "final.json",
        {},
    )

    s = Session(
        session_id=session_id,
        title=title,
        root=root,
        qwen_state=None,
        vad=None,
        subject_id=subject_id,
        committed=committed,
        postprocess_status=str(
            meta.get("postprocess_status")
            or "not_run"
        ),
        whole_reviewed_text=str(
            final_data.get("whole_reviewed_text")
            or ""
        ),
        recording=False,
        active=False,
        segment_index=len(committed),
    )

    return s


def get_session_or_load(session_id):

    s = SESSIONS.get(session_id)

    if s is not None:
        return s

    s = load_session_from_disk(
        session_id
    )

    if s is not None:
        SESSIONS[session_id] = s

    return s


def hydrate_sessions_from_disk():

    count = 0

    for root in sorted(
        DATA_ROOT.iterdir(),
        reverse=True,
    ):

        if not root.is_dir():
            continue

        sid = root.name

        if sid in SESSIONS:
            continue

        s = load_session_from_disk(sid)

        if s is None:
            continue

        # A process restart means an old recording flag can no longer
        # represent a live microphone session.
        meta = _read_json_path(
            root / "session.json",
            {},
        )

        if meta.get("recording"):
            meta["recording"] = False
            meta["interrupted_by_restart"] = True
            meta["recovered_at"] = _now_iso()
            _write_json_path(
                root / "session.json",
                meta,
            )

        SESSIONS[sid] = s
        count += 1

    print(
        f"[LIBRARY] hydrated {count} archived sessions",
        flush=True,
    )


def _session_summary_from_root(root):

    meta = _read_json_path(
        root / "session.json",
        {},
    )

    if not meta:
        return None

    sid = str(
        meta.get("session_id")
        or root.name
    )

    records = []
    transcript_path = root / "transcript.jsonl"

    if transcript_path.exists():
        for line in transcript_path.read_text(
            encoding="utf-8"
        ).splitlines():
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except Exception:
                pass

    duration = 0.0

    for record in records:
        try:
            duration += float(
                record.get("duration_sec")
                or 0.0
            )
        except Exception:
            pass

    edits = _read_json_path(
        root / "manual_edits.json",
        {"segments": {}},
    ).get("segments", {})

    if not isinstance(edits, dict):
        edits = {}

    in_memory = SESSIONS.get(sid)

    postprocess_status = str(
        meta.get("postprocess_status")
        or "not_run"
    )

    recording = False

    pending_count = 0

    if in_memory is not None:
        postprocess_status = (
            in_memory.postprocess_status
        )
        recording = bool(
            in_memory.recording
        )
        pending_count = len(
            in_memory.pending_segments
        )

        # Pending WAVs are already saved, but transcript.jsonl records only
        # appear after background processing completes. Include them in live
        # library stats without double counting completed records.
        completed_ids = {
            int(record.get("segment") or pos)
            for pos, record in enumerate(records, start=1)
            if str(record.get("segment") or pos).isdigit()
        }

        duration += sum(
            float(item.get("duration_sec") or 0.0)
            for idx, item in in_memory.pending_segments.items()
            if int(idx) not in completed_ids
        )

    tags = normalize_tag_entries(
        meta.get("tags", [])
    )

    return {
        "session_id": sid,
        "title": str(
            meta.get("title")
            or sid
        ),
        "subject_id": str(
            meta.get("subject_id")
            or ""
        ),
        "created_at": meta.get("created_at"),
        "stopped_at": meta.get("stopped_at"),
        "recording": recording,
        "postprocess_status": postprocess_status,
        "tags": tags,
        "description": str(
            meta.get("description")
            or ""
        ),
        "segment_count": (
            max(len(records), len(in_memory.committed))
            if in_memory is not None
            else len(records)
        ),
        "pending_count": pending_count,
        "manual_edit_count": len(edits),
        "duration_sec": round(duration, 3),
    }


def session_public_meta(s):

    meta = _read_json_path(
        s.root / "session.json",
        {},
    )

    summary = _session_summary_from_root(
        s.root
    ) or {}

    summary.update({
        "session_id": s.session_id,
        "title": s.title,
        "subject_id": s.subject_id,
        "recording": s.recording,
        "postprocess_status":
            s.postprocess_status,
        "pending_count":
            len(s.pending_segments),
        "segment_count":
            max(
                int(summary.get("segment_count") or 0),
                len(s.committed),
            ),
        "tags": normalize_tag_entries(
            meta.get("tags", [])
        ),
        "description": str(
            meta.get("description")
            or ""
        ),
    })

    return summary


def api_library():

    subjects = load_subjects()
    sessions = []

    for root in DATA_ROOT.iterdir():
        if not root.is_dir():
            continue

        summary = _session_summary_from_root(
            root
        )

        if summary:
            sessions.append(summary)

    sessions.sort(
        key=lambda x: str(
            x.get("created_at")
            or x.get("session_id")
            or ""
        ),
        reverse=True,
    )

    subjects.sort(
        key=lambda x: (
            str(x.get("semester") or ""),
            str(x.get("name") or ""),
        ),
        reverse=True,
    )

    return jsonify({
        "subjects": subjects,
        "sessions": sessions,
    })


def api_subject_create():

    body = request.get_json(
        silent=True
    ) or {}

    name = str(
        body.get("name")
        or ""
    ).strip()

    semester = str(
        body.get("semester")
        or ""
    ).strip()

    emoji = str(
        body.get("emoji")
        or "📘"
    ).strip()[:8]

    if not name:
        return jsonify({
            "error": "subject name is required"
        }), 400

    with SUBJECTS_LOCK:

        subjects = load_subjects()

        for existing in subjects:
            if (
                str(existing.get("name") or "").casefold()
                == name.casefold()
                and str(existing.get("semester") or "").casefold()
                == semester.casefold()
            ):
                return jsonify(existing)

        subject = {
            "id": "subject-" + uuid.uuid4().hex[:10],
            "name": name,
            "semester": semester,
            "emoji": emoji or "📘",
            "created_at": _now_iso(),
        }

        subjects.append(subject)
        save_subjects(subjects)

    return jsonify(subject), 201


def _sync_final_navigation_metadata(s, session_meta):

    final_path = s.root / "final.json"

    if not final_path.exists():
        return

    final_data = _read_json_path(
        final_path,
        {},
    )

    if not isinstance(final_data, dict):
        return

    final_data.update({
        "title": s.title,
        "subject_id": s.subject_id,
        "tags": normalize_tag_entries(
            session_meta.get("tags", [])
        ),
        "description": str(
            session_meta.get("description")
            or ""
        ),
    })

    _write_json_path(
        final_path,
        final_data,
    )


def api_session_meta():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = get_session_or_load(sid)

    if s is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

    body = request.get_json(
        silent=True
    ) or {}

    with s.lock:

        data = _read_json_path(
            s.root / "session.json",
            {},
        )

        if "subject_id" in body:

            subject_id = str(
                body.get("subject_id")
                or ""
            ).strip()

            if (
                subject_id
                and subject_by_id(subject_id) is None
            ):
                return jsonify({
                    "error": "invalid subject_id"
                }), 400

            s.subject_id = subject_id
            data["subject_id"] = subject_id

        if "title" in body:

            title = str(
                body.get("title")
                or ""
            ).strip()

            if not title:
                return jsonify({
                    "error": "title cannot be empty"
                }), 400

            if s.recording:
                return jsonify({
                    "error": "cannot rename while recording"
                }), 409

            s.title = title
            data["title"] = title

        tags = normalize_tag_entries(
            data.get("tags", [])
        )

        if "add_tag" in body:

            name = str(
                body.get("add_tag")
                or ""
            ).strip()

            if name:

                key = name.casefold()
                found = False

                for item in tags:
                    if item["name"].casefold() == key:
                        item["name"] = name
                        item["source"] = "manual"
                        found = True
                        break

                if not found:
                    tags.append({
                        "name": name,
                        "source": "manual",
                    })

                blocklist = [
                    str(x)
                    for x in data.get(
                        "tag_blocklist",
                        [],
                    )
                    if str(x).casefold() != key
                ]
                data["tag_blocklist"] = blocklist

        if "remove_tag" in body:

            name = str(
                body.get("remove_tag")
                or ""
            ).strip()

            if name:
                key = name.casefold()
                tags = [
                    item
                    for item in tags
                    if item["name"].casefold() != key
                ]

                blocklist = {
                    str(x).casefold(): str(x)
                    for x in data.get(
                        "tag_blocklist",
                        [],
                    )
                    if str(x).strip()
                }

                blocklist[key] = name
                data["tag_blocklist"] = list(
                    blocklist.values()
                )

        data["tags"] = tags
        data["updated_at"] = _now_iso()

        _write_json_path(
            s.root / "session.json",
            data,
        )

        _sync_final_navigation_metadata(
            s,
            data,
        )

    return jsonify(
        session_public_meta(s)
    )


# =========================================================
# STRUCTURED WHOLE-SESSION REVIEW
# Human edited segments are LOCKED.
# =========================================================

def whole_session_review_segments(
    title,
    segments,
    subject_name="",
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

COURSE / SUBJECT:
{subject_name if subject_name else "(not assigned)"}

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

    s = get_session_or_load(sid)

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

        meta = session_public_meta(s)

        return jsonify({

            **meta,

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


    s = get_session_or_load(sid)

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

    s = get_session_or_load(sid)

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

        if segment in s.pending_segments:
            return jsonify({
                "error":
                    "wait until sentence processing finishes"
            }), 409

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


        # Transcript changed: generated navigation metadata is stale.
        # Preserve only human-created tags.
        session_meta = _read_json_path(
            s.root / "session.json",
            {},
        )

        session_meta["tags"] = [
            item
            for item in normalize_tag_entries(
                session_meta.get("tags", [])
            )
            if item.get("source") == "manual"
        ]

        session_meta["description"] = ""
        session_meta.pop(
            "ai_metadata_generated_at",
            None,
        )

        _write_json_path(
            s.root / "session.json",
            session_meta,
        )


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

    pending_total = sum(
        len(session.pending_segments)
        for session in SESSIONS.values()
    )

    if pending_total:
        return jsonify({
            "error": (
                f"{pending_total} sentence(s) are still processing; "
                "wait for them to finish before app shutdown"
            ),
            "pending_count": pending_total,
        }), 409

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

def _ui_text(name):

    path = UI_ROOT / name

    if not path.exists():
        return None

    return path.read_text(
        encoding="utf-8"
    )


def index():

    html = _ui_text(
        "index_v6.html"
    )

    if html is None:
        return Response(
            "Local Clova V6.2 UI is missing: /workspace/web/index_v6.html",
            status=500,
            mimetype="text/plain; charset=utf-8",
        )

    return Response(
        html,
        mimetype="text/html; charset=utf-8",
    )


def ui_css():

    css = _ui_text(
        "app_v6.css"
    )

    if css is None:
        return Response(
            "/* app_v6.css missing */",
            status=404,
            mimetype="text/css; charset=utf-8",
        )

    return Response(
        css,
        mimetype="text/css; charset=utf-8",
    )


def ui_js():

    js = _ui_text(
        "app_v6.js"
    )

    if js is None:
        return Response(
            "// app_v6.js missing",
            status=404,
            mimetype="application/javascript; charset=utf-8",
        )

    return Response(
        js,
        mimetype="application/javascript; charset=utf-8",
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

    hydrate_sessions_from_disk()

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

    # V6 UI assets
    demo.app.add_url_rule(
        "/ui/app.css",
        "ui_css",
        ui_css,
        methods=["GET"],
    )

    demo.app.add_url_rule(
        "/ui/app.js",
        "ui_js",
        ui_js,
        methods=["GET"],
    )

    # V6 library / subject / session metadata
    demo.app.add_url_rule(
        "/api/library",
        "api_library",
        api_library,
        methods=["GET"],
    )

    demo.app.add_url_rule(
        "/api/subject",
        "api_subject_create",
        api_subject_create,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/session/meta",
        "api_session_meta",
        api_session_meta,
        methods=["POST"],
    )

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
