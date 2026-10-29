import os
import json
import wave
import uuid
import threading
import queue
import re
import time
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
# V6.4: Silero only reports a *candidate* speech end after 450 ms.
# The Adaptive Segmenter below decides whether to cut now or keep waiting.
VAD_BASE_SILENCE_MS = 450
SPEECH_PAD_MS = 120

# Adaptive segment target: roughly three UI lines for a normal desktop width.
# Backend uses transcript size + speech duration + sentence-ending hints, not
# literal browser line count, so behavior is stable across screen sizes.
ADAPTIVE_SHORT_SILENCE_MS = 1500
ADAPTIVE_MEDIUM_SILENCE_MS = 1000
ADAPTIVE_TARGET_SILENCE_MS = 600
ADAPTIVE_LARGE_SILENCE_MS = 500

PREROLL_SEC = 0.35

# Qwen streaming state는 너무 길어지면 degeneration 가능
QWEN_MAX_STATE_SEC = 18.0

# Hard safety boundary: a lecturer can speak without a 600 ms pause.
# Do not let one BatiSay segment grow forever.
MAX_SENTENCE_SEC = 28.0

UNFIXED_CHUNK_NUM = 4
UNFIXED_TOKEN_NUM = 5
CHUNK_SIZE_SEC = 1.0

FORCE_LANGUAGE = "Korean"

QWEN_ASR_MODEL = "/workspace/Qwen3-ASR-1.7B"
BATISAY_MODEL = "/workspace/batisay-ko-large"
BATISAY_MODEL_ID = "batiai/batisay-ko-large"

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

# V6.4.2: keep each whole-session LLM request safely below the host
# llama.cpp context window. Long lectures are reviewed in overlapping chunks.
POSTPROCESS_CHUNK_CHAR_BUDGET = int(os.getenv("POSTPROCESS_CHUNK_CHAR_BUDGET", "6000"))
POSTPROCESS_CHUNK_MAX_SEGMENTS = int(os.getenv("POSTPROCESS_CHUNK_MAX_SEGMENTS", "60"))
POSTPROCESS_CONTEXT_SEGMENTS = int(os.getenv("POSTPROCESS_CONTEXT_SEGMENTS", "2"))
METADATA_TRANSCRIPT_CHAR_BUDGET = int(os.getenv("METADATA_TRANSCRIPT_CHAR_BUDGET", "9000"))


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
batisay_pipe = None

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

    # BatiSay에 보낼 현재 segment 전체 오디오
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

    # V6.3: background whole-session postprocess state.
    # postprocess_progress is intentionally in-memory for frequent updates;
    # durable status/timestamps are still written to session.json.
    postprocess_progress: dict = field(default_factory=dict)
    postprocess_worker: object = None

    # 녹음 중인지 여부
    recording: bool = True

    active: bool = False
    qwen_samples: int = 0

    # V6.4 adaptive segmentation. Silero's end event starts a silence
    # candidate; it is cancelled if speech resumes before the adaptive cutoff.
    adaptive_silence_active: bool = False
    adaptive_silence_samples: int = 0

    segment_index: int = 0

    # V6.4: segment boundaries are detached from BatiSay inference.
    # The HTTP audio-ingest path only queues jobs; one background worker
    # processes them in order. V6.5 will add adaptive multi-worker scaling.
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
    BatiSay segment는 유지하면서
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
        min_silence_duration_ms=VAD_BASE_SILENCE_MS,
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
# V6.4 ADAPTIVE SEGMENTER + BATISAY SEGMENT STT
# =========================================================


def _normalized_transcript_chars(text):

    return len(
        re.sub(
            r"\s+",
            "",
            str(text or ""),
        )
    )


def _looks_like_sentence_end(text):
    """Conservative Korean lecture sentence-ending hint.

    This never creates a boundary by itself. It only lowers the silence
    requirement after the VAD has already observed a real pause.
    """

    text = str(text or "").strip()

    if not text:
        return False

    if re.search(r"[.!?。？！]$", text):
        return True

    endings = (
        "입니다", "합니다", "됩니다", "있습니다", "없습니다",
        "거죠", "거예요", "겁니다", "인데요", "네요",
        "인가요", "할까요", "됩니다", "보겠습니다",
    )

    return any(text.endswith(item) for item in endings)


def adaptive_silence_threshold_ms(s):
    """Return the pause needed to close the current speech box.

    Goal: average around three visible transcript lines while tolerating a
    lecturer who pauses frequently mid-thought. Browser line count itself is
    intentionally not used because it changes with viewport width/font size.
    """

    text = current_qwen_text(s)
    chars = _normalized_transcript_chars(text)
    duration = (
        len(s.sentence_audio) / SR
        if s.sentence_audio is not None
        else 0.0
    )

    if chars >= 150 or duration >= 22.0:
        threshold = ADAPTIVE_LARGE_SILENCE_MS
    elif chars >= 100 or duration >= 14.0:
        threshold = ADAPTIVE_TARGET_SILENCE_MS
    elif chars >= 45 or duration >= 6.0:
        threshold = ADAPTIVE_MEDIUM_SILENCE_MS
    else:
        threshold = ADAPTIVE_SHORT_SILENCE_MS

    # A plausible sentence ending is supporting evidence, not the primary
    # boundary signal. Never go below the VAD's reliable 450 ms candidate.
    if _looks_like_sentence_end(text):
        threshold = max(
            VAD_BASE_SILENCE_MS,
            min(threshold, 650),
        )

    return int(threshold)


def _adaptive_silence_elapsed_ms(s):

    return (
        1000.0
        * float(s.adaptive_silence_samples or 0)
        / SR
    )


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



def _batisay_once(audio, *, anti_loop=False):

    generate_kwargs = {
        "language": "korean",
        "task": "transcribe",
    }

    # BatiSay 1.1 already ships repetition suppression in generation_config.
    # This retry is only an extra defense if our detector still catches a
    # degenerate output.
    if anti_loop:
        generate_kwargs.update({
            "repetition_penalty": 1.35,
            "no_repeat_ngram_size": 3,
        })

    result = batisay_pipe(
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


def batisay_transcribe(audio):

    if audio is None or len(audio) == 0:
        return "", False, ""

    duration = len(audio) / SR

    print(
        f"[BATISAY] {duration:.2f}s",
        flush=True,
    )

    text = _batisay_once(
        audio,
        anti_loop=False,
    )

    print(
        "[BATISAY RAW]",
        text,
        flush=True,
    )

    bad, reason = detect_repetition_loop(text)

    if not bad:
        return text, False, ""

    print(
        "[BATISAY LOOP DETECTED]",
        reason,
        flush=True,
    )

    try:
        retry = _batisay_once(
            audio,
            anti_loop=True,
        )

        retry_bad, retry_reason = (
            detect_repetition_loop(retry)
        )

        print(
            "[BATISAY RETRY]",
            retry,
            flush=True,
        )

        if retry and not retry_bad:
            print(
                "[BATISAY RETRY RECOVERED]",
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
            "[BATISAY RETRY ERROR]",
            repr(e),
            flush=True,
        )

    # Preserve the raw output for audit, but do not promote a detected loop
    # into the segment. Qwen3-ASR realtime is the safe fallback.
    return text, True, reason


# =========================================================
# WHOLE-SESSION POSTPROCESS
# V6.4.2: Qwen3.8 is intentionally used ONLY here, not per segment.
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
        return transcript, "segment-stt-pass"

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
            "segment-stt-pass",
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
# V6.3 SESSION / POSTPROCESS STATE HELPERS
# =========================================================

POSTPROCESS_STAGE_LABELS = {
    "prepare": "Transcript 준비",
    "whole_review": "전체 강의 문맥 교정",
    "metadata": "AI 태그 / 설명 생성",
    "save": "결과 검증 / 저장",
    "done": "후처리 완료",
    "error": "후처리 실패",
}


def _invalidate_generated_session_outputs(s, *, reason="transcript_changed"):
    """Invalidate only generated whole-session artifacts.

    Caller holds ``s.lock``. Human transcript edits and human-created tags are
    preserved. This is used when a stopped session is resumed and therefore
    its transcript may grow after a previous final review.
    """

    s.postprocess_status = "not_run"
    s.whole_reviewed_text = ""
    s.postprocess_progress = {}

    for stale in [
        s.root / "final.json",
        s.root / "final_segments.json",
    ]:
        try:
            stale.unlink()
        except FileNotFoundError:
            pass

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
    session_meta.pop("ai_metadata_generated_at", None)
    session_meta.pop("postprocess_error", None)
    session_meta["postprocess_invalidated_reason"] = reason
    session_meta["postprocess_invalidated_at"] = _now_iso()

    _write_json_path(
        s.root / "session.json",
        session_meta,
    )


def _postprocess_progress_public(s):
    p = dict(s.postprocess_progress or {})

    status = str(
        p.get("status")
        or s.postprocess_status
        or "not_run"
    )

    started_monotonic = p.get("_started_monotonic")
    elapsed = p.get("elapsed_sec")

    if status == "running" and started_monotonic is not None:
        elapsed = max(
            0.0,
            time.monotonic() - float(started_monotonic),
        )

    if not p and status == "done":
        p = {
            "status": "done",
            "stage": "done",
            "stage_label": POSTPROCESS_STAGE_LABELS["done"],
            "stage_index": 4,
            "stage_total": 4,
            "progress": 1.0,
            "message": "후처리 완료",
        }
    elif not p and status == "error":
        p = {
            "status": "error",
            "stage": "error",
            "stage_label": POSTPROCESS_STAGE_LABELS["error"],
            "stage_index": 0,
            "stage_total": 4,
            "progress": 0.0,
            "message": "이전 후처리가 완료되지 않았습니다.",
        }

    progress = float(p.get("progress") or 0.0)
    progress = max(0.0, min(1.0, progress))

    eta = p.get("eta_sec")
    if eta is not None:
        try:
            eta = max(0.0, float(eta))
        except Exception:
            eta = None

    return {
        "status": status,
        "stage": str(p.get("stage") or ""),
        "stage_label": str(
            p.get("stage_label")
            or POSTPROCESS_STAGE_LABELS.get(
                str(p.get("stage") or ""),
                "",
            )
        ),
        "stage_index": int(p.get("stage_index") or 0),
        "stage_total": int(p.get("stage_total") or 4),
        "progress": round(progress, 4),
        "percent": int(round(progress * 100)),
        "message": str(p.get("message") or ""),
        "elapsed_sec": (
            round(float(elapsed), 1)
            if elapsed is not None
            else None
        ),
        "eta_sec": (
            round(float(eta), 1)
            if eta is not None
            else None
        ),
        "started_at": p.get("started_at"),
        "completed_at": p.get("completed_at"),
        "error": p.get("error"),
    }


def _set_postprocess_progress(
    s,
    *,
    stage,
    stage_index,
    progress,
    message,
    eta_sec=None,
    status="running",
    error=None,
):
    """Update frequent progress in memory without rewriting JSON per token."""

    with s.lock:
        previous = dict(s.postprocess_progress or {})

        started_at = previous.get("started_at") or _now_iso()
        started_monotonic = previous.get("_started_monotonic")
        if started_monotonic is None:
            started_monotonic = time.monotonic()

        completed_at = previous.get("completed_at")
        elapsed_sec = previous.get("elapsed_sec")

        if status in ("done", "error"):
            elapsed_sec = max(
                0.0,
                time.monotonic() - float(started_monotonic),
            )
            completed_at = _now_iso()
            eta_sec = 0.0 if status == "done" else None

        s.postprocess_progress = {
            "status": status,
            "stage": stage,
            "stage_label": POSTPROCESS_STAGE_LABELS.get(stage, stage),
            "stage_index": stage_index,
            "stage_total": 4,
            "progress": max(0.0, min(1.0, float(progress))),
            "message": message,
            "eta_sec": eta_sec,
            "started_at": started_at,
            "completed_at": completed_at,
            "elapsed_sec": elapsed_sec,
            "error": error,
            "_started_monotonic": started_monotonic,
        }



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
    segment_stt_raw,
    final_text,
    final_source,
    segment_stt_rejected=False,
    segment_stt_reject_reason="",
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

    # WAV is normally saved immediately at the boundary before BatiSay.
    if not wav_path.exists():
        save_wav(
            wav_path,
            audio,
        )

    record = {
        "segment": index,
        "session_id": s.session_id,
        "title": s.title,
        "audio": f"segments/{wav_name}",
        "duration_sec": round(
            len(audio) / SR,
            3,
        ),
        "qwen_raw": qwen_raw,
        "segment_stt_raw": segment_stt_raw,
        "segment_stt_model": BATISAY_MODEL_ID,
        "segment_stt_rejected": bool(segment_stt_rejected),
        "segment_stt_reject_reason": segment_stt_reject_reason or None,
        "final_text": final_text,
        "final_source": final_source,
        "processing_status": "done",
        "processing_error": processing_error or None,
        "created_at": _now_iso(),
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
    s.adaptive_silence_active = False
    s.adaptive_silence_samples = 0

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
    reset happen synchronously. BatiSay inference runs in the background worker.
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
        "segment_stt_raw": "",
        "segment_stt_model": BATISAY_MODEL_ID,
        "segment_stt_rejected": False,
        "segment_stt_reject_reason": "",
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
        "[BATISAY WORKER] started",
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

        segment_stt_raw = ""
        segment_stt_rejected = False
        segment_stt_reason = ""
        processing_error = ""

        try:
            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending["status"] = "batisay"

            (
                segment_stt_raw,
                segment_stt_rejected,
                segment_stt_reason,
            ) = batisay_transcribe(audio)

            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending.update({
                        "status": "commit",
                        "segment_stt_raw": segment_stt_raw,
                        "segment_stt_rejected": segment_stt_rejected,
                        "segment_stt_reject_reason": segment_stt_reason,
                    })

            if segment_stt_raw and not segment_stt_rejected:
                final_text = segment_stt_raw
                final_source = "batisay"
            else:
                final_text = (
                    qwen_raw
                    or "[ASR 실패 — 원본 음성을 확인하세요]"
                )
                final_source = "qwen"

        except Exception as e:
            processing_error = repr(e)

            print(
                "[BATISAY WORKER ERROR]",
                f"segment={index}",
                processing_error,
                flush=True,
            )

            final_text = (
                qwen_raw
                or "[ASR 처리 실패 — 원본 음성을 확인하세요]"
            )
            final_source = "qwen"

        try:
            with s.lock:
                save_segment(
                    s,
                    index=index,
                    audio=audio,
                    qwen_raw=qwen_raw,
                    segment_stt_raw=segment_stt_raw,
                    final_text=final_text,
                    final_source=final_source,
                    segment_stt_rejected=segment_stt_rejected,
                    segment_stt_reject_reason=segment_stt_reason,
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
                    pending_count=len(s.pending_segments),
                )

            print(
                "[SEGMENT DONE]",
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



def api_resume():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = get_session_or_load(sid)

    if s is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

    with s.lock:

        if s.recording:
            return jsonify({
                "error": "session is already recording"
            }), 409

        if s.postprocess_status == "running":
            return jsonify({
                "error": "wait until postprocessing finishes before resuming"
            }), 409

        # A resumed session continues the same segment timeline.  Recreate
        # streaming model/VAD state when this session was loaded from disk.
        if s.qwen_state is None:
            s.qwen_state = new_qwen_state(
                s.title,
                s.subject_id,
            )
        else:
            reset_qwen_state(s)

        if s.vad is None:
            s.vad = new_vad()
        else:
            s.vad.reset_states()

        s.active = False
        s.vad_buffer = np.empty(0, dtype=np.float32)
        s.preroll = np.empty(0, dtype=np.float32)
        s.sentence_audio = np.empty(0, dtype=np.float32)
        s.qwen_parts = []
        s.adaptive_silence_active = False
        s.adaptive_silence_samples = 0
        s.qwen_samples = 0

        # New audio makes any previous whole-session review stale. Human
        # edits/manual tags survive; generated final text/tags/description do
        # not.
        _invalidate_generated_session_outputs(
            s,
            reason="recording_resumed",
        )

        s.recording = True

        meta = _read_json_path(
            s.root / "session.json",
            {},
        )
        resume_count = int(
            meta.get("resume_count") or 0
        ) + 1

        update_session_metadata(
            s,
            resumed_at=_now_iso(),
            resume_count=resume_count,
            pending_count=len(s.pending_segments),
            postprocess_status="not_run",
        )

    start_sentence_worker(s)

    print(
        "[SESSION RESUMED]",
        sid,
        f"next_segment={s.segment_index + 1}",
        flush=True,
    )

    return jsonify(
        session_public_meta(s)
    )


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

    with s.lock:
        if not s.recording:
            return jsonify({
                "error": "session is stopped; resume it before sending audio"
            }), 409

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
        # V6.4 Adaptive Segmenter
        #
        # Silero's 450 ms end event is only a candidate. Short boxes wait up
        # to ~1.5 s, medium boxes ~1.0 s, and a ~3-line target box closes
        # around 0.6 s. If speech resumes first, the candidate is cancelled.
        # -------------------------------------------------

        if s.active and speech_start:
            if s.adaptive_silence_active:
                print(
                    "[ADAPTIVE SEGMENT] pause cancelled",
                    f"elapsed={_adaptive_silence_elapsed_ms(s):.0f}ms",
                    flush=True,
                )
            s.adaptive_silence_active = False
            s.adaptive_silence_samples = 0

        if s.active and speech_end and not speech_start:
            s.adaptive_silence_active = True
            s.adaptive_silence_samples = int(
                SR * VAD_BASE_SILENCE_MS / 1000
            )

        elif (
            s.active
            and s.adaptive_silence_active
            and not speech_start
        ):
            s.adaptive_silence_samples += len(wav)

        if s.active and s.adaptive_silence_active:
            threshold_ms = adaptive_silence_threshold_ms(s)
            elapsed_silence_ms = _adaptive_silence_elapsed_ms(s)

            if elapsed_silence_ms >= threshold_ms:
                boundary_reason = (
                    "adaptive_silence:"
                    f"{int(round(elapsed_silence_ms))}ms/"
                    f"{threshold_ms}ms"
                )
                boundary_index = enqueue_sentence(
                    s,
                    boundary_reason=boundary_reason,
                )

                max_pre = int(
                    SR * PREROLL_SEC
                )
                s.preroll = wav[-max_pre:].copy()

        # If the lecturer never pauses long enough, force a safe boundary so
        # BatiSay never receives an unbounded segment.
        if (
            boundary_index is None
            and s.active
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
            s.preroll = wav[-max_pre:].copy()

        # -------------------------------------------------
        # Qwen-only split.
        # BatiSay segment buffer is never split by this state reset.
        # -------------------------------------------------

        elif (
            boundary_index is None
            and s.active
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


def _metadata_transcript_excerpt(transcript, budget=METADATA_TRANSCRIPT_CHAR_BUDGET):
    text = str(transcript or "").strip()
    if len(text) <= budget:
        return text

    # Sample five evenly spaced windows so tags are not biased toward only
    # the beginning/end of a long lecture.
    windows = 5
    each = max(600, budget // windows)
    max_start = max(0, len(text) - each)
    starts = [
        round(max_start * i / (windows - 1))
        for i in range(windows)
    ]
    parts = []
    for i, start in enumerate(starts, start=1):
        piece = text[start:start + each].strip()
        parts.append(f"[LECTURE SAMPLE {i}/{windows}]\n{piece}")
    return "\n\n...\n\n".join(parts)


def generate_ai_session_metadata(
    title,
    subject_name,
    transcript,
):

    if not LLM_BASE_URL:
        return [], ""

    metadata_transcript = _metadata_transcript_excerpt(transcript)

    prompt = f"""
SESSION TITLE:
{title}

COURSE / SUBJECT:
{subject_name if subject_name else "(not assigned)"}

FINAL TRANSCRIPT / REPRESENTATIVE SAMPLES:
{metadata_transcript}

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

    if not r.ok:
        body = (r.text or "").strip()
        raise RuntimeError(
            f"metadata LLM HTTP {r.status_code}: "
            + (body[:1200] if body else "empty error body")
        )

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
# V6.3 ASYNC POSTPROCESS API
# =========================================================

def _run_postprocess_worker(
    s,
    effective_segments,
    sentence_text,
):

    metadata_error = ""
    ai_tags = []
    description = ""
    tags = []
    final_text = ""
    source = ""
    final_segment_map = {}

    try:
        _set_postprocess_progress(
            s,
            stage="prepare",
            stage_index=1,
            progress=0.04,
            message="확정된 문장과 Human LOCK을 준비하는 중",
        )

        _set_postprocess_progress(
            s,
            stage="whole_review",
            stage_index=2,
            progress=0.08,
            message="Qwen3.8이 전체 강의 문맥을 교정하는 중",
        )

        whole_started = time.monotonic()
        last_progress_emit = [0.0]

        def whole_progress(
            generated_chars,
            expected_chars,
        ):
            now = time.monotonic()

            # UI polls at ~500 ms. Avoid taking the session lock for every
            # tiny SSE token while still keeping the bar visibly alive.
            if (
                now - last_progress_emit[0] < 0.20
                and generated_chars < expected_chars
            ):
                return

            last_progress_emit[0] = now

            expected = max(
                1,
                int(expected_chars),
            )
            generated = max(
                0,
                int(generated_chars),
            )

            ratio = min(
                0.98,
                generated / expected,
            )

            stage_elapsed = max(
                0.001,
                now - whole_started,
            )
            chars_per_sec = (
                generated / stage_elapsed
                if generated > 0
                else 0.0
            )

            eta = None
            if chars_per_sec > 0:
                eta = max(
                    0.0,
                    (expected - generated)
                    / chars_per_sec,
                )

            _set_postprocess_progress(
                s,
                stage="whole_review",
                stage_index=2,
                progress=(
                    0.08
                    + 0.72 * ratio
                ),
                message=(
                    "Qwen3.8이 전체 강의 문맥을 교정하는 중"
                    f" · {generated:,}/{expected:,} chars"
                ),
                eta_sec=eta,
            )

        final_text, source, final_segment_map = (
            whole_session_review_segments(
                title=s.title,
                segments=effective_segments,
                subject_name=
                    subject_name_for_id(
                        s.subject_id
                    ),
                progress_callback=
                    whole_progress,
            )
        )

        _set_postprocess_progress(
            s,
            stage="whole_review",
            stage_index=2,
            progress=0.82,
            message="전체 문맥 교정 결과와 세그먼트 경계를 검증하는 중",
            eta_sec=None,
        )

        _set_postprocess_progress(
            s,
            stage="metadata",
            stage_index=3,
            progress=0.86,
            message="핵심 태그와 세션 설명을 생성하는 중",
            eta_sec=None,
        )

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

        _set_postprocess_progress(
            s,
            stage="save",
            stage_index=4,
            progress=0.96,
            message="Human LOCK을 보존하고 최종 결과를 저장하는 중",
            eta_sec=None,
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

        _write_json_file(
            s.root / "final_segments.json",
            {
                "segments":
                    final_segment_map
            },
        )

        completed_at = _now_iso()

        final_data = {
            "session_id": s.session_id,
            "title": s.title,
            "subject_id": s.subject_id,
            "tags": tags,
            "description": description,
            "segment_transcript_text": sentence_text,
            # Legacy key kept so existing downstream readers do not break.
            "sentence_corrected_text": sentence_text,
            "whole_reviewed_text": final_text,
            "postprocess_status": "done",
            "final_source": source,
            "postprocessed_at": completed_at,
        }

        _write_json_path(
            s.root / "final.json",
            final_data,
        )

        with s.lock:
            progress = _postprocess_progress_public(s)
            elapsed = progress.get("elapsed_sec")

            # elapsed is recalculated below by _set_postprocess_progress; the
            # durable field is informational only and may lag by a fraction.
            s.postprocess_status = "done"

            update_session_metadata(
                s,
                postprocessed_at=completed_at,
                final_source=source,
                metadata_ai_error=(
                    metadata_error
                    if metadata_error
                    else None
                ),
                postprocess_elapsed_sec=elapsed,
            )

        _set_postprocess_progress(
            s,
            stage="done",
            stage_index=4,
            progress=1.0,
            message=(
                "전체 후처리와 AI 태깅이 완료됨"
                if not metadata_error
                else "전체 교정 완료 · AI 메타데이터 생성은 실패함"
            ),
            status="done",
        )

        # Save the final measured elapsed time after the progress state closes.
        with s.lock:
            done_progress = _postprocess_progress_public(s)
            update_session_metadata(
                s,
                postprocess_elapsed_sec=
                    done_progress.get(
                        "elapsed_sec"
                    ),
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

    except Exception as e:

        with s.lock:
            s.postprocess_status = "error"
            update_session_metadata(
                s,
                postprocess_error=repr(e),
            )

        current_progress = float(
            (s.postprocess_progress or {}).get(
                "progress",
                0.0,
            )
            or 0.0
        )

        _set_postprocess_progress(
            s,
            stage="error",
            stage_index=0,
            progress=current_progress,
            message="후처리 중 오류가 발생했습니다.",
            status="error",
            error=str(e),
        )

        print(
            "[POSTPROCESS ERROR]",
            repr(e),
            flush=True,
        )


def api_postprocess():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = get_session_or_load(sid)

    if s is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

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

        worker = s.postprocess_worker
        if (
            s.postprocess_status == "running"
            or (
                worker is not None
                and worker.is_alive()
            )
        ):
            return jsonify({
                "error":
                    "postprocessing already running",
                "postprocess_status": "running",
                "progress":
                    _postprocess_progress_public(s),
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
                "error": "transcript is empty"
            }), 400

        started_at = _now_iso()
        started_monotonic = time.monotonic()

        s.postprocess_status = "running"
        s.postprocess_progress = {
            "status": "running",
            "stage": "prepare",
            "stage_label":
                POSTPROCESS_STAGE_LABELS[
                    "prepare"
                ],
            "stage_index": 1,
            "stage_total": 4,
            "progress": 0.02,
            "message": "후처리 작업을 준비하는 중",
            "eta_sec": None,
            "started_at": started_at,
            "completed_at": None,
            "elapsed_sec": 0.0,
            "error": None,
            "_started_monotonic":
                started_monotonic,
        }

        update_session_metadata(
            s,
            postprocess_status="running",
            postprocess_started_at=started_at,
            postprocess_error=None,
        )

        worker = threading.Thread(
            target=_run_postprocess_worker,
            args=(
                s,
                effective_segments,
                sentence_text,
            ),
            daemon=True,
            name=(
                "clova-postprocess-"
                + s.session_id[-8:]
            ),
        )

        s.postprocess_worker = worker

    print()
    print(
        "==================================",
        flush=True,
    )
    print(
        "[POSTPROCESS QUEUED]",
        s.title,
        flush=True,
    )

    worker.start()

    return jsonify({
        "accepted": True,
        "session_id": s.session_id,
        "postprocess_status": "running",
        "progress":
            _postprocess_progress_public(s),
    }), 202


def api_postprocess_status():

    sid = request.args.get(
        "session_id",
        "",
    )

    s = get_session_or_load(sid)

    if s is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

    with s.lock:
        return jsonify(
            _postprocess_progress_public(s)
        )


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

        # V6.4 native field is segment_stt_raw. For archived V6.3 sessions,
        # transparently expose old Whisper output through the same audit layer.
        segment_stt_raw = (
            pending.get("segment_stt_raw")
            if pending
            else (
                record.get("segment_stt_raw")
                or record.get("whisper_raw")
            )
        )

        segment_stt_model = (
            pending.get("segment_stt_model")
            if pending
            else (
                record.get("segment_stt_model")
                or (
                    "openai/whisper-large-v3"
                    if record.get("whisper_raw")
                    else ""
                )
            )
        )

        segment_stt_rejected = bool(
            (
                pending.get("segment_stt_rejected")
                if pending
                else (
                    record.get("segment_stt_rejected")
                    if "segment_stt_rejected" in record
                    else record.get("whisper_rejected")
                )
            )
            or False
        )

        segment_stt_reject_reason = (
            pending.get("segment_stt_reject_reason")
            if pending
            else (
                record.get("segment_stt_reject_reason")
                or record.get("whisper_reject_reason")
            )
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
            "segment_stt_raw": segment_stt_raw,
            "segment_stt_model": segment_stt_model,
            "segment_stt_rejected": segment_stt_rejected,
            "segment_stt_reject_reason": segment_stt_reject_reason,

            # Legacy audit fields remain readable for old sessions only.
            "whisper_raw": record.get("whisper_raw"),
            "llm_corrected": record.get("llm_corrected"),
            "sentence_corrected": record.get("llm_corrected"),

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
            or record.get("segment_stt_raw")
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

    postprocess_status = str(
        meta.get("postprocess_status")
        or "not_run"
    )

    # A process restart cannot preserve an in-flight Python worker. Mark a
    # stale durable "running" state as interrupted instead of showing an
    # endless progress indicator after reboot.
    if postprocess_status == "running":
        postprocess_status = "error"
        meta["postprocess_status"] = "error"
        meta["postprocess_error"] = (
            "interrupted_by_process_restart"
        )
        meta["postprocess_interrupted_at"] = _now_iso()
        _write_json_path(
            root / "session.json",
            meta,
        )

    s = Session(
        session_id=session_id,
        title=title,
        root=root,
        qwen_state=None,
        vad=None,
        subject_id=subject_id,
        committed=committed,
        postprocess_status=
            postprocess_status,
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
        "postprocess_progress":
            _postprocess_progress_public(s),
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

        if s.postprocess_status == "running":
            return jsonify({
                "error": "wait until postprocessing finishes before changing session metadata"
            }), 409

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

def _whole_session_review_segments_single(
    title,
    segments,
    subject_name="",
    progress_callback=None,
):

    if not segments:

        return (
            "",
            "segment-stt-pass",
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
            bool(progress_callback),
    }


    print()
    print(
        "[WHOLE REVIEW / LOCK-AWARE]",
        flush=True,
    )


    stream_response = bool(
        progress_callback
    )

    r = requests.post(

        f"{LLM_BASE_URL}"
        "/v1/chat/completions",

        json=payload,

        timeout=300,

        stream=stream_response,
    )

    if not r.ok:
        body = (r.text or "").strip()
        raise RuntimeError(
            f"whole-session LLM HTTP {r.status_code}: "
            + (body[:1200] if body else "empty error body")
        )


    if not stream_response:

        output = (
            r.json()
            ["choices"][0]
            ["message"]
            ["content"]
        ).strip()

    else:

        output_parts = []
        generated_chars = 0
        expected_chars = max(
            1,
            len(marked_transcript),
        )

        for raw_line in r.iter_lines(
            decode_unicode=True
        ):

            if not raw_line:
                continue

            if isinstance(raw_line, bytes):
                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
            else:
                line = str(raw_line).strip()

            if line.startswith("data:"):
                data = line[5:].strip()
            else:
                data = line

            if data == "[DONE]":
                break

            try:
                event = json.loads(data)
            except Exception:
                continue

            choices = event.get("choices") or []
            if not choices:
                continue

            choice = choices[0] or {}
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}

            piece = (
                delta.get("content")
                or choice.get("text")
                or message.get("content")
                or ""
            )

            if not isinstance(piece, str):
                piece = str(piece or "")

            if not piece:
                continue

            output_parts.append(piece)
            generated_chars += len(piece)

            progress_callback(
                generated_chars,
                expected_chars,
            )

        output = "".join(
            output_parts
        ).strip()

        if not output:
            # Keep V6.2 reliability if a custom llama.cpp build returns an
            # unexpected streaming envelope. Retry once with the proven
            # non-stream OpenAI response instead of losing the postprocess.
            print(
                "[WHOLE REVIEW STREAM FALLBACK] retrying non-stream",
                flush=True,
            )

            fallback_payload = dict(payload)
            fallback_payload["stream"] = False

            fallback_response = requests.post(
                f"{LLM_BASE_URL}/v1/chat/completions",
                json=fallback_payload,
                timeout=300,
            )
            if not fallback_response.ok:
                body = (fallback_response.text or "").strip()
                raise RuntimeError(
                    f"whole-session fallback HTTP {fallback_response.status_code}: "
                    + (body[:1200] if body else "empty error body")
                )
            output = (
                fallback_response.json()
                ["choices"][0]
                ["message"]
                ["content"]
            ).strip()

            if not output:
                raise RuntimeError(
                    "empty whole-session LLM output"
                )


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
# V6.4.2 LONG-LECTURE WHOLE REVIEW
# =========================================================

def _postprocess_segment_cost(seg):
    # Includes a conservative allowance for the SEGMENT/END markers.
    return len(str(seg.get("text") or "")) + 96


def _build_postprocess_chunks(segments):
    chunks = []
    current = []
    current_chars = 0

    for seg in segments:
        cost = _postprocess_segment_cost(seg)
        would_overflow = (
            current
            and (
                current_chars + cost > POSTPROCESS_CHUNK_CHAR_BUDGET
                or len(current) >= POSTPROCESS_CHUNK_MAX_SEGMENTS
            )
        )

        if would_overflow:
            chunks.append(current)
            current = []
            current_chars = 0

        current.append(seg)
        current_chars += cost

    if current:
        chunks.append(current)

    return chunks


def whole_session_review_segments(
    title,
    segments,
    subject_name="",
    progress_callback=None,
):
    """Review arbitrarily long lectures without overflowing llama.cpp context.

    Target chunks are corrected independently, while up to two neighboring
    segments on each side are supplied as LOCKED context.  Only the target
    segments are committed, so overlap can never duplicate or reorder text.
    Human-edited segments remain LOCKED in every request.
    """

    if not segments:
        return "", "segment-stt-pass", {}

    chunks = _build_postprocess_chunks(segments)

    if len(chunks) == 1:
        return _whole_session_review_segments_single(
            title=title,
            segments=segments,
            subject_name=subject_name,
            progress_callback=progress_callback,
        )

    print(
        f"[WHOLE REVIEW CHUNKED] {len(segments)} segments -> {len(chunks)} chunks "
        f"(budget={POSTPROCESS_CHUNK_CHAR_BUDGET} chars)",
        flush=True,
    )

    position = {
        int(seg["segment"]): i
        for i, seg in enumerate(segments)
    }
    final_map = {}
    total_target_chars = max(
        1,
        sum(_postprocess_segment_cost(seg) for seg in segments),
    )
    completed_target_chars = 0

    for chunk_index, target_chunk in enumerate(chunks, start=1):
        first_pos = position[int(target_chunk[0]["segment"])]
        last_pos = position[int(target_chunk[-1]["segment"])]

        context_start = max(0, first_pos - POSTPROCESS_CONTEXT_SEGMENTS)
        context_end = min(
            len(segments),
            last_pos + 1 + POSTPROCESS_CONTEXT_SEGMENTS,
        )

        target_ids = {int(seg["segment"]) for seg in target_chunk}
        request_segments = []

        for seg in segments[context_start:context_end]:
            copy = dict(seg)
            if int(copy["segment"]) not in target_ids:
                # Neighboring overlap is context only. LOCKED guarantees the
                # model cannot rewrite it, and its output is ignored below.
                copy["locked"] = True
            request_segments.append(copy)

        target_expected = max(
            1,
            sum(_postprocess_segment_cost(seg) for seg in target_chunk),
        )

        print(
            f"[WHOLE REVIEW CHUNK {chunk_index}/{len(chunks)}] "
            f"SEG {target_chunk[0]['segment']}..{target_chunk[-1]['segment']}",
            flush=True,
        )

        def chunk_progress(generated_chars, expected_chars):
            if not progress_callback:
                return
            local_ratio = min(
                1.0,
                max(0.0, float(generated_chars) / max(1.0, float(expected_chars))),
            )
            estimated_done = completed_target_chars + int(
                target_expected * local_ratio
            )
            progress_callback(
                min(total_target_chars, estimated_done),
                total_target_chars,
            )

        _text, _source, chunk_map = _whole_session_review_segments_single(
            title=title,
            segments=request_segments,
            subject_name=subject_name,
            progress_callback=chunk_progress if progress_callback else None,
        )

        for seg in target_chunk:
            key = str(seg["segment"])
            final_map[key] = chunk_map.get(key, seg["text"])

        completed_target_chars += target_expected
        if progress_callback:
            progress_callback(
                min(total_target_chars, completed_target_chars),
                total_target_chars,
            )

    final_text = "\n".join(
        final_map.get(str(seg["segment"]), seg["text"])
        for seg in segments
    )

    return final_text, "whole-session-llm-chunked", final_map


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

        if s.postprocess_status == "running":
            return jsonify({
                "error": "wait until postprocessing finishes before editing"
            }), 409

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

    postprocess_running = sum(
        1
        for session in SESSIONS.values()
        if session.postprocess_status == "running"
    )

    if postprocess_running:
        return jsonify({
            "error": (
                f"{postprocess_running} postprocess job(s) are still running; "
                "wait for them to finish before app shutdown"
            ),
            "postprocess_running": postprocess_running,
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
            "Local Clova V6.3 UI is missing: /workspace/web/index_v6.html",
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
    global batisay_pipe

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
        "[2/2] Loading BatiSay-ko-large...",
        flush=True,
    )

    batisay_model = (
        AutoModelForSpeechSeq2Seq
        .from_pretrained(
            BATISAY_MODEL,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        )
    )

    batisay_model.to(
        "cuda:0"
    )

    processor = (
        AutoProcessor
        .from_pretrained(
            BATISAY_MODEL
        )
    )

    batisay_pipe = pipeline(
        "automatic-speech-recognition",
        model=batisay_model,
        tokenizer=
            processor.tokenizer,
        feature_extractor=
            processor.feature_extractor,
        torch_dtype=torch.float16,
        device=0,
    )

    print(
        "[READY] Qwen realtime + BatiSay segment STT",
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

    demo.app.add_url_rule(
        "/api/resume",
        "api_resume",
        api_resume,
        methods=["POST"],
    )

    # Async whole-session review
    demo.app.add_url_rule(
        "/api/postprocess",
        "api_postprocess",
        api_postprocess,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/postprocess/status",
        "api_postprocess_status",
        api_postprocess_status,
        methods=["GET"],
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
