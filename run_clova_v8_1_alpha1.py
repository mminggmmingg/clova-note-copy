import os
import json
import wave
import uuid
import threading
import queue
import re
import time
import hashlib
import shutil
import difflib
import subprocess
import gc
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

try:
    from peft import PeftModel
    PEFT_AVAILABLE = True
except Exception as _peft_import_error:
    PeftModel = None
    PEFT_AVAILABLE = False
    print("[ADAPTIVE ASR] PEFT unavailable:", repr(_peft_import_error), flush=True)

from audio_enhance_v7_9 import enhance_segment
from audio_capture_v8 import append_float32_mono_wav, normalize_stt_audio_source, wav_frame_count


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

# V6.4.3: browser/audio capture can disappear while the backend still has
# recording=True. A different tab may take over only after this lease is stale.
RECORDING_LEASE_TIMEOUT_SEC = 5.0

UNFIXED_CHUNK_NUM = 4
UNFIXED_TOKEN_NUM = 5
CHUNK_SIZE_SEC = 1.0

FORCE_LANGUAGE = "Korean"

QWEN_ASR_MODEL = "/workspace/Qwen3-ASR-1.7B"
BATISAY_MODEL = "/workspace/batisay-ko-large"
BATISAY_MODEL_ID = "batiai/batisay-ko-large"

# V7.8 lecture audio enhancement. Raw segment WAVs remain the immutable
# source of truth; cleaned derivatives are stored separately.
DENOISE_BIN = Path(os.getenv("DENOISE_BIN", "/workspace/tools/deep-filter"))
DENOISE_ENABLED = os.getenv("DENOISE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
DENOISE_TIMEOUT_SEC = float(os.getenv("DENOISE_TIMEOUT_SEC", "90"))
DENOISE_POST_FILTER = os.getenv("DENOISE_POST_FILTER", "1").strip().lower() not in {"0", "false", "off", "no"}
DENOISE_PF_BETA = float(os.getenv("DENOISE_PF_BETA", "0.04"))
DENOISE_ATTEN_LIM_DB = float(os.getenv("DENOISE_ATTEN_LIM_DB", "100"))
DENOISE_MODEL_ID = "DeepFilterNet2-v0.5.6"
DENOISE_STRENGTH_DEFAULT = max(0, min(3, int(os.getenv("DENOISE_STRENGTH_DEFAULT", "2"))))
STT_AUDIO_SOURCE_DEFAULT = normalize_stt_audio_source(os.getenv("STT_AUDIO_SOURCE_DEFAULT", "raw"))
AUDIO_PROVENANCE_SCHEMA = "v8.0-alpha.1-audio-v1"
PDF_WORKSPACE_SCHEMA = "v8.0-beta.6-pdf-workspace-v3"


def denoise_profile(strength):
    """Map the UI's 0..3 strength control to speech-preserving DF settings.

    0 = off (raw copied to clean derivative), 1 = light, 2 = standard
    (the V7.4.1 profile), 3 = strong. The global DENOISE_ENABLED switch
    remains the hard override.
    """
    try:
        level = max(0, min(3, int(strength)))
    except Exception:
        level = DENOISE_STRENGTH_DEFAULT

    if level == 0:
        return {"level": 0, "name": "off", "enabled": False, "post_filter": False, "pf_beta": 0.0}
    if level == 1:
        return {"level": 1, "name": "light", "enabled": True, "post_filter": False, "pf_beta": 0.0}
    if level == 3:
        return {"level": 3, "name": "strong", "enabled": True, "post_filter": True, "pf_beta": max(0.06, DENOISE_PF_BETA * 1.5)}
    return {"level": 2, "name": "standard", "enabled": True, "post_filter": bool(DENOISE_POST_FILTER), "pf_beta": DENOISE_PF_BETA}

APP_DATA_ROOT = Path("/workspace/data")
DATA_ROOT = APP_DATA_ROOT / "sessions"
SUBJECTS_FILE = APP_DATA_ROOT / "subjects.json"
PROFESSORS_FILE = APP_DATA_ROOT / "professors.json"
PROFESSORS_ROOT = APP_DATA_ROOT / "professors"
TRASH_ROOT = APP_DATA_ROOT / "trash"
TRASH_SESSIONS_ROOT = TRASH_ROOT / "sessions"
DENOISE_TMP_ROOT = APP_DATA_ROOT / ".denoise_tmp"
UI_ROOT = Path("/workspace/web")
PDF_LIBRARY_ROOT = Path("/workspace/pdfs")
PDF_MAX_BYTES = max(1, int(os.getenv("PDF_MAX_MB", "200"))) * 1024 * 1024
PDF_ID_RE = re.compile(r"^pdf_[0-9a-f]{16}$")
PDF_TIMELINE_SCHEMA = "v8.0-gamma-pdf-events-v1"
PDF_EVENTS_FILENAME = "pdf_events.jsonl"
PDF_SEMANTIC_TIMELINE_SCHEMA = "v8.0-eta-pdf-semantic-timeline-v1"
PDF_SEMANTIC_TIMELINE_FILENAME = "pdf_semantic_timeline.json"
ANNOTATION_SCHEMA = "v8.1-alpha.1-annotation-events-v2"
ANNOTATION_EVENTS_FILENAME = "annotation_events.jsonl"
ANNOTATION_TOOLS = {"pen", "highlighter"}
ANNOTATION_STYLE = {
    "pen": {"color": "#2563c7", "opacity": 1.0, "width_norm": 0.0024},
    "highlighter": {"color": "#f3d34a", "opacity": 0.34, "width_norm": 0.018},
}
PDF_DWELL_IGNORE_LT = 1.5
PDF_DWELL_WEAK_LT = 4.0
PDF_DWELL_INCLUDE_LT = 10.0

APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
DATA_ROOT.mkdir(parents=True, exist_ok=True)
TRASH_SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
DENOISE_TMP_ROOT.mkdir(parents=True, exist_ok=True)
PROFESSORS_ROOT.mkdir(parents=True, exist_ok=True)
PDF_LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# V8.1-alpha.1 Annotation Layer + V8.0 Semantic/Playback/PDF Master Timeline
# Based on V7.9.3 Adaptive Professor ASR
#
# Qwen3.8 whole-session postprocess is intentionally removed.
# Human corrections become supervised audio/text data; professor-specific
# BatiSay LoRA adapters are trained offline and swapped at inference time.
# ---------------------------------------------------------

LLM_BASE_URL = ""
LLM_MODEL = "REMOVED-IN-V7.9"
POSTPROCESS_CHUNK_CHAR_BUDGET = 0
POSTPROCESS_CHUNK_MAX_SEGMENTS = 0
POSTPROCESS_CONTEXT_SEGMENTS = 0
POSTPROCESS_LLM_READ_TIMEOUT_SEC = 0
POSTPROCESS_MIN_SPLIT_SEGMENTS = 0
METADATA_TRANSCRIPT_CHAR_BUDGET = 0

LORA_MIN_SAMPLES = int(os.getenv("LORA_MIN_SAMPLES", "12"))
LORA_MIN_NEW_SAMPLES = int(os.getenv("LORA_MIN_NEW_SAMPLES", "8"))
LORA_TRAIN_MAX_STEPS = int(os.getenv("LORA_TRAIN_MAX_STEPS", "240"))
LORA_TRAIN_EPOCHS = int(os.getenv("LORA_TRAIN_EPOCHS", "1"))
LORA_TRAIN_LR = float(os.getenv("LORA_TRAIN_LR", "1e-4"))
LORA_TRAIN_SCRIPT = Path("/workspace/professor_lora_v7_9.py")
LORA_PHRASE_MARGIN_SEC = float(os.getenv("LORA_PHRASE_MARGIN_SEC", "0.20"))
HISTORICAL_ALIGNMENT_MIN_RATIO = float(os.getenv("HISTORICAL_ALIGNMENT_MIN_RATIO", "0.60"))
HISTORICAL_ALIGNMENT_MIN_COVERAGE = float(os.getenv("HISTORICAL_ALIGNMENT_MIN_COVERAGE", "0.60"))

DOMAIN_CONTEXT = "Korean university lecture; adaptive professor ASR is enabled."

# =========================================================
# GLOBAL MODELS
# =========================================================

qwen_asr = None
batisay_pipe = None
batisay_model = None
batisay_processor = None
BATISAY_MODEL_LOCK = threading.RLock()
BATISAY_ACTIVE_ADAPTER = {"professor_id": "", "version": "", "name": "base"}

SESSIONS = {}
SUBJECTS_LOCK = threading.Lock()
PROFESSORS_LOCK = threading.Lock()
TRAINING_LOCK = threading.Lock()
TRAINING_THREAD = None
TRAINING_PROFESSOR_ID = ""


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


def load_professors():

    data = _read_json_path(
        PROFESSORS_FILE,
        {"professors": []},
    )
    profs = data.get("professors", [])
    if not isinstance(profs, list):
        return []
    return [
        x for x in profs
        if isinstance(x, dict) and x.get("id") and x.get("name")
    ]


def save_professors(professors):

    _write_json_path(
        PROFESSORS_FILE,
        {"professors": professors},
    )


def professor_by_id(professor_id):

    if not professor_id:
        return None
    for prof in load_professors():
        if prof.get("id") == professor_id:
            return prof
    return None


def ensure_professor(name="", professor_id=""):
    """Resolve/create a professor profile. Names are case-fold deduplicated."""
    name = str(name or "").strip()
    professor_id = str(professor_id or "").strip()

    with PROFESSORS_LOCK:
        professors = load_professors()
        if professor_id:
            for prof in professors:
                if prof.get("id") == professor_id:
                    return prof
        if name:
            folded = name.casefold()
            for prof in professors:
                if str(prof.get("name") or "").strip().casefold() == folded:
                    return prof
        if not name:
            return None
        prof = {
            "id": "prof-" + uuid.uuid4().hex[:10],
            "name": name,
            "created_at": _now_iso(),
        }
        professors.append(prof)
        save_professors(professors)
        root = PROFESSORS_ROOT / prof["id"]
        (root / "training_audio").mkdir(parents=True, exist_ok=True)
        (root / "adapters").mkdir(parents=True, exist_ok=True)
        _write_json_path(root / "profile.json", {
            "professor_id": prof["id"],
            "name": name,
            "adapter_version": 0,
            "active_adapter": "",
            "history": [],
            "trained_sample_ids": [],
        })
        return prof


def professor_for_subject(subject_id):

    subject = subject_by_id(subject_id)
    if not subject:
        return None
    return professor_by_id(str(subject.get("professor_id") or ""))


def professor_name_for_subject(subject_id):

    prof = professor_for_subject(subject_id)
    return str((prof or {}).get("name") or "")


def professor_root(professor_id):
    return PROFESSORS_ROOT / str(professor_id or "")


def professor_runtime_profile(professor_id):
    if not professor_id:
        return {}
    return _read_json_path(professor_root(professor_id) / "profile.json", {})


def professor_training_pool(professor_id):
    data = _read_json_path(
        professor_root(professor_id) / "training_pool.json",
        {"samples": {}},
    )
    samples = data.get("samples", {})
    return samples if isinstance(samples, dict) else {}


def save_professor_training_pool(professor_id, samples):
    root = professor_root(professor_id)
    root.mkdir(parents=True, exist_ok=True)
    _write_json_path(root / "training_pool.json", {"samples": samples})


def professor_adaptive_summary(professor_id):
    prof = professor_by_id(professor_id) or {}
    profile = professor_runtime_profile(professor_id)
    pool = professor_training_pool(professor_id)
    status = _read_json_path(
        professor_root(professor_id) / "training_status.json",
        {"status": "idle"},
    ) if professor_id else {"status": "no_professor"}
    usable = [x for x in pool.values() if isinstance(x, dict) and not x.get("disabled")]
    total_audio = 0.0
    phrase_count = 0
    utterance_count = 0
    for item in usable:
        try:
            total_audio += float(item.get("duration_sec") or 0.0)
        except Exception:
            pass
        if item.get("kind") == "phrase":
            phrase_count += 1
        elif item.get("kind") == "utterance":
            utterance_count += 1
    trained_ids = {str(x) for x in (profile.get("trained_sample_ids") or [])}
    validation_groups = {str(x) for x in (profile.get("validation_group_keys") or [])}

    def group_key(item):
        session = str(item.get("source_session") or "")
        segment = str(item.get("source_segment") or "")
        if session and segment:
            return f"{session}:{segment}"
        return str(item.get("id") or "")

    usable_ids = {str(x.get("id") or "") for x in usable}
    correction_groups = {group_key(x) for x in usable if group_key(x)}
    new_trainable = [
        x for x in usable
        if str(x.get("id") or "") not in trained_ids
        and group_key(x) not in validation_groups
    ]
    new_correction_groups = {group_key(x) for x in new_trainable if group_key(x)}

    return {
        "professor_id": professor_id or "",
        "professor_name": str(prof.get("name") or ""),
        "peft_available": bool(PEFT_AVAILABLE),
        "active_adapter": str(profile.get("active_adapter") or ""),
        "adapter_version": int(profile.get("adapter_version") or 0),
        "metrics": profile.get("metrics") or {},
        "previous_metrics": profile.get("previous_metrics") or {},
        "sample_count": len(usable),
        "correction_count": len(correction_groups),
        "phrase_count": phrase_count,
        "utterance_count": utterance_count,
        "audio_sec": round(total_audio, 3),
        "trained_sample_count": len(usable_ids & trained_ids),
        "new_sample_count": len(new_trainable),
        "new_correction_count": len(new_correction_groups),
        "training_status": status,
        "min_samples": LORA_MIN_SAMPLES,
        "min_new_samples": LORA_MIN_NEW_SAMPLES,
    }


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
    denoise_strength: int = DENOISE_STRENGTH_DEFAULT
    stt_audio_source: str = STT_AUDIO_SOURCE_DEFAULT

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

    # V6.4.3 recorder lease. ``recording_client_id`` identifies the browser
    # tab that owns live capture. ``last_chunk_monotonic`` lets a new tab take
    # over a stale recording after a browser crash/reload without creating a
    # second simultaneous audio source.
    recording_client_id: str = ""
    last_chunk_monotonic: float = 0.0

    active: bool = False
    qwen_samples: int = 0

    # V6.4 adaptive segmentation. Silero's end event starts a silence
    # candidate; it is cancelled if speech resumes before the adaptive cutoff.
    adaptive_silence_active: bool = False
    adaptive_silence_samples: int = 0

    segment_index: int = 0

    # V8.0-alpha master recording clock. This cursor advances only by audio
    # samples accepted from /api/chunk while recording. It is source-recording
    # time, not wall-clock time; deliberate stop/resume gaps do not advance it.
    recording_sample_cursor: int = 0
    recording_time_exact: bool = True
    recording_time_basis: str = "accepted_capture_samples"
    recording_checkpoint_sample: int = 0

    # V8.0-alpha.1 continuous raw capture. Every accepted browser sample is
    # persisted before VAD segmentation so VAD can never destroy provenance.
    continuous_raw_start_sample: int = 0
    continuous_raw_samples: int = 0

    # Source-time anchor for the currently accumulating SEG. -1 means no
    # active SEG. Preroll may make adjacent SEG spans overlap; that overlap is
    # truthful provenance and must not be compressed away.
    sentence_recording_start_sample: int = -1

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
    """Realtime Qwen3-ASR deliberately receives no session metadata.

    V7.7 removes title/subject hints from the streaming ASR path entirely.
    BatiSay is the committed segment recognizer. V7.9.3 keeps Qwen3.8 removed
    post-processing entirely, so leaking metadata into a realtime hypothesis
    is a worse failure mode than losing the small hinting benefit here.
    """

    return ""


_QWEN_ASR_TRAILING_TOKENS = (
    "<|im_end|>",
    "<|endoftext|>",
    "<|eot_id|>",
    "</s>",
)

_QWEN_ASR_STATIC_PROMPT_FRAGMENTS = (
    "Korean university lecture audio.",
    "Korean lecture speech.",
    "Korean speech may contain English technical terms, symbols, acronyms, and proper nouns.",
)


def _subject_text_for_sanitizer(subject_id):
    subject = subject_name_for_id(subject_id)
    return str(subject or "").strip()


def sanitize_qwen_asr_text(raw, title="", subject_id=""):
    """Strip Qwen3-ASR prompt/chat leakage while preserving spoken prefix.

    V7.7 hardens both live and archived transcript rendering. Qwen3-ASR can
    occasionally echo its context inside an otherwise-valid hypothesis, e.g.
    Korean speech followed by ``Session topic is ...``. When a leak starts
    after real speech we keep the spoken prefix; when the payload is only
    prompt serialization we reject it entirely.
    """

    original = str(raw or "")
    text = original.replace("\x00", "").strip()
    if not text:
        return ""

    marker = "<asr_text>"
    if marker in text:
        text = text.rsplit(marker, 1)[1].strip()

    # Remove common special-token wrappers before role detection.
    text = re.sub(
        r"<\|im_start\|>\s*(?:system|user|assistant)?\s*",
        "",
        text,
        flags=re.I,
    )
    for token in _QWEN_ASR_TRAILING_TOKENS:
        text = text.replace(token, "")

    # If an explicit assistant role exists, only the assistant payload can be
    # speech. This handles multiline chat-template serialization.
    role_matches = list(
        re.finditer(
            r"(?:^|\n)assistant\s*(?:\n|:)"
            r"(?:\s*language\s+[A-Za-z_-]+\s*)?",
            text,
            flags=re.I,
        )
    )
    if role_matches:
        text = text[role_matches[-1].end():].strip()

    text = re.sub(
        r"^\s*language\s+[A-Za-z_-]+\s*",
        "",
        text,
        flags=re.I,
    ).strip()

    subject = _subject_text_for_sanitizer(subject_id)
    title = str(title or "").strip()

    # Remove complete known context sentences wherever they appear.
    for fragment in _QWEN_ASR_STATIC_PROMPT_FRAGMENTS:
        text = re.sub(re.escape(fragment), " ", text, flags=re.I)

    # Dynamic metadata labels are particularly dangerous because they can be
    # copied into Korean speech with no role delimiter. Truncate at the first
    # label if meaningful speech already precedes it; otherwise remove it.
    dynamic_patterns = [
        r"\bSession\s+topic\s+is\b",
        r"\bCourse\s+is\b",
        r"\blanguage\s+Korean\b",
        r"SESSION\s+TITLE\s*:",
        r"COURSE\s*/\s*SUBJECT\s*:",
    ]
    leak_positions = []
    for pattern in dynamic_patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            leak_positions.append(match.start())

    if leak_positions:
        leak_start = min(leak_positions)
        prefix = text[:leak_start].strip(" \n\t·,;:-")

        # Older sessions may have echoed the course label immediately before
        # ``Session topic is`` (for example "2026-2 · YouTube."). Because a
        # prompt marker has already proven this tail is metadata, strip the
        # known course name/semester only from the very end of the prefix.
        subject_obj = subject_by_id(subject_id) if subject_id else None
        if subject_obj and prefix:
            semester = str(subject_obj.get("semester") or "").strip()
            name = str(subject_obj.get("name") or "").strip()
            if name:
                pieces = []
                if semester:
                    pieces.append(re.escape(semester) + r"[\s·.,:/_-]*")
                pieces.append(re.escape(name))
                tail_pattern = r"(?:" + "".join(pieces) + r")[\s·.,;:!?-]*$"
                prefix = re.sub(tail_pattern, "", prefix, flags=re.I).strip(" \n\t·,;:-")

        if len(prefix) >= 4:
            print(
                "[QWEN ASR SANITIZER] truncated inline prompt leak",
                repr(text[leak_start:leak_start + 180]),
                flush=True,
            )
            text = prefix
        else:
            print(
                "[QWEN ASR SANITIZER] rejected prompt-only hypothesis",
                repr(text[:180]),
                flush=True,
            )
            return ""

    # Exact title/subject prompt sentences from pre-V7.7 recordings. These are
    # only removed when accompanied by prompt-like wording to avoid deleting a
    # lecturer genuinely saying the course/title name.
    if subject:
        text = re.sub(
            rf"Course\s+is\s+{re.escape(subject)}\s*[.!]?",
            " ",
            text,
            flags=re.I,
        )
    if title:
        text = re.sub(
            rf"Session\s+topic\s+is\s+{re.escape(title)}\s*[.!]?",
            " ",
            text,
            flags=re.I,
        )

    # Stray role lines mean serialization survived without a trustworthy
    # delimiter. Preserve a spoken prefix if one exists; otherwise reject.
    role_or_context = re.search(
        r"(?:^|\n)\s*(?:system|user)\s*(?:$|\n|:)",
        text,
        flags=re.I,
    )
    if role_or_context:
        prefix = text[:role_or_context.start()].strip()
        if len(prefix) >= 4:
            text = prefix
        else:
            return ""

    text = re.sub(r"\s{2,}", " ", text).strip()
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
        raw,
        title=s.title,
        subject_id=s.subject_id,
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



def _rebuild_batisay_pipeline():
    global batisay_pipe
    if batisay_model is None or batisay_processor is None:
        batisay_pipe = None
        return
    batisay_pipe = pipeline(
        "automatic-speech-recognition",
        model=batisay_model,
        tokenizer=batisay_processor.tokenizer,
        feature_extractor=batisay_processor.feature_extractor,
        torch_dtype=torch.float16,
        device=0,
    )


def _disable_batisay_adapters_locked():
    """Guarantee base-model inference after an adapter switch failure.

    Caller must hold BATISAY_MODEL_LOCK. Without this guard, a failed switch
    could accidentally leave the previous professor's adapter active.
    """
    if PEFT_AVAILABLE and PeftModel is not None and isinstance(batisay_model, PeftModel):
        try:
            if hasattr(batisay_model, "disable_adapter_layers"):
                batisay_model.disable_adapter_layers()
        except Exception as exc:
            print("[ADAPTER] base disable warning", repr(exc), flush=True)


def ensure_batisay_adapter(professor_id=""):
    """Activate the latest promoted professor LoRA, or base BatiSay."""
    global batisay_model
    global BATISAY_ACTIVE_ADAPTER

    professor_id = str(professor_id or "").strip()
    profile = professor_runtime_profile(professor_id) if professor_id else {}
    version = str(profile.get("active_adapter") or "").strip()

    with BATISAY_MODEL_LOCK:
        current = dict(BATISAY_ACTIVE_ADAPTER)
        if (
            current.get("professor_id") == professor_id
            and current.get("version") == version
        ):
            return current

        if not version:
            _disable_batisay_adapters_locked()
            BATISAY_ACTIVE_ADAPTER = {
                "professor_id": professor_id,
                "version": "",
                "name": "base",
            }
            print("[ADAPTER] BatiSay base", f"professor={professor_id or '-'}", flush=True)
            return dict(BATISAY_ACTIVE_ADAPTER)

        if not PEFT_AVAILABLE or PeftModel is None:
            print("[ADAPTER WARN] promoted adapter exists but PEFT is unavailable", flush=True)
            BATISAY_ACTIVE_ADAPTER = {
                "professor_id": professor_id,
                "version": "",
                "name": "base-peft-unavailable",
            }
            return dict(BATISAY_ACTIVE_ADAPTER)

        adapter_path = professor_root(professor_id) / "adapters" / version
        if not adapter_path.is_dir():
            print("[ADAPTER WARN] missing adapter", adapter_path, flush=True)
            _disable_batisay_adapters_locked()
            BATISAY_ACTIVE_ADAPTER = {"professor_id": professor_id, "version": "", "name": "base-missing-adapter"}
            return dict(BATISAY_ACTIVE_ADAPTER)

        adapter_name = f"{professor_id}_{version}".replace("-", "_")
        try:
            if isinstance(batisay_model, PeftModel):
                loaded = getattr(batisay_model, "peft_config", {})
                if adapter_name not in loaded:
                    batisay_model.load_adapter(str(adapter_path), adapter_name=adapter_name, is_trainable=False)
                if hasattr(batisay_model, "enable_adapter_layers"):
                    batisay_model.enable_adapter_layers()
                batisay_model.set_adapter(adapter_name)
            else:
                batisay_model = PeftModel.from_pretrained(
                    batisay_model,
                    str(adapter_path),
                    adapter_name=adapter_name,
                    is_trainable=False,
                )
                _rebuild_batisay_pipeline()

            BATISAY_ACTIVE_ADAPTER = {
                "professor_id": professor_id,
                "version": version,
                "name": adapter_name,
            }
            print("[ADAPTER ACTIVE]", professor_id, version, flush=True)
        except Exception as exc:
            print("[ADAPTER ERROR]", repr(exc), flush=True)
            _disable_batisay_adapters_locked()
            BATISAY_ACTIVE_ADAPTER = {
                "professor_id": professor_id,
                "version": "",
                "name": "base-adapter-error",
                "error": repr(exc),
            }
        return dict(BATISAY_ACTIVE_ADAPTER)


def _normalize_stt_chunks(result):
    chunks = []
    for item in (result or {}).get("chunks", []) or []:
        if not isinstance(item, dict):
            continue
        ts = item.get("timestamp")
        if not isinstance(ts, (list, tuple)) or len(ts) != 2:
            continue
        try:
            start = 0.0 if ts[0] is None else float(ts[0])
            end = start if ts[1] is None else float(ts[1])
        except Exception:
            continue
        chunks.append({
            "text": str(item.get("text") or ""),
            "timestamp": [round(max(0.0, start), 3), round(max(start, end), 3)],
        })
    return chunks


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
        return_timestamps="word",
    )

    return (
        (result.get("text", "") or "").strip(),
        _normalize_stt_chunks(result),
    )


def batisay_transcribe(audio, professor_id=""):

    if audio is None or len(audio) == 0:
        return "", False, "", [], {"name": "base", "version": "", "professor_id": professor_id or ""}

    duration = len(audio) / SR

    print(
        f"[BATISAY] {duration:.2f}s",
        flush=True,
    )

    with BATISAY_MODEL_LOCK:
        adapter_info = ensure_batisay_adapter(professor_id)
        text, chunks = _batisay_once(
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
        return text, False, "", chunks, adapter_info

    print(
        "[BATISAY LOOP DETECTED]",
        reason,
        flush=True,
    )

    try:
        with BATISAY_MODEL_LOCK:
            retry, retry_chunks = _batisay_once(
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
            ), retry_chunks, adapter_info

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
    return text, True, reason, chunks, adapter_info


# =========================================================
# WHOLE-SESSION POSTPROCESS
# V6.4: Qwen3.8 is intentionally used ONLY here, not per segment.
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

        "stt_audio_source": normalize_stt_audio_source(getattr(s, "stt_audio_source", STT_AUDIO_SOURCE_DEFAULT)),

        "postprocess_status":
            s.postprocess_status,
    })

    # V8.0-alpha: source recording time is durable and independent from
    # transcript visibility/deletion or compressed playback time.
    data.update(_timeline_meta_payload(s))

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
# V8.0-alpha MASTER RECORDING TIMELINE
# =========================================================

TIMELINE_SCHEMA_VERSION = "v8.0-alpha-recording-time-v1"

def _samples_to_sec(samples):
    return round(max(0, int(samples)) / float(SR), 6)

def _legacy_recording_cursor_from_records(records):
    """Best-effort cursor for pre-V8 sessions without silence-aware time."""
    max_end = 0.0
    cumulative = 0.0
    exact = False
    for record in records or []:
        try:
            cumulative += max(0.0, float(record.get("duration_sec") or 0.0))
        except Exception:
            pass
        try:
            end = record.get("recording_end")
            if end is not None:
                max_end = max(max_end, float(end))
                exact = True
        except Exception:
            pass
    seconds = max_end if exact else cumulative
    return int(round(seconds * SR)), ("recording_end" if exact else "legacy-cumulative-duration")

def _timeline_meta_payload(s):
    return {
        "timeline_schema": TIMELINE_SCHEMA_VERSION,
        "recording_time_basis": str(getattr(s, "recording_time_basis", "accepted_capture_samples")),
        "recording_time_exact": bool(getattr(s, "recording_time_exact", True)),
        "recording_paused_wall_time_excluded": True,
        "recording_samples": int(max(0, s.recording_sample_cursor)),
        "recording_time_sec": _samples_to_sec(s.recording_sample_cursor),
        "audio_provenance_schema": AUDIO_PROVENANCE_SCHEMA,
        "continuous_raw_audio": "lecture_raw.wav",
        "continuous_raw_start_sample": int(max(0, getattr(s, "continuous_raw_start_sample", 0))),
        "continuous_raw_samples": int(max(0, getattr(s, "continuous_raw_samples", 0))),
        "continuous_raw_end_sample": int(max(0, getattr(s, "continuous_raw_start_sample", 0)) + max(0, getattr(s, "continuous_raw_samples", 0))),
        "continuous_raw_time_sec": _samples_to_sec(getattr(s, "continuous_raw_samples", 0)),
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
    segment_stt_chunks=None,
    segment_stt_adapter=None,
    final_text=None,
    final_source=None,
    segment_stt_rejected=False,
    segment_stt_reject_reason="",
    processing_error="",
    denoise_meta=None,
    asr_audio_variant="clean",
    stt_audio_source_requested="raw",
    recording_start=None,
    recording_end=None,
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

    word_audio_map = []
    word_alignment_meta = {
        "version": "v7.9.3-immutable-word-map",
        "source": "unavailable",
        "coverage": 0.0,
        "audio_variant": asr_audio_variant,
        "immutable": True,
    }

    if segment_stt_raw and not segment_stt_rejected:
        try:
            word_audio_map, word_alignment_meta = _build_word_audio_map(
                segment_stt_raw,
                segment_stt_chunks or [],
                len(audio) / SR,
                audio_variant=asr_audio_variant,
            )
            print(
                "[WORD MAP]",
                f"segment={index}",
                f"mapped={len(word_audio_map)}",
                f"coverage={word_alignment_meta.get('coverage', 0):.3f}",
                f"audio={asr_audio_variant}",
                flush=True,
            )
        except Exception as exc:
            print(
                "[WORD MAP ERROR]",
                f"segment={index}",
                repr(exc),
                flush=True,
            )

    record = {
        "segment": index,
        "session_id": s.session_id,
        "title": s.title,
        # V7.4 keeps the original WAV immutable and stores the denoised
        # derivative separately. `audio` points to the preferred playback
        # variant for new consumers while explicit raw/clean fields preserve
        # auditability and backward compatibility.
        "audio": (
            f"segments_clean/{wav_name}"
            if (
                normalize_stt_audio_source(stt_audio_source_requested) == "clean"
                and (s.root / "segments_clean" / wav_name).exists()
            )
            else f"segments/{wav_name}"
        ),
        "audio_raw": f"segments/{wav_name}",
        "audio_clean": (
            f"segments_clean/{wav_name}"
            if (s.root / "segments_clean" / wav_name).exists()
            else None
        ),
        "denoise": denoise_meta or {"status": "not_run"},
        "asr_audio_variant": asr_audio_variant,
        "stt_audio_source_requested": normalize_stt_audio_source(stt_audio_source_requested),
        "duration_sec": round(
            len(audio) / SR,
            3,
        ),
        # V8.0-alpha immutable source timeline captured at the SEG boundary.
        "recording_start": (round(float(recording_start), 6) if recording_start is not None else None),
        "recording_end": (round(float(recording_end), 6) if recording_end is not None else None),
        "timeline_schema": TIMELINE_SCHEMA_VERSION,
        "qwen_raw": qwen_raw,
        "segment_stt_raw": segment_stt_raw,
        "segment_stt_chunks": segment_stt_chunks or [],
        # V7.9.3: immutable word/audio linkage captured at the same moment as
        # the committed BatiSay transcript. Human edits never overwrite this
        # map. LoRA phrase crops and playback highlighting both consume it.
        "word_audio_map": word_audio_map,
        "word_alignment_meta": word_alignment_meta,
        "segment_stt_adapter": segment_stt_adapter or {"name": "base", "version": "", "professor_id": ""},
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
    s.sentence_recording_start_sample = -1

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

    # Capture immutable source time before live state is reset.
    start_sample = int(s.sentence_recording_start_sample)
    if start_sample < 0:
        start_sample = max(0, int(s.recording_sample_cursor) - len(audio))
    end_sample = min(
        max(start_sample, start_sample + len(audio)),
        int(s.recording_sample_cursor),
    )
    recording_start = _samples_to_sec(start_sample)
    recording_end = _samples_to_sec(end_sample)

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

    segment_stt_source = normalize_stt_audio_source(
        getattr(s, "stt_audio_source", STT_AUDIO_SOURCE_DEFAULT),
        STT_AUDIO_SOURCE_DEFAULT,
    )
    segment_denoise_strength = denoise_profile(
        getattr(s, "denoise_strength", DENOISE_STRENGTH_DEFAULT)
    )["level"]

    pending = {
        "segment": index,
        "status": "queued",
        "stt_audio_source_requested": segment_stt_source,
        "denoise_strength": segment_denoise_strength,
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
        "recording_start": recording_start,
        "recording_end": recording_end,
        "timeline_schema": TIMELINE_SCHEMA_VERSION,
        "created_at": _now_iso(),
    }

    s.pending_segments[index] = pending

    s.sentence_queue.put({
        "segment": index,
        "audio": audio,
        "qwen_raw": qwen_raw,
        "boundary_reason": boundary_reason,
        "recording_start": recording_start,
        "recording_end": recording_end,
        "stt_audio_source": segment_stt_source,
        "denoise_strength": segment_denoise_strength,
    })

    print(
        "[SENTENCE QUEUED]",
        f"segment={index}",
        f"reason={boundary_reason}",
        f"duration={len(audio) / SR:.2f}s",
        f"recording={recording_start:.3f}-{recording_end:.3f}s",
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
        recording_start = job.get("recording_start")
        recording_end = job.get("recording_end")
        requested_audio_source = normalize_stt_audio_source(
            job.get("stt_audio_source"), STT_AUDIO_SOURCE_DEFAULT
        )
        segment_denoise_strength = denoise_profile(
            job.get("denoise_strength", DENOISE_STRENGTH_DEFAULT)
        )["level"]

        segment_stt_raw = ""
        segment_stt_chunks = []
        segment_stt_adapter = {"name": "base", "version": "", "professor_id": ""}
        segment_stt_rejected = False
        segment_stt_reason = ""
        processing_error = ""
        clean_audio = audio
        denoise_meta = {"status": "not_run", "backend": "none"}
        asr_audio_variant = "raw"

        try:
            # V7.4: denoise only the committed sentence path. Realtime Qwen
            # stays untouched so capture latency/state complexity do not grow.
            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending["status"] = "denoise"

            profile = denoise_profile(segment_denoise_strength)
            clean_audio, denoise_meta = enhance_segment(
                audio,
                sr=SR,
                binary=DENOISE_BIN,
                work_root=DENOISE_TMP_ROOT,
                enabled=(DENOISE_ENABLED and profile["enabled"]),
                timeout_sec=DENOISE_TIMEOUT_SEC,
                post_filter=profile["post_filter"],
                pf_beta=profile["pf_beta"],
                atten_lim_db=DENOISE_ATTEN_LIM_DB,
            )
            denoise_meta["ui_strength"] = profile["level"]
            denoise_meta["ui_profile"] = profile["name"]

            # Immutable-timeline rule: waveform enhancement must never alter
            # segment duration/sample count. The helper enforces this; assert
            # again here before persisting the derivative.
            if len(clean_audio) != len(audio):
                raise RuntimeError(
                    f"denoiser changed sample count {len(audio)} -> {len(clean_audio)}"
                )

            clean_dir = s.root / "segments_clean"
            clean_dir.mkdir(parents=True, exist_ok=True)
            save_wav(clean_dir / f"{index:06d}.wav", clean_audio)
            asr_audio_variant = "clean"

            print(
                "[DENOISE]",
                f"segment={index}",
                f"backend={denoise_meta.get('backend')}",
                f"status={denoise_meta.get('status')}",
                f"elapsed={denoise_meta.get('elapsed_sec', 0):.3f}s",
                f"profile={denoise_meta.get('profile', 'default')}",
                f"ui_strength={denoise_meta.get('ui_strength', getattr(s, 'denoise_strength', DENOISE_STRENGTH_DEFAULT))}",
                flush=True,
            )

            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending["status"] = "batisay"
                    pending["denoise"] = denoise_meta
                    pending["audio_variant"] = asr_audio_variant

            professor = professor_for_subject(s.subject_id)
            professor_id = str((professor or {}).get("id") or "")
            # V8.0-alpha.1 defaults to RAW for speech fidelity. CLEAN remains a
            # derivative and is used as the primary recognizer input only when
            # explicitly selected. A complete primary failure may retry once on
            # the opposite variant; partial word omissions are never guessed or
            # silently overwritten by a second transcript.
            primary_audio = audio if requested_audio_source == "raw" else clean_audio
            primary_variant = requested_audio_source
            fallback_audio = clean_audio if requested_audio_source == "raw" else audio
            fallback_variant = "clean" if requested_audio_source == "raw" else "raw"
            asr_audio_variant = primary_variant

            (
                segment_stt_raw,
                segment_stt_rejected,
                segment_stt_reason,
                segment_stt_chunks,
                segment_stt_adapter,
            ) = batisay_transcribe(primary_audio, professor_id=professor_id)

            if (
                (not segment_stt_raw or segment_stt_rejected)
                and fallback_variant != primary_variant
                and (fallback_variant == "raw" or (DENOISE_ENABLED and profile["enabled"]))
            ):
                alt_text, alt_rejected, alt_reason, alt_chunks, alt_adapter = batisay_transcribe(
                    fallback_audio, professor_id=professor_id
                )
                if alt_text and not alt_rejected:
                    segment_stt_raw = alt_text
                    segment_stt_chunks = alt_chunks
                    segment_stt_adapter = alt_adapter
                    segment_stt_rejected = False
                    segment_stt_reason = (
                        f"{fallback_variant}-fallback-after-{primary_variant}:"
                        + (segment_stt_reason or "primary-empty-or-rejected")
                    )
                    asr_audio_variant = fallback_variant
                    print(
                        "[BATISAY AUDIO FALLBACK RECOVERED]",
                        f"segment={index}",
                        f"primary={primary_variant}",
                        f"used={fallback_variant}",
                        flush=True,
                    )
                elif alt_reason:
                    segment_stt_reason = (
                        (segment_stt_reason + ";") if segment_stt_reason else ""
                    ) + f"{fallback_variant}=" + alt_reason

            with s.lock:
                pending = s.pending_segments.get(index)
                if pending is not None:
                    pending.update({
                        "status": "commit",
                        "segment_stt_raw": segment_stt_raw,
                        "segment_stt_chunks": segment_stt_chunks,
                        "segment_stt_adapter": segment_stt_adapter,
                        "segment_stt_rejected": segment_stt_rejected,
                        "segment_stt_reject_reason": segment_stt_reason,
                        "denoise": denoise_meta,
                        "audio_variant": asr_audio_variant,
                        "requested_audio_source": requested_audio_source,
                        "denoise_strength": segment_denoise_strength,
                    })

            if segment_stt_raw and not segment_stt_rejected:
                final_text = segment_stt_raw
                final_source = "batisay_lora" if segment_stt_adapter.get("version") else "batisay"
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
                    segment_stt_chunks=segment_stt_chunks,
                    segment_stt_adapter=segment_stt_adapter,
                    final_text=final_text,
                    final_source=final_source,
                    segment_stt_rejected=segment_stt_rejected,
                    segment_stt_reject_reason=segment_stt_reason,
                    processing_error=processing_error,
                    denoise_meta=denoise_meta,
                    asr_audio_variant=asr_audio_variant,
                    stt_audio_source_requested=requested_audio_source,
                    recording_start=recording_start,
                    recording_end=recording_end,
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
                f"audio={asr_audio_variant}",
                flush=True,
            )

        finally:
            s.sentence_queue.task_done()


# =========================================================
# API
# =========================================================

def api_start():

    if _training_busy():
        return jsonify({"error": "Professor LoRA 학습 중에는 새 녹음을 시작할 수 없습니다."}), 409

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

    recording_client_id = str(
        body.get("client_id") or ""
    ).strip()[:128]

    try:
        denoise_strength = max(0, min(3, int(body.get("denoise_strength", DENOISE_STRENGTH_DEFAULT))))
    except Exception:
        denoise_strength = DENOISE_STRENGTH_DEFAULT

    stt_audio_source = normalize_stt_audio_source(
        body.get("stt_audio_source"),
        STT_AUDIO_SOURCE_DEFAULT,
    )

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
    (root / "segments_clean").mkdir(
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

        "denoise_strength": denoise_strength,
        "stt_audio_source": stt_audio_source,
        "browser_audio_processing": {"echoCancellation": False, "noiseSuppression": True, "autoGainControl": True},
        "pdf_workspace_schema": PDF_WORKSPACE_SCHEMA,
        "pdf_ids": [],
        "pdf_view_state": {"active_pdf_id": "", "page": 1, "reading": False},
        "pdf_timeline_schema": PDF_TIMELINE_SCHEMA,
        "pdf_events_file": PDF_EVENTS_FILENAME,
        "pdf_timeline_default_state": "no_pdf",
        "pdf_semantic_timeline_schema": PDF_SEMANTIC_TIMELINE_SCHEMA,
        "pdf_semantic_timeline_file": PDF_SEMANTIC_TIMELINE_FILENAME,
        "pdf_semantic_timeline_dirty": True,
        "audio_provenance_schema": AUDIO_PROVENANCE_SCHEMA,
        "continuous_raw_audio": "lecture_raw.wav",
        "continuous_raw_start_sample": 0,
        "continuous_raw_samples": 0,

        "postprocess_status":
            "not_run",

        "timeline_schema": TIMELINE_SCHEMA_VERSION,
        "recording_time_basis": "accepted_capture_samples",
        "recording_time_exact": True,
        "recording_paused_wall_time_excluded": True,
        "recording_samples": 0,
        "recording_time_sec": 0.0,
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
        denoise_strength=denoise_strength,
        stt_audio_source=stt_audio_source,
        recording_client_id=recording_client_id,
        continuous_raw_start_sample=0,
        continuous_raw_samples=0,
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
        "denoise_strength": denoise_strength,
        "stt_audio_source": stt_audio_source,
        "postprocess_status":
            "not_run",
    })



def api_resume():

    if _training_busy():
        return jsonify({"error": "Professor LoRA 학습 중에는 녹음을 재개할 수 없습니다."}), 409

    sid = request.args.get(
        "session_id",
        "",
    )

    client_id = str(
        request.args.get("client_id")
        or ""
    ).strip()[:128]

    s = get_session_or_load(sid)

    if s is None:
        return jsonify({
            "error": "invalid session_id"
        }), 400

    reconnected = False
    takeover = False

    with s.lock:

        if s.postprocess_status == "running":
            return jsonify({
                "error": "wait until postprocessing finishes before resuming"
            }), 409

        # -------------------------------------------------
        # V6.4.3 reconnect / recorder lease
        # -------------------------------------------------
        if s.recording:
            now_mono = time.monotonic()
            age = (
                now_mono - s.last_chunk_monotonic
                if s.last_chunk_monotonic > 0
                else float("inf")
            )

            same_client = bool(
                client_id
                and s.recording_client_id
                and client_id == s.recording_client_id
            )

            stale = age >= RECORDING_LEASE_TIMEOUT_SEC

            if not same_client and not stale:
                return jsonify({
                    "error": (
                        "another recorder is still active; "
                        f"last audio chunk {age:.1f}s ago"
                    ),
                    "recording": True,
                    "retry_after_sec": max(
                        0.0,
                        RECORDING_LEASE_TIMEOUT_SEC - age,
                    ),
                }), 409

            # The old browser/capture path is gone. A gap between clients is a
            # natural boundary: preserve the partial audio before resetting
            # live Qwen/VAD state.
            if s.active and len(s.sentence_audio):
                enqueue_sentence(
                    s,
                    boundary_reason="client_reconnect",
                )

            reconnected = True
            takeover = not same_client

        else:
            # A deliberately stopped session is a normal resume. New audio
            # invalidates old whole-session AI outputs, while human edits and
            # manual tags survive.
            _invalidate_generated_session_outputs(
                s,
                reason="recording_resumed",
            )
            s.recording = True

        # A resumed/reconnected session continues the same segment timeline.
        # Recreate streaming model/VAD state when loaded from disk.
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
        s.sentence_recording_start_sample = -1
        s.qwen_parts = []
        s.adaptive_silence_active = False
        s.adaptive_silence_samples = 0
        s.qwen_samples = 0
        s.last_chunk_monotonic = 0.0

        if client_id:
            s.recording_client_id = client_id

        meta = _read_json_path(
            s.root / "session.json",
            {},
        )

        if reconnected:
            reconnect_count = int(
                meta.get("reconnect_count") or 0
            ) + 1
            update_session_metadata(
                s,
                reconnected_at=_now_iso(),
                reconnect_count=reconnect_count,
                recorder_takeover=bool(takeover),
                pending_count=len(s.pending_segments),
            )
        else:
            resume_count = int(
                meta.get("resume_count") or 0
            ) + 1
            update_session_metadata(
                s,
                resumed_at=_now_iso(),
                resume_count=resume_count,
                pending_count=len(s.pending_segments),
                postprocess_status="not_run",
                pdf_semantic_timeline_dirty=True,
            )

        # Reconcile PDF viewer changes made while recording was stopped.
        _sync_pdf_timeline_to_view_locked(s, reason="recording_resume")

    start_sentence_worker(s)

    print(
        "[SESSION RECONNECTED]" if reconnected else "[SESSION RESUMED]",
        sid,
        f"next_segment={s.segment_index + 1}",
        f"takeover={takeover}" if reconnected else "",
        flush=True,
    )

    payload = session_public_meta(s)
    payload["reconnected"] = reconnected
    payload["recorder_takeover"] = takeover
    return jsonify(payload)

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

    client_id = str(
        request.args.get("client_id")
        or ""
    ).strip()[:128]

    with s.lock:
        if not s.recording:
            return jsonify({
                "error": "session is stopped; resume it before sending audio"
            }), 409

        if (
            s.recording_client_id
            and client_id
            and client_id != s.recording_client_id
        ):
            return jsonify({
                "error": "recording is owned by another browser capture"
            }), 409

        if client_id and not s.recording_client_id:
            s.recording_client_id = client_id

        s.last_chunk_monotonic = time.monotonic()

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

        # Re-check after body decoding: api_finish() may have stopped the
        # session between the lease check above and this processing section.
        if not s.recording:
            return jsonify({
                "error": "session stopped before this audio chunk was committed"
            }), 409

        # V8.0-alpha.1: preserve every accepted capture sample BEFORE VAD.
        # If a new alpha.1 capture starts on a legacy session, record the exact
        # absolute source offset covered by lecture_raw.wav instead of pretending
        # the old audio is present in the new continuous file.
        chunk_start_sample = int(s.recording_sample_cursor)
        continuous_path = s.root / "lecture_raw.wav"
        if s.continuous_raw_samples <= 0 and not continuous_path.exists():
            s.continuous_raw_start_sample = chunk_start_sample
        appended = append_float32_mono_wav(continuous_path, wav, sample_rate=SR)
        if appended != len(wav):
            raise RuntimeError(
                f"continuous raw append mismatch {appended} != {len(wav)}"
            )
        s.continuous_raw_samples += appended

        # Master clock advances exactly once for each accepted capture chunk.
        # Silence is included because it exists in the source recording;
        # deliberate stopped wall-time is excluded because no chunks arrive.
        s.recording_sample_cursor += len(wav)

        # Crash-tolerant durable checkpoint without rewriting JSON per chunk.
        if (
            s.recording_sample_cursor - int(s.recording_checkpoint_sample)
            >= int(SR * 5.0)
        ):
            update_session_metadata(s)
            s.recording_checkpoint_sample = int(s.recording_sample_cursor)

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
                s.sentence_recording_start_sample = max(
                    0,
                    chunk_start_sample - len(s.preroll),
                )

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

            if s.sentence_recording_start_sample < 0:
                s.sentence_recording_start_sample = max(
                    0,
                    chunk_start_sample - len(s.sentence_audio),
                )

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

            "recording_time_sec":
                _samples_to_sec(s.recording_sample_cursor),
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

        try:
            semantic_pdf_timeline = _build_pdf_semantic_timeline_locked(s, write=True)
        except Exception as e:
            semantic_pdf_timeline = None
            print("[PDF SEMANTIC TIMELINE ERROR]", sid, repr(e), flush=True)

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

        "pdf_semantic_timeline":
            (semantic_pdf_timeline.get("summary") if isinstance(semantic_pdf_timeline, dict) else None),
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
                checkpoint_path=
                    s.root / "postprocess_checkpoint.json",
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
# V7.9.3 PROFESSOR LoRA TRAINING API
# =========================================================


def _training_busy():
    return bool(TRAINING_THREAD is not None and TRAINING_THREAD.is_alive())


def _recording_or_pending_exists():
    for session in SESSIONS.values():
        if session.recording or session.pending_segments:
            return True
    return False


def _professor_train_worker(professor_id):
    global TRAINING_THREAD
    global TRAINING_PROFESSOR_ID

    root = professor_root(professor_id)
    status_path = root / "training_status.json"
    log_path = root / "training.log"
    cmd = [
        "python3", str(LORA_TRAIN_SCRIPT),
        "--professor-id", professor_id,
        "--data-root", str(APP_DATA_ROOT),
        "--base-model", str(BATISAY_MODEL),
        "--status-file", str(status_path),
        "--epochs", str(LORA_TRAIN_EPOCHS),
        "--max-steps", str(LORA_TRAIN_MAX_STEPS),
        "--learning-rate", str(LORA_TRAIN_LR),
        "--min-samples", str(LORA_MIN_SAMPLES),
        "--min-new-samples", str(LORA_MIN_NEW_SAMPLES),
    ]
    try:
        root.mkdir(parents=True, exist_ok=True)
        recovery = recover_historical_phrase_samples(professor_id, status_path=status_path)
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n\n=== V7.9.3 training " + _now_iso() + " ===\n")
            log.write("historical_phrase_recovery=" + json.dumps(recovery, ensure_ascii=False) + "\n")
            log.flush()
            proc = subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        if proc.returncode != 0:
            status = _read_json_path(status_path, {})
            if status.get("status") != "error":
                status.update({
                    "status": "error",
                    "stage": "error",
                    "stage_label": "학습 실패",
                    "progress": 1.0,
                    "error": f"trainer exited with code {proc.returncode}",
                    "completed_at": _now_iso(),
                })
                _write_json_path(status_path, status)
        else:
            # The next BatiSay call observes profile.json and hot-switches to
            # the newly promoted adapter. No app restart is required.
            print("[LoRA TRAIN DONE]", professor_id, flush=True)
    except Exception as exc:
        _write_json_path(status_path, {
            "status": "error",
            "stage": "error",
            "stage_label": "학습 실패",
            "progress": 1.0,
            "message": "Professor LoRA trainer를 실행하지 못했습니다",
            "error": repr(exc),
            "completed_at": _now_iso(),
        })
        print("[LoRA TRAIN ERROR]", repr(exc), flush=True)
    finally:
        with TRAINING_LOCK:
            TRAINING_THREAD = None
            TRAINING_PROFESSOR_ID = ""


def api_professor_status():
    professor_id = str(request.args.get("professor_id") or "").strip()
    session_id = str(request.args.get("session_id") or "").strip()
    if not professor_id and session_id:
        s = get_session_or_load(session_id)
        if s is not None:
            professor_id = str(((subject_by_id(s.subject_id) or {}).get("professor_id") or ""))
    if not professor_id:
        return jsonify({
            "professor_id": "",
            "professor_name": "",
            "status": "no_professor",
            "training_status": {"status": "no_professor"},
            "sample_count": 0,
            "active_adapter": "",
            "peft_available": bool(PEFT_AVAILABLE),
        })
    summary = professor_adaptive_summary(professor_id)
    summary["training_busy"] = _training_busy()
    summary["training_professor_id"] = TRAINING_PROFESSOR_ID
    return jsonify(summary)


def api_professor_train():
    global TRAINING_THREAD
    global TRAINING_PROFESSOR_ID

    body = request.get_json(silent=True) or {}
    session_id = str(body.get("session_id") or request.args.get("session_id") or "").strip()
    professor_id = str(body.get("professor_id") or "").strip()
    if not professor_id and session_id:
        s = get_session_or_load(session_id)
        if s is None:
            return jsonify({"error": "invalid session_id"}), 400
        professor_id = str(((subject_by_id(s.subject_id) or {}).get("professor_id") or ""))

    professor = professor_by_id(professor_id)
    if professor is None:
        return jsonify({"error": "이 과목에 교수를 먼저 지정하세요."}), 400
    if not PEFT_AVAILABLE:
        return jsonify({"error": "PEFT runtime이 없습니다. V7.9.3 installer의 LoRA image build를 다시 실행하세요."}), 503
    if not LORA_TRAIN_SCRIPT.is_file():
        return jsonify({"error": "professor_lora_v7_9.py missing"}), 500
    if _recording_or_pending_exists():
        return jsonify({"error": "녹음/SEG 처리가 모두 끝난 뒤 LoRA를 학습하세요."}), 409

    # Safety/back-compat: V7.9.2 turns historical Human LOCK edits into training
    # data too, so users do not lose labels accumulated in V7.x.  This is
    # incremental: already-current source groups are skipped.
    backfill = backfill_professor_training_data(professor_id)
    summary = professor_adaptive_summary(professor_id)
    historical_recovery_candidates = historical_phrase_recovery_candidate_count(professor_id)
    if int(summary.get("correction_count") or 0) < LORA_MIN_SAMPLES:
        return jsonify({
            "error": f"Human-corrected SEG가 최소 {LORA_MIN_SAMPLES}개 필요합니다.",
            "adaptive_asr": summary,
        }), 409
    if (
        summary.get("active_adapter")
        and int(summary.get("new_correction_count") or 0) < LORA_MIN_NEW_SAMPLES
        and int(summary.get("new_sample_count") or 0) < LORA_MIN_NEW_SAMPLES
        and historical_recovery_candidates <= 0
    ):
        return jsonify({
            "error": (
                f"현재 Adapter 이후 새 Human-corrected SEG 또는 supervised sample이 "
                f"최소 {LORA_MIN_NEW_SAMPLES}개 필요합니다."
            ),
            "adaptive_asr": summary,
        }), 409

    with TRAINING_LOCK:
        if _training_busy():
            return jsonify({
                "error": "다른 Professor LoRA 학습이 이미 진행 중입니다.",
                "professor_id": TRAINING_PROFESSOR_ID,
            }), 409
        status_path = professor_root(professor_id) / "training_status.json"
        _write_json_path(status_path, {
            "status": "queued",
            "stage": "queued",
            "stage_label": "학습 대기",
            "progress": 0.0,
            "message": "Professor LoRA worker 시작을 기다리는 중",
            "queued_at": _now_iso(),
        })
        TRAINING_PROFESSOR_ID = professor_id
        TRAINING_THREAD = threading.Thread(
            target=_professor_train_worker,
            args=(professor_id,),
            daemon=True,
            name="clova-professor-lora-" + professor_id[-6:],
        )
        TRAINING_THREAD.start()

    return jsonify({
        "accepted": True,
        "professor_id": professor_id,
        "professor_name": professor.get("name"),
        "adaptive_asr": professor_adaptive_summary(professor_id),
        "backfill": backfill,
        "historical_phrase_recovery_candidates": historical_recovery_candidates,
    }), 202


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


# =========================================================
# V7.9.3 IMMUTABLE WORD ALIGNMENT + HUMAN CORRECTION DATA
# =========================================================

_TRAIN_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[-._'][A-Za-z0-9]+)*|[가-힣]+|[^\s]"
)

_WORD_UNIT_RE = re.compile(r"\S+")
_WORD_NORM_RE = re.compile(r"[A-Za-z0-9가-힣]+")


def _token_spans(text):
    text = str(text or "")
    return [
        {
            "text": m.group(0),
            "norm": m.group(0).casefold(),
            "start": m.start(),
            "end": m.end(),
        }
        for m in _TRAIN_TOKEN_RE.finditer(text)
    ]


def _word_norm(text):
    """Normalize a whitespace-delimited spoken unit for stable matching.

    Punctuation differences should not destroy audio linkage. If a token is
    punctuation-only, fall back to casefolded raw text so it can still be
    represented without pretending it is speech.
    """
    raw = str(text or "").strip().casefold()
    lexical = "".join(_WORD_NORM_RE.findall(raw))
    return lexical or raw


def _word_unit_spans(text):
    """Return exact whitespace-delimited units with character offsets."""
    text = str(text or "")
    result = []
    for idx, match in enumerate(_WORD_UNIT_RE.finditer(text)):
        token = match.group(0)
        result.append({
            "index": idx,
            "text": token,
            "norm": _word_norm(token),
            "start": match.start(),
            "end": match.end(),
        })
    return result


def _chunk_word_units(chunks):
    """Flatten BatiSay word chunks into whitespace units with timestamps."""
    result = []
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        ts = chunk.get("timestamp")
        if not isinstance(ts, (list, tuple)) or len(ts) != 2:
            continue
        try:
            start = 0.0 if ts[0] is None else float(ts[0])
            end = start if ts[1] is None else float(ts[1])
        except Exception:
            continue
        start = max(0.0, start)
        end = max(start, end)
        units = _word_unit_spans(chunk.get("text") or "")
        if not units:
            continue

        # BatiSay normally returns one lexical word per timestamp chunk. If a
        # chunk contains multiple whitespace units, divide that trusted chunk
        # span deterministically so every stored reference still points back
        # into the same immutable source audio interval.
        span = max(0.001, end - start)
        weights = [max(1, len(x["text"])) for x in units]
        total_weight = float(sum(weights))
        cursor = start
        for pos, (unit, weight) in enumerate(zip(units, weights)):
            if pos == len(units) - 1:
                unit_end = end
            else:
                unit_end = cursor + span * (weight / total_weight)
            result.append({
                "text": unit["text"],
                "norm": unit["norm"],
                "time": (cursor, max(cursor, unit_end)),
            })
            cursor = unit_end
            total_weight -= weight
            span = max(0.0, end - cursor)
    return result


def _build_word_audio_map(original_text, chunks, duration_sec, *, audio_variant="clean"):
    """Build the canonical V7.9.3 word -> source-audio map once at commit.

    The returned timestamps are relative to the SEG WAV. They are immutable;
    later Human LOCK edits are represented in a separate display timeline.
    """
    original = _word_unit_spans(original_text)
    timed = _chunk_word_units(chunks)
    mapping = {}

    if original and timed:
        matcher = difflib.SequenceMatcher(
            a=[x["norm"] for x in original],
            b=[x["norm"] for x in timed],
            autojunk=False,
        )
        for i1, j1, n in matcher.get_matching_blocks():
            for k in range(n):
                t0, t1 = timed[j1 + k]["time"]
                if duration_sec > 0:
                    t0 = min(float(duration_sec), max(0.0, t0))
                    t1 = min(float(duration_sec), max(t0, t1))
                mapping[i1 + k] = (t0, t1)

    word_map = []
    for unit in original:
        if unit["index"] not in mapping:
            continue
        t0, t1 = mapping[unit["index"]]
        word_map.append({
            "index": int(unit["index"]),
            "text": unit["text"],
            "norm": unit["norm"],
            "char_start": int(unit["start"]),
            "char_end": int(unit["end"]),
            "start_sec": round(float(t0), 3),
            "end_sec": round(float(t1), 3),
            "confidence": 1.0,
            "source": "batisay-word-timestamp",
        })

    coverage = len(word_map) / max(1, len(original))
    meta = {
        "version": "v7.9.3-immutable-word-map",
        "source": "batisay-return_timestamps-word",
        "coverage": round(float(coverage), 3),
        "word_count": len(original),
        "mapped_count": len(word_map),
        "audio_variant": str(audio_variant or "clean"),
        "source_text_sha1": hashlib.sha1(
            str(original_text or "").encode("utf-8")
        ).hexdigest(),
        "immutable": True,
        "created_at": _now_iso(),
    }
    return word_map, meta


def _validated_word_audio_map(word_map, original_text):
    """Accept only a monotonic map that still refers to the original ASR."""
    units = _word_unit_spans(original_text)
    by_index = {x["index"]: x for x in units}
    result = []
    previous_end = -1.0

    for item in word_map or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
            t0 = float(item.get("start_sec"))
            t1 = float(item.get("end_sec"))
        except Exception:
            continue
        unit = by_index.get(idx)
        if unit is None:
            continue
        if _word_norm(item.get("text") or "") != unit["norm"]:
            continue
        if t0 < 0 or t1 < t0 or t0 + 0.050 < previous_end:
            continue
        previous_end = max(previous_end, t1)
        result.append({
            "index": idx,
            "text": unit["text"],
            "norm": unit["norm"],
            "char_start": int(unit["start"]),
            "char_end": int(unit["end"]),
            "start_sec": round(t0, 3),
            "end_sec": round(t1, 3),
            "confidence": float(item.get("confidence") or 1.0),
            "source": str(item.get("source") or "persisted-word-map"),
        })
    return result


def _build_display_word_timeline(base_text, display_text, word_audio_map):
    """Project immutable BatiSay times onto the currently visible text.

    Equal words keep exact timestamps. Replacement words inherit only the
    source replacement span and are split *for UI highlighting only*; those
    approximated per-word splits are never used for LoRA phrase supervision.
    Pure insertions deliberately receive no timestamp.
    """
    base_units = _word_unit_spans(base_text)
    display_units = _word_unit_spans(display_text)
    source_map = {
        int(x["index"]): x
        for x in _validated_word_audio_map(word_audio_map, base_text)
    }
    if not base_units or not display_units or not source_map:
        return []

    matcher = difflib.SequenceMatcher(
        a=[x["norm"] for x in base_units],
        b=[x["norm"] for x in display_units],
        autojunk=False,
    )
    timeline = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                src = source_map.get(i1 + offset)
                dst = display_units[j1 + offset]
                if not src:
                    continue
                timeline.append({
                    "index": int(dst["index"]),
                    "text": dst["text"],
                    "char_start": int(dst["start"]),
                    "char_end": int(dst["end"]),
                    "start_sec": src["start_sec"],
                    "end_sec": src["end_sec"],
                    "approximate": False,
                    "source": "immutable-word-map",
                })
            continue

        if tag != "replace" or i1 == i2 or j1 == j2:
            # delete: no target text; insert: no trustworthy source audio.
            continue

        source_entries = [source_map.get(i) for i in range(i1, i2)]
        if not source_entries or any(x is None for x in source_entries):
            continue
        t0 = min(float(x["start_sec"]) for x in source_entries)
        t1 = max(float(x["end_sec"]) for x in source_entries)
        if t1 <= t0:
            continue
        targets = display_units[j1:j2]
        weights = [max(1, len(x["text"])) for x in targets]
        total = float(sum(weights))
        cursor = t0
        remaining_span = t1 - t0
        remaining_weight = total
        for pos, (dst, weight) in enumerate(zip(targets, weights)):
            if pos == len(targets) - 1:
                end = t1
            else:
                end = cursor + remaining_span * (weight / remaining_weight)
            timeline.append({
                "index": int(dst["index"]),
                "text": dst["text"],
                "char_start": int(dst["start"]),
                "char_end": int(dst["end"]),
                "start_sec": round(cursor, 3),
                "end_sec": round(max(cursor, end), 3),
                "approximate": True,
                "source": "human-replacement-ui-only",
            })
            remaining_weight -= weight
            cursor = end
            remaining_span = max(0.0, t1 - cursor)

    return sorted(timeline, key=lambda x: (x["char_start"], x["start_sec"]))


def _segment_record(s, segment):
    for pos, record in enumerate(load_transcript_records(s), start=1):
        try:
            idx = int(record.get("segment") or pos)
        except Exception:
            idx = pos
        if idx == segment:
            return record
    return {}


def _read_wav_float(path):
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if width != 2 or rate != SR:
        raise ValueError(f"unsupported training WAV format width={width} rate={rate}")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio


def _source_audio_for_training(s, segment):
    clean = s.root / "segments_clean" / f"{segment:06d}.wav"
    raw = s.root / "segments" / f"{segment:06d}.wav"
    return clean if clean.is_file() else raw


def _map_original_tokens_to_time(original_text, chunks, duration_sec):
    original = _token_spans(original_text)
    chunk_tokens = []
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        ts = chunk.get("timestamp")
        if not isinstance(ts, (list, tuple)) or len(ts) != 2:
            continue
        try:
            t0, t1 = float(ts[0]), float(ts[1])
        except Exception:
            continue
        parts = _token_spans(chunk.get("text") or "")
        if not parts:
            continue
        span = max(0.02, t1 - t0)
        for i, token in enumerate(parts):
            # If a Whisper chunk contains multiple lexical tokens, split its
            # timestamp proportionally. This still comes from DTW word timing
            # and is much tighter than segment-duration estimation.
            a = t0 + span * i / len(parts)
            b = t0 + span * (i + 1) / len(parts)
            chunk_tokens.append({"norm": token["norm"], "time": (a, b)})

    mapping = {}
    if original and chunk_tokens:
        a = [x["norm"] for x in original]
        b = [x["norm"] for x in chunk_tokens]
        matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for i1, j1, n in matcher.get_matching_blocks():
            for k in range(n):
                mapping[i1 + k] = chunk_tokens[j1 + k]["time"]

    # V7.8/older sessions have no word timestamps. Keep a conservative
    # proportional fallback so full-utterance data still works and phrase
    # samples can be marked lower-confidence instead of silently invented.
    fallback = False
    if not mapping and original and duration_sec > 0:
        fallback = True
        n = len(original)
        for i in range(n):
            mapping[i] = (
                duration_sec * i / n,
                duration_sec * (i + 1) / n,
            )
    return original, mapping, fallback


def _remove_training_samples_for_source(professor_id, session_id, segment):
    pool = professor_training_pool(professor_id)
    changed = False
    for sid, item in list(pool.items()):
        if not isinstance(item, dict):
            continue
        if (
            str(item.get("source_session") or "") == str(session_id)
            and int(item.get("source_segment") or 0) == int(segment)
        ):
            audio_path = Path(str(item.get("audio_path") or ""))
            try:
                if audio_path.is_file() and professor_root(professor_id) in audio_path.parents:
                    audio_path.unlink()
            except Exception:
                pass
            pool.pop(sid, None)
            changed = True
    if changed:
        save_professor_training_pool(professor_id, pool)
    return pool


def _store_training_sample(professor_id, pool, *, sample_id, audio, target, kind,
                           source_session, source_segment, subject_id, before,
                           clip_start, clip_end, confidence, alignment):
    root = professor_root(professor_id)
    audio_dir = root / "training_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{sample_id}.wav"
    save_wav(audio_path, audio)
    item = {
        "id": sample_id,
        "professor_id": professor_id,
        "subject_id": subject_id,
        "kind": kind,
        "audio_path": str(audio_path),
        "target": str(target).strip(),
        "asr_before": str(before or "").strip(),
        "source_session": source_session,
        "source_segment": int(source_segment),
        "clip_start_sec": round(float(clip_start), 3),
        "clip_end_sec": round(float(clip_end), 3),
        "duration_sec": round(len(audio) / SR, 3),
        "alignment_confidence": round(float(confidence), 3),
        "alignment": alignment,
        "created_at": _now_iso(),
        "disabled": False,
    }
    pool[sample_id] = item
    return item


def capture_training_samples_from_manual_edit(s, segment, human_text):
    """Create full-utterance + precise changed-phrase pairs automatically.

    V7.9.3 uses the immutable word_audio_map persisted at BatiSay commit time.
    There is no timestamp re-discovery for new sessions: replacement spans are
    cropped directly from already-linked source words. Pure insertions and
    ambiguous legacy data safely degrade to whole-utterance supervision only.
    """
    subject = subject_by_id(s.subject_id) or {}
    professor_id = str(subject.get("professor_id") or "")
    if not professor_id:
        return {"status": "no_professor", "created": 0}

    record = _segment_record(s, segment)
    batisay_before = str(record.get("segment_stt_raw") or "").strip()
    if record.get("segment_stt_rejected"):
        before = str(
            record.get("final_text")
            or record.get("qwen_raw")
            or batisay_before
            or (s.committed[segment - 1] if 0 < segment <= len(s.committed) else "")
            or ""
        ).strip()
    else:
        before = str(
            batisay_before
            or record.get("final_text")
            or (s.committed[segment - 1] if 0 < segment <= len(s.committed) else "")
            or ""
        ).strip()
    human_text = str(human_text or "").strip()

    # A later edit supersedes every older training pair from this SEG. Remove
    # stale pairs *before* any early return, including a user reverting the
    # text back to the original ASR output.
    pool = _remove_training_samples_for_source(
        professor_id,
        s.session_id,
        segment,
    )

    if not before or not human_text or before == human_text:
        return {"status": "unchanged", "created": 0}

    audio_path = _source_audio_for_training(s, segment)
    if not audio_path.is_file():
        return {"status": "no_audio", "created": 0}
    audio = _read_wav_float(audio_path)
    duration = len(audio) / SR
    if duration < 0.45 or duration > 30.5:
        return {"status": "duration_rejected", "created": 0}

    created = []

    # Full corrected SEG is always a valid supervised pair.  It carries the
    # natural co-articulation/context that tiny phrase-only datasets lack.
    utterance_key = hashlib.sha1(
        f"{s.session_id}:{segment}:utterance:{human_text}".encode("utf-8")
    ).hexdigest()[:20]
    utterance_id = "utt-" + utterance_key
    created.append(_store_training_sample(
        professor_id, pool,
        sample_id=utterance_id,
        audio=audio,
        target=human_text,
        kind="utterance",
        source_session=s.session_id,
        source_segment=segment,
        subject_id=s.subject_id,
        before=before,
        clip_start=0.0,
        clip_end=duration,
        confidence=1.0,
        alignment="whole-human-corrected-segment",
    ))

    original_tokens = _word_unit_spans(before)
    human_tokens = _word_unit_spans(human_text)

    word_map = []
    if not record.get("segment_stt_rejected") and before == batisay_before:
        word_map = _validated_word_audio_map(
            record.get("word_audio_map") or [],
            before,
        )
    alignment_name = "immutable-batisay-word-map-v7.9.3"

    # V7.9.0-7.9.2 already saved BatiSay word chunks but did not persist the
    # canonical map. Derive it once in memory from those existing timestamps;
    # no ASR rerun is required. Truly old V7.x sessions stay utterance-only
    # here and are handled by the separate historical recovery path.
    if (
        not word_map
        and not record.get("segment_stt_rejected")
        and before == batisay_before
        and record.get("segment_stt_chunks")
    ):
        derived_map, _ = _build_word_audio_map(
            before,
            record.get("segment_stt_chunks") or [],
            duration,
            audio_variant=str(record.get("asr_audio_variant") or "clean"),
        )
        word_map = _validated_word_audio_map(derived_map, before)
        alignment_name = "saved-batisay-chunks-derived-v7.9.3"

    map_by_index = {int(x["index"]): x for x in word_map}
    matcher = difflib.SequenceMatcher(
        a=[x["norm"] for x in original_tokens],
        b=[x["norm"] for x in human_tokens],
        autojunk=False,
    )

    phrase_number = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or j1 == j2:
            continue
        if (i2 - i1) > 10 or (j2 - j1) > 12:
            continue
        if i1 == i2:
            # Pure insertion has no source ASR word to attach to. Keep the
            # whole utterance pair; inventing a local crop would poison LoRA.
            continue
        target_start = human_tokens[j1]["start"]
        target_end = human_tokens[j2 - 1]["end"]
        target_phrase = human_text[target_start:target_end].strip()
        if len(target_phrase) < 2:
            continue

        mapped = [map_by_index.get(k) for k in range(i1, i2)]
        if not mapped or any(x is None for x in mapped):
            continue

        t0 = max(
            0.0,
            min(float(x["start_sec"]) for x in mapped) - LORA_PHRASE_MARGIN_SEC,
        )
        t1 = min(
            duration,
            max(float(x["end_sec"]) for x in mapped) + LORA_PHRASE_MARGIN_SEC,
        )
        if t1 - t0 < 0.35 or t1 - t0 > 9.0:
            continue

        confidence = min(
            0.99,
            min(float(x.get("confidence") or 1.0) for x in mapped),
        )
        if confidence < 0.65:
            continue

        a = int(round(t0 * SR))
        b = int(round(t1 * SR))
        clip = audio[a:b]
        phrase_number += 1
        key = hashlib.sha1(
            f"{s.session_id}:{segment}:phrase:{phrase_number}:{target_phrase}:{t0:.3f}:{t1:.3f}".encode("utf-8")
        ).hexdigest()[:20]
        created.append(_store_training_sample(
            professor_id, pool,
            sample_id="phr-" + key,
            audio=clip,
            target=target_phrase,
            kind="phrase",
            source_session=s.session_id,
            source_segment=segment,
            subject_id=s.subject_id,
            before=before,
            clip_start=t0,
            clip_end=t1,
            confidence=confidence,
            alignment=alignment_name,
        ))

    save_professor_training_pool(professor_id, pool)
    print(
        "[ADAPTIVE DATA]",
        f"professor={professor_id}",
        f"segment={segment}",
        f"samples={len(created)}",
        f"phrase={sum(1 for x in created if x.get('kind') == 'phrase')}",
        f"word_map={len(word_map)}",
        f"alignment={alignment_name}",
        flush=True,
    )
    return {
        "status": "captured",
        "created": len(created),
        "phrase_created": sum(1 for x in created if x.get("kind") == "phrase"),
        "professor_id": professor_id,
    }



def _source_has_phrase_sample(pool, session_id, segment):
    session_id = str(session_id or "")
    segment = int(segment or 0)
    for item in pool.values():
        if not isinstance(item, dict) or item.get("disabled"):
            continue
        if item.get("kind") != "phrase":
            continue
        if str(item.get("source_session") or "") != session_id:
            continue
        if int(item.get("source_segment") or 0) != segment:
            continue
        return True
    return False


def _extract_phrase_samples_with_timestamps(
    s,
    segment,
    human_text,
    *,
    before,
    audio,
    chunks,
    professor_id,
    pool,
    alignment_name,
    confidence_bonus=0.0,
    fresh_alignment_text="",
):
    """Create only phrase derivatives from trusted word timestamps.

    V7.9.2 uses this for historical V7.x Human edits after re-running the
    *base* BatiSay model solely to recover word timestamps. The canonical full
    utterance pair is left untouched.
    """
    duration = len(audio) / SR
    original_tokens, time_map, fallback = _map_original_tokens_to_time(
        before,
        chunks or [],
        duration,
    )
    if fallback or not time_map:
        return []

    human_tokens = _token_spans(human_text)
    matcher = difflib.SequenceMatcher(
        a=[x["norm"] for x in original_tokens],
        b=[x["norm"] for x in human_tokens],
        autojunk=False,
    )
    created = []
    phrase_number = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or j1 == j2:
            continue
        if (i2 - i1) > 10 or (j2 - j1) > 12:
            continue

        target_start = human_tokens[j1]["start"]
        target_end = human_tokens[j2 - 1]["end"]
        target_phrase = human_text[target_start:target_end].strip()
        if len(target_phrase) < 2:
            continue

        mapped = [time_map[k] for k in range(i1, i2) if k in time_map]
        if not mapped:
            # Pure insertion: only trust a crop when both neighbors are known.
            prev_t = time_map.get(i1 - 1)
            next_t = time_map.get(i2)
            if prev_t and next_t:
                mapped = [(prev_t[1], next_t[0])]
            else:
                continue

        local_coverage = len(mapped) / max(1, i2 - i1)
        if local_coverage < 0.60:
            continue
        t0 = max(0.0, min(x[0] for x in mapped) - LORA_PHRASE_MARGIN_SEC)
        t1 = min(duration, max(x[1] for x in mapped) + LORA_PHRASE_MARGIN_SEC)
        if t1 - t0 < 0.35 or t1 - t0 > 9.0:
            continue

        confidence = min(
            0.99,
            0.72 + 0.25 * min(1.0, local_coverage) + float(confidence_bonus),
        )
        if confidence < 0.65:
            continue

        a = int(round(t0 * SR))
        b = int(round(t1 * SR))
        clip = audio[a:b]
        phrase_number += 1
        key = hashlib.sha1(
            f"{s.session_id}:{segment}:phrase:{phrase_number}:{target_phrase}:{t0:.3f}:{t1:.3f}".encode("utf-8")
        ).hexdigest()[:20]
        item = _store_training_sample(
            professor_id,
            pool,
            sample_id="phr-" + key,
            audio=clip,
            target=target_phrase,
            kind="phrase",
            source_session=s.session_id,
            source_segment=segment,
            subject_id=s.subject_id,
            before=before,
            clip_start=t0,
            clip_end=t1,
            confidence=confidence,
            alignment=alignment_name,
        )
        if fresh_alignment_text:
            item["alignment_source_text"] = fresh_alignment_text
            item["alignment_recovered_at"] = _now_iso()
        created.append(item)
    return created


def _historical_phrase_candidates(professor_id):
    """Return historical Human edits that have utterance pairs but no phrase.

    This is intentionally a lightweight scan: it does not run ASR. It lets the
    API queue V7.9.2 recovery even when there are zero *new correction groups*
    after an already-promoted adapter.
    """
    professor_id = str(professor_id or "").strip()
    eligible_subjects = {
        str(x.get("id") or "")
        for x in load_subjects()
        if str(x.get("professor_id") or "") == professor_id
    }
    if not eligible_subjects:
        return []

    pool = professor_training_pool(professor_id)
    out = []
    for root in sorted(DATA_ROOT.iterdir()):
        if not root.is_dir():
            continue
        meta = _read_json_path(root / "session.json", {})
        if str(meta.get("subject_id") or "") not in eligible_subjects:
            continue
        edits_data = _read_json_path(root / "manual_edits.json", {"segments": {}})
        edits = edits_data.get("segments", {}) if isinstance(edits_data, dict) else {}
        if not isinstance(edits, dict):
            continue
        s = get_session_or_load(root.name)
        if s is None or str(s.subject_id or "") not in eligible_subjects:
            continue
        deleted = load_deleted_segments(s)
        for key, value in edits.items():
            if not str(key).isdigit():
                continue
            segment = int(key)
            if bool(deleted.get(str(segment))):
                continue
            human_text = str((value.get("text") or "") if isinstance(value, dict) else (value or "")).strip()
            if not human_text:
                continue
            if not _training_source_is_current(pool, s.session_id, segment, human_text, s.subject_id):
                continue
            if _source_has_phrase_sample(pool, s.session_id, segment):
                continue
            record = _segment_record(s, segment)
            # Native V7.9+ word timestamps mean a normal edit already had a
            # chance to create precise phrase samples. Recovery targets legacy
            # rows where those timestamps are absent.
            if record.get("segment_stt_chunks"):
                continue
            audio_path = _source_audio_for_training(s, segment)
            if not audio_path.is_file():
                continue
            out.append((s, segment, human_text))
    return out


def historical_phrase_recovery_candidate_count(professor_id):
    try:
        return len(_historical_phrase_candidates(professor_id))
    except Exception as exc:
        print("[HISTORICAL ALIGN CANDIDATE ERROR]", repr(exc), flush=True)
        return 0


def recover_historical_phrase_samples(professor_id, status_path=None):
    """Recover phrase crops for pre-V7.9 Human edits from preserved WAVs.

    The base BatiSay model is re-run only to obtain word timestamps. Existing
    Human text remains the target/source of truth and existing transcript JSON
    is never overwritten. Any active professor adapter is temporarily disabled
    during alignment, then restored before the function returns.
    """
    global BATISAY_ACTIVE_ADAPTER

    professor_id = str(professor_id or "").strip()
    candidates = _historical_phrase_candidates(professor_id)
    if not candidates:
        return {"status": "no_candidates", "candidates": 0, "recovered": 0, "phrases": 0, "skipped": 0}

    if status_path:
        _write_json_path(Path(status_path), {
            "status": "running",
            "stage": "historical_alignment",
            "stage_label": "과거 수정 음성 정렬",
            "progress": 0.03,
            "message": f"기존 Human edit {len(candidates)}개에서 phrase timestamp 복구 중",
            "started_at": _now_iso(),
        })

    pool = professor_training_pool(professor_id)
    recovered_groups = 0
    phrase_count = 0
    skipped = 0
    errors = []

    with BATISAY_MODEL_LOCK:
        previous = dict(BATISAY_ACTIVE_ADAPTER)
        _disable_batisay_adapters_locked()
        BATISAY_ACTIVE_ADAPTER = {
            "professor_id": "",
            "version": "",
            "name": "base-historical-alignment-v7.9.2",
        }
        try:
            for idx, (s, segment, human_text) in enumerate(candidates, start=1):
                try:
                    record = _segment_record(s, segment)
                    before = str(
                        record.get("segment_stt_raw")
                        or record.get("final_text")
                        or (s.committed[segment - 1] if 0 < segment <= len(s.committed) else "")
                        or ""
                    ).strip()
                    audio_path = _source_audio_for_training(s, segment)
                    audio = _read_wav_float(audio_path)
                    if not before or not human_text or len(audio) < int(0.45 * SR):
                        skipped += 1
                        continue

                    fresh_text, chunks = _batisay_once(audio, anti_loop=False)
                    bad, _ = detect_repetition_loop(fresh_text)
                    if bad or not chunks:
                        fresh_text, chunks = _batisay_once(audio, anti_loop=True)
                    if not fresh_text or not chunks:
                        skipped += 1
                        continue

                    before_tokens = [x["norm"] for x in _token_spans(before)]
                    fresh_tokens = [x["norm"] for x in _token_spans(fresh_text)]
                    if not before_tokens or not fresh_tokens:
                        skipped += 1
                        continue
                    ratio = difflib.SequenceMatcher(
                        a=before_tokens,
                        b=fresh_tokens,
                        autojunk=False,
                    ).ratio()
                    original_tokens, mapping, fallback = _map_original_tokens_to_time(
                        before,
                        chunks,
                        len(audio) / SR,
                    )
                    coverage = len(mapping) / max(1, len(original_tokens))
                    if (
                        fallback
                        or ratio < HISTORICAL_ALIGNMENT_MIN_RATIO
                        or coverage < HISTORICAL_ALIGNMENT_MIN_COVERAGE
                    ):
                        print(
                            "[HISTORICAL ALIGN SKIP]",
                            s.session_id,
                            segment,
                            f"ratio={ratio:.3f}",
                            f"coverage={coverage:.3f}",
                            flush=True,
                        )
                        skipped += 1
                        continue

                    created = _extract_phrase_samples_with_timestamps(
                        s,
                        segment,
                        human_text,
                        before=before,
                        audio=audio,
                        chunks=chunks,
                        professor_id=professor_id,
                        pool=pool,
                        alignment_name="historical-base-batisay-word-dtw-v7.9.2",
                        confidence_bonus=min(0.05, max(0.0, ratio - 0.60) * 0.10),
                        fresh_alignment_text=fresh_text,
                    )
                    if created:
                        recovered_groups += 1
                        phrase_count += len(created)
                        save_professor_training_pool(professor_id, pool)
                        print(
                            "[HISTORICAL ALIGN RECOVERED]",
                            s.session_id,
                            segment,
                            f"phrases={len(created)}",
                            f"ratio={ratio:.3f}",
                            f"coverage={coverage:.3f}",
                            flush=True,
                        )
                    else:
                        skipped += 1
                except Exception as exc:
                    errors.append({"session_id": s.session_id, "segment": segment, "error": repr(exc)})
                    print("[HISTORICAL ALIGN ERROR]", s.session_id, segment, repr(exc), flush=True)

                if status_path:
                    progress = 0.03 + 0.09 * idx / max(1, len(candidates))
                    _write_json_path(Path(status_path), {
                        "status": "running",
                        "stage": "historical_alignment",
                        "stage_label": "과거 수정 음성 정렬",
                        "progress": round(progress, 4),
                        "message": f"{idx}/{len(candidates)} 정렬 · phrase {phrase_count}개 복구",
                        "historical_candidates": len(candidates),
                        "historical_recovered_groups": recovered_groups,
                        "historical_phrase_count": phrase_count,
                    })
        finally:
            # Restore exactly the adapter family that was active before the
            # alignment pass. Force ensure_batisay_adapter() to execute instead
            # of returning early from its state cache.
            if previous.get("version") and previous.get("professor_id"):
                BATISAY_ACTIVE_ADAPTER = {
                    "professor_id": "__restore__",
                    "version": "__restore__",
                    "name": "restore-pending",
                }
                ensure_batisay_adapter(previous.get("professor_id"))
            else:
                _disable_batisay_adapters_locked()
                BATISAY_ACTIVE_ADAPTER = previous or {
                    "professor_id": "",
                    "version": "",
                    "name": "base",
                }

    return {
        "status": "ok" if not errors else "partial",
        "candidates": len(candidates),
        "recovered": recovered_groups,
        "phrases": phrase_count,
        "skipped": skipped,
        "errors": errors[:20],
    }

def _training_source_is_current(pool, session_id, segment, human_text, subject_id=""):
    """Return True when an active utterance pair already matches this edit.

    Phrase derivatives are intentionally ignored here: the full utterance is
    the canonical evidence that a Human LOCK correction has already been
    captured.  If it is missing/disabled/stale, capture regenerates the whole
    source group deterministically.
    """
    session_id = str(session_id or "")
    segment = int(segment or 0)
    human_text = str(human_text or "").strip()
    subject_id = str(subject_id or "")
    for item in pool.values():
        if not isinstance(item, dict) or item.get("disabled"):
            continue
        if item.get("kind") != "utterance":
            continue
        if str(item.get("source_session") or "") != session_id:
            continue
        if int(item.get("source_segment") or 0) != segment:
            continue
        if subject_id and str(item.get("subject_id") or "") != subject_id:
            continue
        if str(item.get("target") or "").strip() == human_text:
            return True
    return False


def set_training_samples_disabled_for_subject(professor_id, subject_id, disabled=True):
    """Disable samples from one old professor/subject relationship.

    This is used when the user corrects professor metadata for a subject.  The
    audio/text provenance is retained, but it must not train the wrong voice
    adapter after reassignment.
    """
    professor_id = str(professor_id or "")
    subject_id = str(subject_id or "")
    if not professor_id or not subject_id:
        return 0
    pool = professor_training_pool(professor_id)
    changed = 0
    for item in pool.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("subject_id") or "") != subject_id:
            continue
        new_value = bool(disabled)
        if bool(item.get("disabled")) == new_value:
            continue
        item["disabled"] = new_value
        item["disabled_at"] = _now_iso() if new_value else None
        changed += 1
    if changed:
        save_professor_training_pool(professor_id, pool)
    return changed


def backfill_professor_training_data(professor_id, subject_id=""):
    """Import pre-V7.9 Human LOCK edits into a professor Training Pool.

    Existing manual_edits.json files are the user's historical labels.  V7.9
    scans active (non-trash) sessions for subjects currently assigned to this
    professor and captures only missing/stale source groups.  Old sessions
    without BatiSay word timestamps still contribute the full corrected SEG;
    precise phrase crops are deliberately skipped when alignment is weak.
    """
    professor_id = str(professor_id or "").strip()
    subject_id = str(subject_id or "").strip()
    if not professor_id or professor_by_id(professor_id) is None:
        return {"status": "invalid_professor", "sessions": 0, "edits": 0, "captured": 0, "samples": 0}

    eligible_subjects = {
        str(x.get("id") or "")
        for x in load_subjects()
        if str(x.get("professor_id") or "") == professor_id
        and (not subject_id or str(x.get("id") or "") == subject_id)
    }
    if not eligible_subjects:
        return {"status": "no_subjects", "sessions": 0, "edits": 0, "captured": 0, "samples": 0}

    pool = professor_training_pool(professor_id)
    session_count = 0
    edit_count = 0
    captured_groups = 0
    sample_count = 0
    errors = []

    for root in sorted(DATA_ROOT.iterdir()):
        if not root.is_dir():
            continue
        meta = _read_json_path(root / "session.json", {})
        sid_subject = str(meta.get("subject_id") or "")
        if sid_subject not in eligible_subjects:
            continue
        edits_data = _read_json_path(root / "manual_edits.json", {"segments": {}})
        edits = edits_data.get("segments", {}) if isinstance(edits_data, dict) else {}
        if not isinstance(edits, dict) or not edits:
            continue

        s = get_session_or_load(root.name)
        if s is None:
            errors.append({"session_id": root.name, "error": "session_load_failed"})
            continue
        # Trust the hydrated session metadata if it differs from a stale file.
        if str(s.subject_id or "") not in eligible_subjects:
            continue
        deleted = load_deleted_segments(s)
        deleted_ids = {
            int(k) for k, v in deleted.items()
            if str(k).isdigit() and bool(v)
        }
        session_count += 1

        for key, value in sorted(edits.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 10**9):
            if not str(key).isdigit():
                continue
            segment = int(key)
            if segment < 1 or segment in deleted_ids:
                continue
            if isinstance(value, dict):
                human_text = str(value.get("text") or "").strip()
            else:
                # Defensive support for very old/manual JSON layouts.
                human_text = str(value or "").strip()
            if not human_text:
                continue
            edit_count += 1

            # Re-read the pool because capture writes it after each source.
            pool = professor_training_pool(professor_id)
            if _training_source_is_current(pool, s.session_id, segment, human_text, s.subject_id):
                continue
            try:
                result = capture_training_samples_from_manual_edit(s, segment, human_text)
                created = int(result.get("created") or 0)
                if created:
                    captured_groups += 1
                    sample_count += created
            except Exception as exc:
                errors.append({
                    "session_id": s.session_id,
                    "segment": segment,
                    "error": repr(exc),
                })
                print("[ADAPTIVE BACKFILL ERROR]", s.session_id, segment, repr(exc), flush=True)

    result = {
        "status": "ok" if not errors else "partial",
        "sessions": session_count,
        "edits": edit_count,
        "captured": captured_groups,
        "samples": sample_count,
        "errors": errors[:20],
    }
    print(
        "[ADAPTIVE BACKFILL]",
        f"professor={professor_id}",
        f"sessions={session_count}",
        f"edits={edit_count}",
        f"captured={captured_groups}",
        f"samples={sample_count}",
        f"errors={len(errors)}",
        flush=True,
    )
    return result


def set_training_samples_disabled_for_segment(s, segment, disabled=True):
    # Scan all professor pools so a later subject/professor reassignment does
    # not leave stale samples active under the previous professor profile.
    for prof in load_professors():
        professor_id = str(prof.get("id") or "")
        if not professor_id:
            continue
        pool = professor_training_pool(professor_id)
        changed = False
        for item in pool.values():
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("source_session") or "") == s.session_id
                and int(item.get("source_segment") or 0) == int(segment)
            ):
                item["disabled"] = bool(disabled)
                item["disabled_at"] = _now_iso() if disabled else None
                changed = True
        if changed:
            save_professor_training_pool(professor_id, pool)


def set_training_samples_disabled_for_session(session_id, disabled=True):
    """Disable provenance-linked samples when a whole session is trashed.

    Scan every professor pool because an old correction may have been created
    before the subject's professor field was later changed.
    """
    session_id = str(session_id or "")
    if not session_id:
        return 0
    changed_total = 0
    for prof in load_professors():
        professor_id = str(prof.get("id") or "")
        if not professor_id:
            continue
        pool = professor_training_pool(professor_id)
        changed = False
        for item in pool.values():
            if not isinstance(item, dict):
                continue
            if str(item.get("source_session") or "") != session_id:
                continue
            item["disabled"] = bool(disabled)
            item["disabled_at"] = _now_iso() if disabled else None
            changed = True
            changed_total += 1
        if changed:
            save_professor_training_pool(professor_id, pool)
    return changed_total


# =========================================================
# V7 SOFT-DELETED SEGMENTS
# =========================================================

def load_deleted_segments(s):
    data = _read_json_file(
        s.root / "deleted_segments.json",
        {"segments": {}},
    )
    segments = data.get("segments", {})
    return segments if isinstance(segments, dict) else {}


def save_deleted_segments(s, segments):
    _write_json_file(
        s.root / "deleted_segments.json",
        {"segments": segments},
    )


def _deleted_segments_from_root(root):
    data = _read_json_path(
        root / "deleted_segments.json",
        {"segments": {}},
    )
    segments = data.get("segments", {})
    return segments if isinstance(segments, dict) else {}


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
    include_deleted=False,
):

    manual = load_manual_edits(s)
    deleted_segments = load_deleted_segments(s)

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

        deleted_info = deleted_segments.get(key, {})
        deleted = bool(deleted_info)
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
        qwen_raw = sanitize_qwen_asr_text(
            qwen_raw,
            title=s.title,
            subject_id=s.subject_id,
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

        segment_stt_adapter = (
            pending.get("segment_stt_adapter")
            if pending
            else record.get("segment_stt_adapter")
        ) or {"name": "base", "version": "", "professor_id": ""}

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
        else:
            # Repair old persisted Qwen fallback/final text on read as well as
            # new live hypotheses. Human LOCKED text is never touched.
            text = sanitize_qwen_asr_text(
                text,
                title=s.title,
                subject_id=s.subject_id,
            ) or (
                segment_stt_raw
                if segment_stt_raw and not segment_stt_rejected
                else qwen_raw
            ) or text

        raw_audio_path = (
            s.root
            / "segments"
            / f"{i:06d}.wav"
        )
        clean_audio_path = (
            s.root
            / "segments_clean"
            / f"{i:06d}.wav"
        )
        audio_path = clean_audio_path if clean_audio_path.exists() else raw_audio_path

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

        raw_recording_start = (pending.get("recording_start") if pending else record.get("recording_start"))
        raw_recording_end = (pending.get("recording_end") if pending else record.get("recording_end"))

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

        recording_exact = bool(getattr(s, "recording_time_exact", False))
        try:
            recording_start = float(raw_recording_start)
            recording_end = float(raw_recording_end)
            if recording_end < recording_start:
                raise ValueError("recording_end before start")
        except Exception:
            # Legacy sessions lack discarded-silence timing; expose an
            # explicitly inexact fallback without rewriting old records.
            recording_start = start_sec
            recording_end = end_sec
            recording_exact = False

        word_audio_map = []
        word_alignment_meta = record.get("word_alignment_meta") or {}
        if segment_stt_raw and not segment_stt_rejected:
            word_audio_map = _validated_word_audio_map(
                record.get("word_audio_map") or [],
                segment_stt_raw,
            )

            # Seamless upgrade for V7.9.0-7.9.2 sessions: their saved
            # segment_stt_chunks already contain the timestamps, so playback
            # highlighting can work immediately without rerunning BatiSay.
            if not word_audio_map and record.get("segment_stt_chunks"):
                try:
                    word_audio_map, derived_meta = _build_word_audio_map(
                        segment_stt_raw,
                        record.get("segment_stt_chunks") or [],
                        duration,
                        audio_variant=str(record.get("asr_audio_variant") or "clean"),
                    )
                    word_audio_map = _validated_word_audio_map(
                        word_audio_map,
                        segment_stt_raw,
                    )
                    if word_audio_map:
                        word_alignment_meta = {
                            **derived_meta,
                            "version": "v7.9.3-derived-from-saved-chunks",
                            "immutable": False,
                        }
                except Exception:
                    word_audio_map = []

        word_timeline = (
            _build_display_word_timeline(
                segment_stt_raw,
                text,
                word_audio_map,
            )
            if segment_stt_raw and word_audio_map
            else []
        )

        item = {

            "segment": i,
            "text": text,
            "deleted": deleted,
            "deleted_at": (
                deleted_info.get("deleted_at")
                if isinstance(deleted_info, dict)
                else None
            ),

            "qwen_raw": qwen_raw,
            "segment_stt_raw": segment_stt_raw,
            "segment_stt_model": segment_stt_model,
            "segment_stt_adapter": segment_stt_adapter,
            "segment_stt_rejected": segment_stt_rejected,
            "segment_stt_reject_reason": segment_stt_reject_reason,
            "word_audio_map": word_audio_map,
            "word_timeline": word_timeline,
            "word_alignment_meta": word_alignment_meta,

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

            "recording_start":
                recording_start,

            "recording_end":
                recording_end,

            "recording_time_exact":
                recording_exact,

            "timeline_schema": (
                (pending.get("timeline_schema") if pending else record.get("timeline_schema"))
                or (TIMELINE_SCHEMA_VERSION if recording_exact else "legacy-fallback")
            ),

            "audio_available":
                audio_path.exists(),

            "audio_variant": (
                "clean" if clean_audio_path.exists() else "raw"
            ),

            "denoise": record.get("denoise"),

            "audio_url":
                (
                    "/api/segment/audio"
                    f"?session_id={s.session_id}"
                    f"&segment={i}"
                ),

            "audio_raw_url":
                (
                    "/api/segment/audio"
                    f"?session_id={s.session_id}"
                    f"&segment={i}&variant=raw"
                ),
        }

        if include_deleted or not deleted:
            result.append(item)

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

    try:
        recording_sample_cursor = int(meta.get("recording_samples"))
        if recording_sample_cursor < 0:
            raise ValueError("negative recording_samples")
        recording_cursor_source = str(meta.get("recording_time_basis") or "session.json")
        recording_time_exact = bool(meta.get("recording_time_exact")) if "recording_time_exact" in meta else str(meta.get("timeline_schema") or "").startswith("v8.0-alpha")
    except Exception:
        recording_sample_cursor, recording_cursor_source = _legacy_recording_cursor_from_records(records)
        recording_time_exact = False

    s = Session(
        session_id=session_id,
        title=title,
        root=root,
        qwen_state=None,
        vad=None,
        subject_id=subject_id,
        denoise_strength=denoise_profile(meta.get("denoise_strength", DENOISE_STRENGTH_DEFAULT))["level"],
        stt_audio_source=normalize_stt_audio_source(meta.get("stt_audio_source"), STT_AUDIO_SOURCE_DEFAULT),
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
        recording_sample_cursor=recording_sample_cursor,
        recording_time_exact=recording_time_exact,
        recording_time_basis=recording_cursor_source,
        recording_checkpoint_sample=recording_sample_cursor,
        continuous_raw_start_sample=int(meta.get("continuous_raw_start_sample") or 0),
        continuous_raw_samples=max(int(meta.get("continuous_raw_samples") or 0), wav_frame_count(root / "lecture_raw.wav")),
        sentence_recording_start_sample=-1,
    )

    if "timeline_schema" not in meta:
        meta["timeline_schema"] = "legacy-fallback"
        meta["recording_time_basis"] = recording_cursor_source
        meta["recording_time_exact"] = False
        meta["recording_samples"] = int(recording_sample_cursor)
        meta["recording_time_sec"] = _samples_to_sec(recording_sample_cursor)
        _write_json_path(root / "session.json", meta)

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

    deleted_segments = _deleted_segments_from_root(root)
    deleted_ids = {
        int(key)
        for key in deleted_segments.keys()
        if str(key).isdigit()
    }

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

    live_recording_time_sec = (
        _samples_to_sec(in_memory.recording_sample_cursor)
        if in_memory is not None
        else float(meta.get("recording_time_sec") or duration)
    )
    live_recording_time_exact = (
        bool(in_memory.recording_time_exact)
        if in_memory is not None
        else bool(meta.get("recording_time_exact", False))
    )
    live_recording_time_basis = (
        str(in_memory.recording_time_basis)
        if in_memory is not None
        else str(meta.get("recording_time_basis") or "legacy-cumulative-duration")
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
        "professor_id": str(((subject_by_id(str(meta.get("subject_id") or "")) or {}).get("professor_id") or "")),
        "professor_name": professor_name_for_subject(str(meta.get("subject_id") or "")),
        "created_at": meta.get("created_at"),
        "stopped_at": meta.get("stopped_at"),
        "recording": recording,
        "postprocess_status": postprocess_status,
        "tags": tags,
        "description": str(
            meta.get("description")
            or ""
        ),
        "denoise_strength": denoise_profile(meta.get("denoise_strength", DENOISE_STRENGTH_DEFAULT))["level"],
        "segment_count": max(
            0,
            (
                max(len(records), len(in_memory.committed))
                if in_memory is not None
                else len(records)
            ) - len(deleted_ids),
        ),
        "total_segment_count": (
            max(len(records), len(in_memory.committed))
            if in_memory is not None
            else len(records)
        ),
        "deleted_count": len(deleted_ids),
        "pending_count": pending_count,
        "manual_edit_count": len([
            key for key in edits.keys()
            if not (str(key).isdigit() and int(key) in deleted_ids)
        ]),
        "duration_sec": round(duration, 3),
        "recording_time_sec": round(float(live_recording_time_sec), 3),
        "recording_time_exact": live_recording_time_exact,
        "recording_time_basis": live_recording_time_basis,
        "timeline_schema": str(meta.get("timeline_schema") or "legacy-fallback"),
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
        "professor_id": str(((subject_by_id(s.subject_id) or {}).get("professor_id") or "")),
        "professor_name": professor_name_for_subject(s.subject_id),
        "adaptive_asr": professor_adaptive_summary(str(((subject_by_id(s.subject_id) or {}).get("professor_id") or ""))),
        "recording": s.recording,
        "postprocess_status":
            s.postprocess_status,
        "postprocess_progress":
            _postprocess_progress_public(s),
        "pending_count":
            len(s.pending_segments),
        "segment_count": int(summary.get("segment_count") or 0),
        "total_segment_count": int(
            summary.get("total_segment_count")
            or len(s.committed)
        ),
        "deleted_count": int(summary.get("deleted_count") or 0),
        "recording_time_sec": float(summary.get("recording_time_sec") or 0.0),
        "recording_time_exact": bool(summary.get("recording_time_exact", False)),
        "recording_time_basis": str(summary.get("recording_time_basis") or "legacy-cumulative-duration"),
        "timeline_schema": str(summary.get("timeline_schema") or "legacy-fallback"),
        "tags": normalize_tag_entries(
            meta.get("tags", [])
        ),
        "description": str(
            meta.get("description")
            or ""
        ),
        "denoise_strength": denoise_profile(meta.get("denoise_strength", getattr(s, "denoise_strength", DENOISE_STRENGTH_DEFAULT)))["level"],
        "stt_audio_source": normalize_stt_audio_source(meta.get("stt_audio_source", getattr(s, "stt_audio_source", STT_AUDIO_SOURCE_DEFAULT)), STT_AUDIO_SOURCE_DEFAULT),
        "audio_provenance_schema": str(meta.get("audio_provenance_schema") or "legacy-segment-only"),
        "continuous_raw_audio": str(meta.get("continuous_raw_audio") or ""),
        "continuous_raw_start_sample": int(meta.get("continuous_raw_start_sample") or 0),
        "continuous_raw_samples": int(meta.get("continuous_raw_samples") or 0),
        "capture_settings": meta.get("capture_settings") if isinstance(meta.get("capture_settings"), dict) else {},
        "pdf_workspace_schema": str(meta.get("pdf_workspace_schema") or PDF_WORKSPACE_SCHEMA),
        "pdf_ids": [str(x) for x in (meta.get("pdf_ids") or []) if isinstance(x, str)],
        "pdf_view_state": meta.get("pdf_view_state") if isinstance(meta.get("pdf_view_state"), dict) else {"active_pdf_id": "", "page": 1, "reading": False},
    })

    return summary


def api_library():

    subjects = load_subjects()
    professors = load_professors()
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
        "professors": professors,
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

    professor_id = str(body.get("professor_id") or "").strip()
    professor_name = str(body.get("professor_name") or "").strip()
    professor = ensure_professor(professor_name, professor_id) if (professor_name or professor_id) else None

    if not name:
        return jsonify({
            "error": "subject name is required"
        }), 400

    existing_result = None
    old_professor_id = ""
    professor_changed = False
    with SUBJECTS_LOCK:

        subjects = load_subjects()

        for existing in subjects:
            if (
                str(existing.get("name") or "").casefold()
                == name.casefold()
                and str(existing.get("semester") or "").casefold()
                == semester.casefold()
            ):
                old_professor_id = str(existing.get("professor_id") or "")
                if professor and old_professor_id != professor.get("id"):
                    existing["professor_id"] = professor.get("id")
                    existing["updated_at"] = _now_iso()
                    save_subjects(subjects)
                    professor_changed = True
                existing_result = dict(existing)
                break

        if existing_result is None:
            subject = {
                "id": "subject-" + uuid.uuid4().hex[:10],
                "name": name,
                "semester": semester,
                "emoji": emoji or "📘",
                "professor_id": (professor or {}).get("id", ""),
                "created_at": _now_iso(),
            }

            subjects.append(subject)
            save_subjects(subjects)
        else:
            subject = existing_result

    # A duplicate-create can double as metadata correction in the UI. Preserve
    # ASR provenance just like the dedicated professor-assignment endpoint.
    if existing_result is not None and professor_changed:
        new_professor_id = str((professor or {}).get("id") or "")
        if old_professor_id and old_professor_id != new_professor_id:
            set_training_samples_disabled_for_subject(old_professor_id, subject["id"], True)
        if new_professor_id:
            backfill_professor_training_data(new_professor_id, subject["id"])

    return jsonify(subject), (200 if existing_result is not None else 201)


def api_subject_professor():

    body = request.get_json(silent=True) or {}
    subject_id = str(body.get("subject_id") or "").strip()
    professor_id = str(body.get("professor_id") or "").strip()
    professor_name = str(body.get("professor_name") or "").strip()

    if not subject_id:
        return jsonify({"error": "subject_id is required"}), 400

    professor = None
    old_professor_id = ""
    target = None
    with SUBJECTS_LOCK:
        subjects = load_subjects()
        target = next((x for x in subjects if x.get("id") == subject_id), None)
        if target is None:
            return jsonify({"error": "invalid subject_id"}), 404

        old_professor_id = str(target.get("professor_id") or "")
        if not professor_id and not professor_name:
            target["professor_id"] = ""
            target["updated_at"] = _now_iso()
            save_subjects(subjects)
        else:
            professor = ensure_professor(professor_name, professor_id)
            if professor is None:
                return jsonify({"error": "invalid professor"}), 400
            target["professor_id"] = professor["id"]
            target["updated_at"] = _now_iso()
            save_subjects(subjects)

    # Do provenance migration outside SUBJECTS_LOCK. capture/backfill calls
    # subject_by_id(), which reads the same store and must never be nested under
    # the subject mutation lock.
    new_professor_id = str((professor or {}).get("id") or "")
    disabled_old = 0
    if old_professor_id and old_professor_id != new_professor_id:
        disabled_old = set_training_samples_disabled_for_subject(
            old_professor_id, subject_id, True
        )

    backfill = None
    if new_professor_id:
        backfill = backfill_professor_training_data(new_professor_id, subject_id)

    return jsonify({
        "subject": target,
        "professor": professor,
        "adaptive_backfill": backfill,
        "disabled_old_training_samples": disabled_old,
    })


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

        if "denoise_strength" in body:
            try:
                denoise_strength = max(0, min(3, int(body.get("denoise_strength"))))
            except Exception:
                return jsonify({"error": "denoise_strength must be 0..3"}), 400
            s.denoise_strength = denoise_strength
            data["denoise_strength"] = denoise_strength

        if "stt_audio_source" in body:
            requested_source = str(body.get("stt_audio_source") or "").strip().lower()
            if requested_source not in {"raw", "clean"}:
                return jsonify({"error": "stt_audio_source must be raw or clean"}), 400
            s.stt_audio_source = requested_source
            data["stt_audio_source"] = requested_source

        if "capture_settings" in body:
            incoming = body.get("capture_settings")
            if isinstance(incoming, dict):
                allowed = {
                    "sampleRate", "channelCount", "echoCancellation",
                    "noiseSuppression", "autoGainControl", "deviceId",
                    "browser_requested_raw",
                }
                data["capture_settings"] = {
                    k: incoming.get(k) for k in allowed if k in incoming
                }

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

def _whole_session_review_segments_sparse_single(
    title,
    segments,
    subject_name="",
    progress_callback=None,
):
    """Return only necessary corrections for one context-safe chunk."""

    if not segments:
        return "", "segment-stt-pass", {}

    blocks = []
    segment_by_id = {}
    for seg in segments:
        idx = int(seg["segment"])
        segment_by_id[idx] = seg
        state = "LOCKED" if seg["locked"] else "AUTO"
        blocks.append(
            f"<<<SEGMENT {idx} {state}>>>\n"
            f"{seg['text']}\n"
            f"<<<END {idx}>>>"
        )

    marked_transcript = "\n\n".join(blocks)

    system_prompt = """
You are performing a conservative FINAL ASR correction pass over one chunk of a Korean university lecture.

The input contains numbered AUTO and LOCKED segments.

CRITICAL:
- LOCKED segments were manually corrected by the user. NEVER change or return them.
- For AUTO segments, output a correction ONLY when there is a clear ASR error.
- If an AUTO segment is already acceptable, OMIT it completely.
- Do not summarize, paraphrase, add facts, remove spoken information, or rewrite style.
- Use surrounding segments only to resolve ASR mistakes, technical terms, Korean/English mixed terms, punctuation, proper nouns, and mathematical notation.

OUTPUT FORMAT — sparse corrections only:
<<<CORRECTION 123>>>
corrected text for segment 123
<<<END 123>>>

Return zero or more correction blocks in segment order.
If nothing needs correction, return exactly:
NO_CHANGES

No commentary. No markdown. Never reproduce unchanged segments.
""".strip()

    user_prompt = f"""
SESSION TITLE:
{title}

COURSE / SUBJECT:
{subject_name if subject_name else "(not assigned)"}

TRANSCRIPT CHUNK:
{marked_transcript}

Return only necessary sparse corrections.
""".strip()

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 1536,
        "stream": bool(progress_callback),
    }

    print("[WHOLE REVIEW / SPARSE-DIFF]", flush=True)

    stream_response = bool(progress_callback)
    r = requests.post(
        f"{LLM_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=(15, POSTPROCESS_LLM_READ_TIMEOUT_SEC),
        stream=stream_response,
    )

    if not r.ok:
        body = (r.text or "").strip()
        raise RuntimeError(
            f"whole-session LLM HTTP {r.status_code}: "
            + (body[:1200] if body else "empty error body")
        )

    if not stream_response:
        output = r.json()["choices"][0]["message"]["content"].strip()
    else:
        output_parts = []
        generated_chars = 0
        expected_sparse_chars = max(200, min(1600, len(marked_transcript) // 5))

        for raw_line in r.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="replace").strip()
            else:
                line = str(raw_line).strip()

            data = line[5:].strip() if line.startswith("data:") else line
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
            progress_callback(generated_chars, expected_sparse_chars)

        output = "".join(output_parts).strip()

        if not output:
            print("[WHOLE REVIEW STREAM FALLBACK] retrying non-stream", flush=True)
            fallback_payload = dict(payload)
            fallback_payload["stream"] = False
            fallback_response = requests.post(
                f"{LLM_BASE_URL}/v1/chat/completions",
                json=fallback_payload,
                timeout=(15, POSTPROCESS_LLM_READ_TIMEOUT_SEC),
            )
            if not fallback_response.ok:
                body = (fallback_response.text or "").strip()
                raise RuntimeError(
                    f"whole-session fallback HTTP {fallback_response.status_code}: "
                    + (body[:1200] if body else "empty error body")
                )
            output = fallback_response.json()["choices"][0]["message"]["content"].strip()

    final_map = {
        str(int(seg["segment"])): str(seg["text"])
        for seg in segments
    }

    if output and output.strip() != "NO_CHANGES":
        correction_re = re.compile(
            r"<<<CORRECTION\s+(\d+)>>>\s*(.*?)\s*<<<END\s+\1>>>",
            flags=re.S,
        )
        for match in correction_re.finditer(output):
            idx = int(match.group(1))
            corrected = match.group(2).strip()
            seg = segment_by_id.get(idx)
            if seg is None:
                print(f"[SPARSE CORRECTION IGNORE] unknown segment={idx}", flush=True)
                continue
            if seg.get("locked"):
                print(f"[SPARSE CORRECTION IGNORE] LOCKED segment={idx}", flush=True)
                continue

            original = str(seg.get("text") or "")
            if not corrected:
                continue
            ratio = len(corrected) / max(1, len(original))
            if ratio < 0.45 or ratio > 1.80:
                print(
                    f"[SPARSE CORRECTION REJECT] segment={idx} ratio={ratio:.2f}",
                    flush=True,
                )
                continue
            final_map[str(idx)] = corrected

    final_text = "\n".join(
        final_map[str(int(seg["segment"]))]
        for seg in segments
    )
    return final_text, "whole-session-llm-sparse", final_map


def _postprocess_segment_cost(seg):
    return len(str(seg.get("text") or "")) + 96


def _build_postprocess_chunks(segments):
    chunks = []
    current = []
    current_chars = 0

    for seg in segments:
        cost = _postprocess_segment_cost(seg)
        if (
            current
            and (
                current_chars + cost > POSTPROCESS_CHUNK_CHAR_BUDGET
                or len(current) >= POSTPROCESS_CHUNK_MAX_SEGMENTS
            )
        ):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(seg)
        current_chars += cost

    if current:
        chunks.append(current)
    return chunks


def _postprocess_input_signature(title, subject_name, segments):
    h = hashlib.sha256()
    h.update(str(title).encode("utf-8", errors="replace"))
    h.update(b"\0")
    h.update(str(subject_name).encode("utf-8", errors="replace"))
    for seg in segments:
        h.update(b"\0")
        h.update(str(seg.get("segment")).encode())
        h.update(b"\0")
        h.update(b"1" if seg.get("locked") else b"0")
        h.update(b"\0")
        h.update(str(seg.get("text") or "").encode("utf-8", errors="replace"))
    return h.hexdigest()


def whole_session_review_segments(
    title,
    segments,
    subject_name="",
    progress_callback=None,
    checkpoint_path=None,
):
    """Sparse, chunked, resumable review for arbitrarily long lectures."""

    if not segments:
        return "", "segment-stt-pass", {}

    chunks = _build_postprocess_chunks(segments)
    position = {int(seg["segment"]): i for i, seg in enumerate(segments)}
    total_target_chars = max(
        1,
        sum(_postprocess_segment_cost(seg) for seg in segments),
    )
    input_signature = _postprocess_input_signature(title, subject_name, segments)

    final_map = {}
    completed_ids = set()
    checkpoint = Path(checkpoint_path) if checkpoint_path else None

    if checkpoint and checkpoint.exists():
        data = _read_json_path(checkpoint, {})
        if data.get("input_signature") == input_signature:
            final_map = {
                str(k): str(v)
                for k, v in (data.get("final_map") or {}).items()
            }
            completed_ids = {
                int(x)
                for x in (data.get("completed_ids") or [])
                if str(x).isdigit()
            }
            print(
                f"[POSTPROCESS RESUME] checkpoint contains {len(completed_ids)} segments",
                flush=True,
            )
        else:
            try:
                checkpoint.unlink()
            except FileNotFoundError:
                pass

    completed_target_chars = sum(
        _postprocess_segment_cost(seg)
        for seg in segments
        if int(seg["segment"]) in completed_ids
    )

    print(
        f"[WHOLE REVIEW CHUNKED/SPARSE] {len(segments)} segments -> {len(chunks)} chunks "
        f"(budget={POSTPROCESS_CHUNK_CHAR_BUDGET}, timeout={POSTPROCESS_LLM_READ_TIMEOUT_SEC}s)",
        flush=True,
    )

    def save_checkpoint():
        if checkpoint:
            _write_json_path(
                checkpoint,
                {
                    "version": "6.4.3",
                    "input_signature": input_signature,
                    "completed_ids": sorted(completed_ids),
                    "final_map": final_map,
                    "updated_at": _now_iso(),
                },
            )

    def request_segments_for(piece):
        first_pos = position[int(piece[0]["segment"])]
        last_pos = position[int(piece[-1]["segment"])]
        context_start = max(0, first_pos - POSTPROCESS_CONTEXT_SEGMENTS)
        context_end = min(
            len(segments),
            last_pos + 1 + POSTPROCESS_CONTEXT_SEGMENTS,
        )
        target_ids = {int(seg["segment"]) for seg in piece}
        request_segments = []
        for seg in segments[context_start:context_end]:
            copy = dict(seg)
            if int(copy["segment"]) not in target_ids:
                copy["locked"] = True
            request_segments.append(copy)
        return request_segments

    def is_retryable(exc):
        if isinstance(exc, (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError)):
            return True
        text = str(exc).lower()
        return any(token in text for token in (
            "timed out", "timeout", "http 400", "http 413",
            "http 429", "http 500", "http 503",
        ))

    def review_piece(piece, label, depth=0):
        nonlocal completed_target_chars
        piece = [seg for seg in piece if int(seg["segment"]) not in completed_ids]
        if not piece:
            return

        piece_expected = max(
            1,
            sum(_postprocess_segment_cost(seg) for seg in piece),
        )
        print(
            f"[WHOLE REVIEW {label}] SEG {piece[0]['segment']}..{piece[-1]['segment']} depth={depth}",
            flush=True,
        )

        def piece_progress(generated_chars, expected_chars):
            if not progress_callback:
                return
            local_ratio = min(
                0.75,
                max(0.0, float(generated_chars) / max(1.0, float(expected_chars))),
            )
            estimated_done = completed_target_chars + int(piece_expected * local_ratio)
            progress_callback(
                min(total_target_chars, estimated_done),
                total_target_chars,
            )

        try:
            _text, _source, piece_map = _whole_session_review_segments_sparse_single(
                title=title,
                segments=request_segments_for(piece),
                subject_name=subject_name,
                progress_callback=piece_progress if progress_callback else None,
            )
        except Exception as exc:
            if is_retryable(exc) and len(piece) > POSTPROCESS_MIN_SPLIT_SEGMENTS:
                mid = len(piece) // 2
                left = piece[:mid]
                right = piece[mid:]
                print(
                    f"[WHOLE REVIEW AUTO-SPLIT] {type(exc).__name__}: "
                    f"SEG {piece[0]['segment']}..{piece[-1]['segment']} -> "
                    f"{len(left)} + {len(right)}",
                    flush=True,
                )
                review_piece(left, label + "A", depth + 1)
                review_piece(right, label + "B", depth + 1)
                return
            raise

        for seg in piece:
            key = str(int(seg["segment"]))
            final_map[key] = piece_map.get(key, str(seg["text"]))
            completed_ids.add(int(seg["segment"]))

        completed_target_chars += piece_expected
        save_checkpoint()
        if progress_callback:
            progress_callback(
                min(total_target_chars, completed_target_chars),
                total_target_chars,
            )

    for chunk_index, chunk in enumerate(chunks, start=1):
        review_piece(chunk, f"CHUNK {chunk_index}/{len(chunks)}")

    for seg in segments:
        key = str(int(seg["segment"]))
        final_map.setdefault(key, str(seg["text"]))

    final_text = "\n".join(
        final_map[str(int(seg["segment"]))]
        for seg in segments
    )

    if checkpoint:
        try:
            checkpoint.unlink()
        except FileNotFoundError:
            pass

    return final_text, "whole-session-llm-sparse-chunked", final_map



# =========================================================
# V8.1-alpha.1 PDF annotation + V8.0 workspace / playback auto-sync frontend support
# =========================================================

def _safe_pdf_id(value):
    value = str(value or "").strip()
    return value if PDF_ID_RE.fullmatch(value) else ""


def _pdf_root(pdf_id):
    pdf_id = _safe_pdf_id(pdf_id)
    if not pdf_id:
        return None
    return PDF_LIBRARY_ROOT / pdf_id


def _detect_pdf_page_count(path):
    path = Path(path)
    try:
        from pypdf import PdfReader
        return max(0, len(PdfReader(str(path)).pages))
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["pdfinfo", str(path)],
            capture_output=True, text=True, check=False, timeout=12,
        )
        if result.returncode == 0:
            match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
            if match:
                return max(0, int(match.group(1)))
    except Exception:
        pass
    return 0


def _pdf_meta(pdf_id):
    root = _pdf_root(pdf_id)
    if root is None:
        return None
    meta = _read_json_path(root / "meta.json", {})
    source = root / "source.pdf"
    if not isinstance(meta, dict) or not source.is_file():
        return None
    page_count = int(meta.get("page_count") or 0)
    if page_count <= 0:
        detected = _detect_pdf_page_count(source)
        if detected > 0:
            page_count = detected
            meta["page_count"] = detected
            _write_json_path(root / "meta.json", meta)
    return {
        "pdf_id": pdf_id,
        "relative_path": f"pdfs/{pdf_id}/source.pdf",
        "original_filename": str(meta.get("original_filename") or "document.pdf"),
        "aliases": [str(x) for x in (meta.get("aliases") or []) if isinstance(x, str)],
        "sha256": str(meta.get("sha256") or ""),
        "size_bytes": int(meta.get("size_bytes") or source.stat().st_size),
        "created_at": str(meta.get("created_at") or ""),
        "page_count": page_count,
    }


def _session_pdf_ids(meta):
    result = []
    seen = set()
    for raw in meta.get("pdf_ids") or []:
        pdf_id = _safe_pdf_id(raw)
        if not pdf_id or pdf_id in seen or _pdf_meta(pdf_id) is None:
            continue
        seen.add(pdf_id)
        result.append(pdf_id)
    return result


def _annotation_events_path(s):
    return s.root / ANNOTATION_EVENTS_FILENAME


def _safe_annotation_id(value):
    value = str(value or "").strip()
    if re.fullmatch(r"ann_[0-9a-f]{16,64}", value):
        return value
    return ""


def _read_annotation_events(s):
    path = _annotation_events_path(s)
    events = []
    if not path.is_file():
        return events
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if isinstance(item, dict) and item.get("type") in {"annotation_add", "annotation_erase"}:
                events.append(item)
    except Exception:
        return []
    return events


def _annotation_state_from_events(events):
    strokes = {}
    order = []
    erased = set()
    for item in events:
        kind = str(item.get("type") or "")
        if kind == "annotation_add":
            annotation_id = _safe_annotation_id(item.get("annotation_id"))
            if not annotation_id:
                continue
            strokes[annotation_id] = item
            if annotation_id not in order:
                order.append(annotation_id)
            erased.discard(annotation_id)
        elif kind == "annotation_erase":
            target = _safe_annotation_id(item.get("target_annotation_id"))
            if target:
                erased.add(target)
    active = []
    all_strokes = []
    for annotation_id in order:
        item = dict(strokes.get(annotation_id) or {})
        if not item:
            continue
        item["erased"] = annotation_id in erased
        all_strokes.append(item)
        if annotation_id not in erased:
            active.append(item)
    return {"active": active, "all": all_strokes, "erased_ids": sorted(erased)}


def _append_annotation_event_locked(s, event):
    events = _read_annotation_events(s)
    seq = 1
    for item in events:
        try:
            seq = max(seq, int(item.get("seq") or 0) + 1)
        except Exception:
            pass
    payload = dict(event)
    payload["seq"] = seq
    payload["event_id"] = str(payload.get("event_id") or f"evt_{uuid.uuid4().hex}")
    payload["annotation_schema"] = ANNOTATION_SCHEMA
    payload["recorded_at"] = _now_iso()
    path = _annotation_events_path(s)
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    try:
        if path.is_file() and path.stat().st_size > 0:
            with path.open("rb") as check:
                check.seek(-1, os.SEEK_END)
                needs_newline = check.read(1) != b"\n"
    except Exception:
        needs_newline = False
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    meta = _read_json_path(s.root / "session.json", {})
    meta["annotation_schema"] = ANNOTATION_SCHEMA
    meta["annotation_events_file"] = ANNOTATION_EVENTS_FILENAME
    meta["annotation_event_count"] = seq
    _write_json_path(s.root / "session.json", meta)
    return payload


def _annotation_time_context_locked(s, body):
    """Resolve an annotation's temporal anchor without inventing time 0.

    Priority:
      1) recorder-owner while recording -> live_recording + exact recording cursor
      2) explicit valid playback cursor -> playback + recording_time
      3) otherwise -> page_only + lecture_time=None

    page_only is intentional: browsing/drawing a PDF with neither recording nor
    playback active has no defensible lecture-time anchor.
    """
    client_id = str(body.get("client_id") or "").strip()[:128]
    owns_recording = bool(
        s.recording
        and client_id
        and (not s.recording_client_id or client_id == s.recording_client_id)
    )
    if owns_recording:
        current_sample = int(max(0, getattr(s, "recording_sample_cursor", 0)))
        try:
            requested_sample = int(body.get("anchor_recording_sample"))
        except Exception:
            requested_sample = current_sample
        sample = max(0, min(current_sample, requested_sample))
        return {
            "anchor_type": "live_recording",
            "lecture_time": round(_samples_to_sec(sample), 6),
            "recording_sample": sample,
            "created_during": "live",
            "lecture_time_source": "recording_cursor",
            "recording_time_exact": bool(getattr(s, "recording_time_exact", False)),
            "recording_time_basis": str(getattr(s, "recording_time_basis", "accepted_capture_samples")),
        }

    # New V8.1-alpha.1 payload names are accepted alongside alpha legacy names
    # so already-created alpha sessions remain editable.
    raw_time = body.get("lecture_time")
    if raw_time is None:
        raw_time = body.get("operation_lecture_time")
    anchor_type = str(body.get("anchor_type") or body.get("operation_anchor_type") or "").strip()
    source = str(body.get("lecture_time_source") or body.get("operation_lecture_time_source") or "").strip()

    lecture_time = None
    try:
        if raw_time is not None and str(raw_time).strip() != "":
            value = float(raw_time)
            if math.isfinite(value):
                lecture_time = max(0.0, value)
    except Exception:
        lecture_time = None

    if lecture_time is not None and anchor_type in {"playback", ""}:
        end = _recording_end_sec(s)
        if end > 0:
            lecture_time = min(lecture_time, end)
        return {
            "anchor_type": "playback",
            "lecture_time": round(lecture_time, 6),
            "recording_sample": None,
            "created_during": "review",
            "lecture_time_source": "playback_cursor" if source != "recording_cursor" else source,
            "recording_time_exact": bool(getattr(s, "recording_time_exact", False)),
            "recording_time_basis": str(getattr(s, "recording_time_basis", "accepted_capture_samples")),
        }

    return {
        "anchor_type": "page_only",
        "lecture_time": None,
        "recording_sample": None,
        "created_during": "page_only",
        "lecture_time_source": None,
        "recording_time_exact": None,
        "recording_time_basis": None,
    }


def _validated_annotation_points(raw_points):
    if not isinstance(raw_points, list):
        return []
    result = []
    for item in raw_points[:5000]:
        if not isinstance(item, dict):
            continue
        try:
            x = min(1.0, max(0.0, float(item.get("x"))))
            y = min(1.0, max(0.0, float(item.get("y"))))
        except Exception:
            continue
        result.append({"x": round(x, 6), "y": round(y, 6)})
    return result


def _pdf_events_path(s):
    return s.root / PDF_EVENTS_FILENAME


def _read_pdf_events(s):
    path = _pdf_events_path(s)
    events = []
    if not path.is_file():
        return events
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if isinstance(item, dict) and item.get("type") in {"pdf_open", "pdf_page", "pdf_close"}:
                events.append(item)
    except Exception:
        return []
    return events


def _pdf_state_from_events(events):
    state = {"state": "no_pdf", "pdf_id": "", "page": 1, "seq": 0, "time": 0.0}
    for item in events:
        try:
            seq = int(item.get("seq") or 0)
        except Exception:
            seq = state["seq"] + 1
        kind = str(item.get("type") or "")
        try:
            event_time = float(item.get("time") or state["time"])
        except Exception:
            event_time = float(state["time"])
        if kind == "pdf_close":
            state = {"state": "no_pdf", "pdf_id": "", "page": 1, "seq": seq, "time": event_time}
        elif kind in {"pdf_open", "pdf_page"}:
            pdf_id = _safe_pdf_id(item.get("pdf_id"))
            if not pdf_id:
                continue
            try:
                page = max(1, int(item.get("page") or 1))
            except Exception:
                page = 1
            state = {"state": "pdf", "pdf_id": pdf_id, "page": page, "seq": seq, "time": event_time}
    return state


def _classify_pdf_dwell(dwell_sec):
    dwell = max(0.0, float(dwell_sec or 0.0))
    if dwell < PDF_DWELL_IGNORE_LT:
        return "ignore"
    if dwell < PDF_DWELL_WEAK_LT:
        return "weak"
    if dwell < PDF_DWELL_INCLUDE_LT:
        return "include"
    return "strong"


def _recording_end_sec(s, meta=None):
    meta = meta if isinstance(meta, dict) else _read_json_path(s.root / "session.json", {})
    values = []
    try:
        values.append(_samples_to_sec(int(max(0, getattr(s, "recording_sample_cursor", 0)))))
    except Exception:
        pass
    try:
        values.append(float(meta.get("recording_time_sec") or 0.0))
    except Exception:
        pass
    return max(values or [0.0])


def _build_pdf_semantic_timeline_locked(s, *, write=True):
    """Derive dwell metadata from immutable pdf_events.jsonl. Caller must hold s.lock."""
    meta = _read_json_path(s.root / "session.json", {})
    raw_events = _read_pdf_events(s)
    events = []
    for pos, item in enumerate(raw_events):
        try:
            t = max(0.0, float(item.get("time") or 0.0))
        except Exception:
            t = 0.0
        try:
            seq = int(item.get("seq") or (pos + 1))
        except Exception:
            seq = pos + 1
        events.append((t, seq, pos, item))
    events.sort(key=lambda x: (x[0], x[1], x[2]))

    recording_end = _recording_end_sec(s, meta)
    if events:
        recording_end = max(recording_end, events[-1][0])

    entries = []
    for idx, (t, seq, _pos, item) in enumerate(events):
        kind = str(item.get("type") or "")
        if kind not in {"pdf_open", "pdf_page"}:
            continue
        pdf_id = _safe_pdf_id(item.get("pdf_id"))
        if not pdf_id:
            continue
        try:
            page = max(1, int(item.get("page") or 1))
        except Exception:
            page = 1
        end = recording_end
        if idx + 1 < len(events):
            end = max(t, float(events[idx + 1][0]))
        dwell = max(0.0, end - t)
        weight = _classify_pdf_dwell(dwell)
        entries.append({
            "pdf_id": pdf_id,
            "page": page,
            "ref": f"clova://pdf/{pdf_id}/page/{page}",
            "start": round(t, 6),
            "end": round(end, 6),
            "dwell": round(dwell, 6),
            "semantic_weight": weight,
            "source_seq": seq,
        })

    counts = {"ignore": 0, "weak": 0, "include": 0, "strong": 0}
    for entry in entries:
        counts[entry["semantic_weight"]] += 1

    payload = {
        "schema": PDF_SEMANTIC_TIMELINE_SCHEMA,
        "generated_at": _now_iso(),
        "source": {
            "pdf_timeline_schema": PDF_TIMELINE_SCHEMA,
            "pdf_events_file": PDF_EVENTS_FILENAME,
            "event_count": len(raw_events),
            "llm_used": False,
        },
        "recording_time_sec": round(recording_end, 6),
        "recording_time_exact": bool(meta.get("recording_time_exact", getattr(s, "recording_time_exact", False))),
        "recording_time_basis": str(meta.get("recording_time_basis") or getattr(s, "recording_time_basis", "accepted_capture_samples")),
        "thresholds_sec": {
            "ignore_lt": PDF_DWELL_IGNORE_LT,
            "weak_range": [PDF_DWELL_IGNORE_LT, PDF_DWELL_WEAK_LT],
            "include_range": [PDF_DWELL_WEAK_LT, PDF_DWELL_INCLUDE_LT],
            "strong_gte": PDF_DWELL_INCLUDE_LT,
        },
        "classification_rule": "[0,1.5)=ignore; [1.5,4)=weak; [4,10)=include; [10,+inf)=strong",
        "entries": entries,
        "summary": {
            "entry_count": len(entries),
            "counts": counts,
            "semantic_entry_count": counts["weak"] + counts["include"] + counts["strong"],
            "included_or_strong_count": counts["include"] + counts["strong"],
        },
    }
    if write:
        _write_json_path(s.root / PDF_SEMANTIC_TIMELINE_FILENAME, payload)
        meta["pdf_semantic_timeline_schema"] = PDF_SEMANTIC_TIMELINE_SCHEMA
        meta["pdf_semantic_timeline_file"] = PDF_SEMANTIC_TIMELINE_FILENAME
        meta["pdf_semantic_timeline_dirty"] = False
        meta["pdf_semantic_timeline_summary"] = payload["summary"]
        _write_json_path(s.root / "session.json", meta)
    return payload


def _pdf_view_state_from_meta(meta):
    view = meta.get("pdf_view_state") if isinstance(meta.get("pdf_view_state"), dict) else {}
    pdf_id = _safe_pdf_id(view.get("active_pdf_id"))
    reading = bool(view.get("reading", False)) and bool(pdf_id)
    try:
        page = max(1, int(view.get("page") or 1))
    except Exception:
        page = 1
    return {"state": "pdf" if reading else "no_pdf", "pdf_id": pdf_id if reading else "", "page": page}


def _append_pdf_event_locked(s, kind, *, pdf_id="", page=1, reason="viewer_change"):
    """Append one durable lecture-PDF event. Caller must hold s.lock."""
    events = _read_pdf_events(s)
    prior = _pdf_state_from_events(events)
    seq = int(prior.get("seq") or 0) + 1
    sample = int(max(0, getattr(s, "recording_sample_cursor", 0)))
    t = _samples_to_sec(sample)
    pdf_id = _safe_pdf_id(pdf_id)
    try:
        page = max(1, int(page or 1))
    except Exception:
        page = 1

    event = {
        "seq": seq,
        "time": round(float(t), 6),
        "recording_sample": sample,
        "type": str(kind),
        "source": ("recording_resume_snapshot" if str(reason) == "recording_resume" else "manual_recording_event"),
        "reason": str(reason or "viewer_change"),
        "recorded_at": _now_iso(),
        "timeline_schema": TIMELINE_SCHEMA_VERSION,
        "pdf_timeline_schema": PDF_TIMELINE_SCHEMA,
        "recording_time_exact": bool(getattr(s, "recording_time_exact", False)),
        "recording_time_basis": str(getattr(s, "recording_time_basis", "accepted_capture_samples")),
    }
    if kind in {"pdf_open", "pdf_page"} and pdf_id:
        event.update({"pdf_id": pdf_id, "page": page, "ref": f"clova://pdf/{pdf_id}/page/{page}"})
    elif kind == "pdf_close":
        closed_id = _safe_pdf_id(prior.get("pdf_id")) or pdf_id
        closed_page = max(1, int(prior.get("page") or page or 1))
        if closed_id:
            event.update({"pdf_id": closed_id, "page": closed_page, "ref": f"clova://pdf/{closed_id}/page/{closed_page}"})

    path = _pdf_events_path(s)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    # If a power loss left a truncated final JSONL record, do not concatenate
    # the next valid event onto that damaged line. Start a fresh record.
    needs_newline = False
    try:
        if path.is_file() and path.stat().st_size > 0:
            with path.open("rb") as check:
                check.seek(-1, os.SEEK_END)
                needs_newline = check.read(1) != b"\n"
    except Exception:
        needs_newline = False
    with path.open("a", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    meta = _read_json_path(s.root / "session.json", {})
    meta["pdf_timeline_schema"] = PDF_TIMELINE_SCHEMA
    meta["pdf_events_file"] = PDF_EVENTS_FILENAME
    meta["pdf_semantic_timeline_schema"] = PDF_SEMANTIC_TIMELINE_SCHEMA
    meta["pdf_semantic_timeline_file"] = PDF_SEMANTIC_TIMELINE_FILENAME
    meta["pdf_semantic_timeline_dirty"] = True
    meta["pdf_timeline_last_event"] = {
        "seq": seq,
        "time": round(float(t), 6),
        "type": str(kind),
        "pdf_id": str(event.get("pdf_id") or ""),
        "page": int(event.get("page") or 1),
    }
    _write_json_path(s.root / "session.json", meta)
    print("[PDF TIMELINE]", s.session_id, f"seq={seq}", f"t={t:.3f}", kind, event.get("pdf_id", ""), event.get("page", ""), flush=True)
    return event


def _sync_pdf_timeline_to_view_locked(s, *, reason="viewer_change"):
    """Transition lecture PDF state to current viewer state, if needed."""
    meta = _read_json_path(s.root / "session.json", {})
    target = _pdf_view_state_from_meta(meta)
    prior = _pdf_state_from_events(_read_pdf_events(s))

    if target["state"] == "no_pdf":
        if prior["state"] == "pdf":
            return _append_pdf_event_locked(s, "pdf_close", reason=reason)
        return None

    pdf_id = target["pdf_id"]
    page = target["page"]
    if prior["state"] == "no_pdf" or prior.get("pdf_id") != pdf_id:
        return _append_pdf_event_locked(s, "pdf_open", pdf_id=pdf_id, page=page, reason=reason)
    if int(prior.get("page") or 1) != int(page):
        return _append_pdf_event_locked(s, "pdf_page", pdf_id=pdf_id, page=page, reason=reason)
    return None


def _pdf_public_for_session(s):
    meta = _read_json_path(s.root / "session.json", {})
    ids = _session_pdf_ids(meta)
    pdfs = []
    for pdf_id in ids:
        item = _pdf_meta(pdf_id)
        if item:
            pdfs.append(item)
    view = meta.get("pdf_view_state") if isinstance(meta.get("pdf_view_state"), dict) else {}
    active = _safe_pdf_id(view.get("active_pdf_id"))
    if active not in ids:
        active = ids[-1] if ids else ""
    try:
        page = max(1, int(view.get("page") or 1))
    except Exception:
        page = 1
    reading = bool(view.get("reading", False)) and bool(active)
    return {
        "schema": str(meta.get("pdf_workspace_schema") or PDF_WORKSPACE_SCHEMA),
        "pdfs": pdfs,
        "active_pdf_id": active,
        "page": page,
        "reading": reading,
        "canonical_ref": f"clova://pdf/{active}/page/{page}" if active else "",
        "pdf_timeline_schema": PDF_TIMELINE_SCHEMA,
        "lecture_pdf_state": _pdf_state_from_events(_read_pdf_events(s)),
    }


def api_pdfs():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    with s.lock:
        return jsonify(_pdf_public_for_session(s))


def api_pdf_import():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400

    uploads = request.files.getlist("pdfs")
    if not uploads:
        single = request.files.get("pdf")
        uploads = [single] if single else []
    uploads = [x for x in uploads if x is not None and str(x.filename or "").strip()]
    if not uploads:
        return jsonify({"error": "PDF file is required"}), 400
    if len(uploads) > 20:
        return jsonify({"error": "한 번에 최대 20개 PDF까지 추가할 수 있습니다."}), 400

    imported = []
    temp_paths = []
    try:
        for upload in uploads:
            original = Path(str(upload.filename or "document.pdf")).name.strip() or "document.pdf"
            tmp = PDF_LIBRARY_ROOT / f".import-{uuid.uuid4().hex}.tmp"
            temp_paths.append(tmp)
            digest = hashlib.sha256()
            total = 0
            first = b""
            with tmp.open("wb") as out:
                while True:
                    chunk = upload.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    if not first:
                        first = bytes(chunk[:8])
                    total += len(chunk)
                    if total > PDF_MAX_BYTES:
                        raise ValueError(f"{original}: PDF_MAX_MB 제한을 초과했습니다.")
                    digest.update(chunk)
                    out.write(chunk)
            if total < 5 or not first.startswith(b"%PDF-"):
                raise ValueError(f"{original}: PDF 파일이 아닙니다.")

            sha = digest.hexdigest()
            pdf_id = f"pdf_{sha[:16]}"
            root = PDF_LIBRARY_ROOT / pdf_id
            source = root / "source.pdf"
            meta_path = root / "meta.json"

            if root.exists() and source.is_file():
                tmp.unlink(missing_ok=True)
                old = _read_json_path(meta_path, {})
                aliases = [str(x) for x in (old.get("aliases") or []) if isinstance(x, str)]
                prior_name = str(old.get("original_filename") or "")
                for name in (prior_name, original):
                    if name and name not in aliases:
                        aliases.append(name)
                old.update({
                    "pdf_id": pdf_id,
                    "relative_path": f"pdfs/{pdf_id}/source.pdf",
                    "sha256": sha,
                    "size_bytes": int(source.stat().st_size),
                    "aliases": aliases,
                })
                if not old.get("original_filename"):
                    old["original_filename"] = original
                _write_json_path(meta_path, old)
            else:
                root.mkdir(parents=True, exist_ok=True)
                os.replace(tmp, source)
                _write_json_path(meta_path, {
                    "pdf_id": pdf_id,
                    "relative_path": f"pdfs/{pdf_id}/source.pdf",
                    "original_filename": original,
                    "aliases": [original],
                    "sha256": sha,
                    "size_bytes": total,
                    "created_at": _now_iso(),
                    "page_count": _detect_pdf_page_count(source),
                })
            imported.append(pdf_id)

        with s.lock:
            meta = _read_json_path(s.root / "session.json", {})
            prior_view = meta.get("pdf_view_state") if isinstance(meta.get("pdf_view_state"), dict) else {}
            ids = _session_pdf_ids(meta)
            for pdf_id in imported:
                if pdf_id not in ids:
                    ids.append(pdf_id)
            prior_active = _safe_pdf_id(prior_view.get("active_pdf_id"))
            active = prior_active if prior_active in ids else (imported[-1] if imported else (ids[-1] if ids else ""))
            try:
                prior_page = max(1, int(prior_view.get("page") or 1))
            except Exception:
                prior_page = 1
            reading = bool(prior_view.get("reading", False)) and bool(active)
            meta["pdf_workspace_schema"] = PDF_WORKSPACE_SCHEMA
            meta["pdf_ids"] = ids
            meta["pdf_view_state"] = {
                "active_pdf_id": active,
                "page": prior_page if active == prior_active else 1,
                "reading": reading,
                "updated_at": _now_iso(),
                "source": "viewer_state_plus_recording_timeline_when_owner",
            }
            _write_json_path(s.root / "session.json", meta)
            result = _pdf_public_for_session(s)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("[PDF IMPORT ERROR]", repr(e), flush=True)
        return jsonify({"error": "PDF import failed"}), 500
    finally:
        for tmp in temp_paths:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass


def api_pdf_file():
    from flask import send_file
    pdf_id = _safe_pdf_id(request.args.get("pdf_id", ""))
    meta = _pdf_meta(pdf_id)
    root = _pdf_root(pdf_id)
    if meta is None or root is None:
        return jsonify({"error": "invalid pdf_id"}), 404
    return send_file(
        root / "source.pdf",
        mimetype="application/pdf",
        as_attachment=False,
        download_name=meta.get("original_filename") or "document.pdf",
        conditional=True,
        max_age=3600,
    )


def api_pdf_page():
    pdf_id = _safe_pdf_id(request.args.get("pdf_id", ""))
    meta = _pdf_meta(pdf_id)
    root = _pdf_root(pdf_id)
    if meta is None or root is None:
        return jsonify({"error": "invalid pdf_id"}), 404
    try:
        page = max(1, int(request.args.get("page") or 1))
    except Exception:
        page = 1
    total = int(meta.get("page_count") or 0)
    if total > 0 and page > total:
        return jsonify({"error": "page out of range"}), 404
    renderer = shutil.which("pdftoppm")
    if not renderer:
        return jsonify({"error": "pdftoppm is unavailable in the Local Clova runtime"}), 500
    try:
        result = subprocess.run(
            [renderer, "-f", str(page), "-l", str(page), "-singlefile", "-png", "-scale-to", "1900", str(root / "source.pdf")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=45,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "PDF page render timeout"}), 504
    if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        detail = result.stderr.decode("utf-8", errors="replace")[-500:]
        print("[PDF PAGE RENDER ERROR]", pdf_id, page, detail, flush=True)
        return jsonify({"error": "PDF page render failed"}), 500
    response = Response(result.stdout, mimetype="image/png")
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["X-Clova-PDF-Ref"] = f"clova://pdf/{pdf_id}/page/{page}"
    return response


def api_pdf_view_state():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    body = request.get_json(silent=True) or {}
    pdf_id = _safe_pdf_id(body.get("pdf_id"))
    reading = bool(body.get("reading", False))
    client_id = str(body.get("client_id") or "").strip()[:128]
    try:
        page = max(1, int(body.get("page") or 1))
    except Exception:
        page = 1
    with s.lock:
        meta = _read_json_path(s.root / "session.json", {})
        ids = _session_pdf_ids(meta)
        if pdf_id and pdf_id not in ids:
            return jsonify({"error": "PDF is not attached to this session"}), 400
        if reading and not pdf_id:
            return jsonify({"error": "reading=true requires pdf_id"}), 400
        meta["pdf_workspace_schema"] = PDF_WORKSPACE_SCHEMA
        meta["pdf_ids"] = ids
        meta["pdf_view_state"] = {
            "active_pdf_id": pdf_id,
            "page": page,
            "reading": bool(reading and pdf_id),
            "updated_at": _now_iso(),
            "source": "viewer_state_plus_recording_timeline_when_owner",
        }
        _write_json_path(s.root / "session.json", meta)

        owns_recording = bool(
            s.recording
            and client_id
            and (not s.recording_client_id or client_id == s.recording_client_id)
        )
        timeline_event = None
        if owns_recording:
            timeline_event = _sync_pdf_timeline_to_view_locked(s, reason="viewer_change")

        result = _pdf_public_for_session(s)
        result["timeline_event"] = timeline_event
        result["timeline_recorded"] = bool(timeline_event)
        result["timeline_recording_owner"] = bool(owns_recording)
        return jsonify(result)



def api_pdf_events():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    with s.lock:
        events = _read_pdf_events(s)
        return jsonify({
            "schema": PDF_TIMELINE_SCHEMA,
            "default_state": "no_pdf",
            "state": _pdf_state_from_events(events),
            "events": events,
        })


def api_pdf_semantic_timeline():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    with s.lock:
        payload = _build_pdf_semantic_timeline_locked(s, write=True)
        return jsonify(payload)


def api_annotation_anchor():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    body = request.get_json(silent=True) or {}
    with s.lock:
        context = _annotation_time_context_locked(s, body)
        return jsonify({"schema": ANNOTATION_SCHEMA, **context, "captured_at": _now_iso()})


def api_annotations():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    with s.lock:
        events = _read_annotation_events(s)
        state = _annotation_state_from_events(events)
        return jsonify({
            "schema": ANNOTATION_SCHEMA,
            "soft_erase": True,
            "events": events,
            "active_annotations": state["active"],
            "erased_ids": state["erased_ids"],
        })


def api_annotation_stroke():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    body = request.get_json(silent=True) or {}
    pdf_id = _safe_pdf_id(body.get("pdf_id"))
    if not pdf_id or _pdf_meta(pdf_id) is None:
        return jsonify({"error": "invalid pdf_id"}), 400
    try:
        page = max(1, int(body.get("page") or 1))
    except Exception:
        page = 1
    tool = str(body.get("tool") or "pen").strip().lower()
    if tool not in ANNOTATION_TOOLS:
        return jsonify({"error": "tool must be pen or highlighter"}), 400
    points = _validated_annotation_points(body.get("points"))
    if not points:
        return jsonify({"error": "annotation points are required"}), 400
    annotation_id = _safe_annotation_id(body.get("annotation_id")) or f"ann_{uuid.uuid4().hex}"
    style = ANNOTATION_STYLE[tool]
    with s.lock:
        meta = _read_json_path(s.root / "session.json", {})
        if pdf_id not in _session_pdf_ids(meta):
            return jsonify({"error": "PDF is not attached to this session"}), 400
        context = _annotation_time_context_locked(s, body)
        event = _append_annotation_event_locked(s, {
            "type": "annotation_add",
            "annotation_id": annotation_id,
            "pdf_id": pdf_id,
            "page": page,
            "ref": f"clova://pdf/{pdf_id}/page/{page}",
            "tool": tool,
            "color": style["color"],
            "opacity": style["opacity"],
            "width_norm": style["width_norm"],
            "points": points,
            "anchor_type": context["anchor_type"],
            "lecture_time": context["lecture_time"],
            "recording_sample": context["recording_sample"],
            "created_at": str(body.get("created_at") or _now_iso())[:64],
            "created_during": context["created_during"],
            "lecture_time_source": context["lecture_time_source"],
            "recording_time_exact": context["recording_time_exact"],
            "recording_time_basis": context["recording_time_basis"],
            "pdf_follow_was_auto": bool(body.get("pdf_follow_was_auto", False)),
        })
        return jsonify({"ok": True, "event": event})


def api_annotation_erase():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400
    body = request.get_json(silent=True) or {}
    target_id = _safe_annotation_id(body.get("target_annotation_id"))
    if not target_id:
        return jsonify({"error": "invalid target_annotation_id"}), 400
    with s.lock:
        events = _read_annotation_events(s)
        state = _annotation_state_from_events(events)
        target = next((item for item in state["active"] if item.get("annotation_id") == target_id), None)
        if target is None:
            if target_id in state["erased_ids"]:
                return jsonify({"ok": True, "already_erased": True, "target_annotation_id": target_id})
            return jsonify({"error": "annotation not found"}), 404
        context = _annotation_time_context_locked(s, body)
        event = _append_annotation_event_locked(s, {
            "type": "annotation_erase",
            "target_annotation_id": target_id,
            "pdf_id": target.get("pdf_id"),
            "page": int(target.get("page") or 1),
            "ref": target.get("ref") or f"clova://pdf/{target.get('pdf_id')}/page/{int(target.get('page') or 1)}",
            "soft_erase": True,
            "operation_anchor_type": context["anchor_type"],
            "operation_lecture_time": context["lecture_time"],
            "operation_recording_sample": context["recording_sample"],
            "created_at": str(body.get("created_at") or _now_iso())[:64],
            "created_during": context["created_during"],
            "operation_lecture_time_source": context["lecture_time_source"],
            "operation_recording_time_exact": context["recording_time_exact"],
            "operation_recording_time_basis": context["recording_time_basis"],
        })
        return jsonify({"ok": True, "event": event, "target_annotation_id": target_id})


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


    include_deleted = str(
        request.args.get("include_deleted", "0")
    ).strip().lower() in {"1", "true", "yes", "on"}

    with s.lock:

        segments = (
            get_effective_segments(
                s,
                include_deleted=include_deleted,
            )
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


    variant = (request.args.get("variant", "clean") or "clean").strip().lower()
    raw_path = s.root / "segments" / f"{segment:06d}.wav"
    clean_path = s.root / "segments_clean" / f"{segment:06d}.wav"

    if variant == "raw":
        path = raw_path
        served_variant = "raw"
    elif clean_path.exists():
        path = clean_path
        served_variant = "clean"
    else:
        path = raw_path
        served_variant = "raw"


    if not path.exists():

        return jsonify({
            "error":
                "audio segment not found"
        }), 404


    response = send_file(
        str(path),
        mimetype="audio/wav",
        conditional=True,
    )
    response.headers["X-Clova-Audio-Variant"] = served_variant
    return response


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


        # V7.9.3: Human LOCK is both the visible source of truth and an
        # automatic supervised-data signal. Qwen3.8 whole-session review was
        # removed, so an edit no longer invalidates/re-runs an LLM pass.
        update_session_metadata(
            s,
            last_manual_edit=_now_iso(),
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


    try:
        adaptive_data = capture_training_samples_from_manual_edit(s, segment, text)
    except Exception as exc:
        adaptive_data = {"status": "capture_error", "created": 0, "error": repr(exc)}
        print("[ADAPTIVE DATA ERROR]", repr(exc), flush=True)

    print(
        "[MANUAL EDIT]"
        f" segment={segment}",
        f" adaptive={adaptive_data.get('status')}",
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

        "adaptive_data": adaptive_data,

        "committed_text":
            committed_text,
    })


# =========================================================
# V7 API: transcript / library deletion
# =========================================================

def _validate_segment_for_mutation(s, segment):
    if segment < 1 or segment > len(s.committed):
        return "invalid segment"
    if segment in s.pending_segments:
        return "wait until sentence processing finishes"
    return None


def api_delete_segment():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400

    body = request.get_json(silent=True) or {}
    try:
        segment = int(body.get("segment", 0))
    except Exception:
        segment = 0

    with s.lock:
        error = _validate_segment_for_mutation(s, segment)
        if error:
            return jsonify({"error": error}), 409 if "wait" in error else 400

        deleted = load_deleted_segments(s)
        key = str(segment)
        if key not in deleted:
            deleted[key] = {
                "deleted_at": _now_iso(),
                "deleted_by": "human",
            }
            save_deleted_segments(s, deleted)
            _invalidate_generated_session_outputs(
                s,
                reason="segment_deleted",
            )
            update_session_metadata(
                s,
                last_segment_delete=_now_iso(),
            )

    set_training_samples_disabled_for_segment(s, segment, True)
    print(f"[SEGMENT SOFT DELETE] segment={segment}", flush=True)
    return jsonify({
        "ok": True,
        "segment": segment,
        "deleted": True,
        **session_public_meta(s),
    })


def api_restore_segment():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400

    body = request.get_json(silent=True) or {}
    try:
        segment = int(body.get("segment", 0))
    except Exception:
        segment = 0

    with s.lock:
        error = _validate_segment_for_mutation(s, segment)
        if error:
            return jsonify({"error": error}), 409 if "wait" in error else 400

        deleted = load_deleted_segments(s)
        key = str(segment)
        existed = key in deleted
        if existed:
            deleted.pop(key, None)
            save_deleted_segments(s, deleted)
            _invalidate_generated_session_outputs(
                s,
                reason="segment_restored",
            )
            update_session_metadata(
                s,
                last_segment_restore=_now_iso(),
            )

    set_training_samples_disabled_for_segment(s, segment, False)
    print(f"[SEGMENT RESTORE] segment={segment}", flush=True)
    return jsonify({
        "ok": True,
        "segment": segment,
        "deleted": False,
        "restored": existed,
        **session_public_meta(s),
    })


def api_delete_session():
    sid = request.args.get("session_id", "")
    s = get_session_or_load(sid)
    if s is None:
        return jsonify({"error": "invalid session_id"}), 400

    with s.lock:
        if s.recording:
            return jsonify({"error": "stop recording before deleting the session"}), 409
        if s.pending_segments:
            return jsonify({"error": "wait until sentence processing finishes before deleting the session"}), 409
        if s.postprocess_status == "running":
            return jsonify({"error": "wait until postprocessing finishes before deleting the session"}), 409

        root = s.root
        title = s.title

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = TRASH_SESSIONS_ROOT / f"{sid}-{stamp}"
    counter = 2
    while target.exists():
        target = TRASH_SESSIONS_ROOT / f"{sid}-{stamp}-{counter}"
        counter += 1

    disabled_training = set_training_samples_disabled_for_session(sid, True)
    shutil.move(str(root), str(target))
    SESSIONS.pop(sid, None)

    print(
        f"[SESSION DELETE] {sid} -> {target.name}",
        f"training_samples_disabled={disabled_training}",
        flush=True,
    )
    return jsonify({
        "ok": True,
        "session_id": sid,
        "title": title,
        "deleted": True,
    })


def api_delete_subject():
    body = request.get_json(silent=True) or {}
    subject_id = str(body.get("subject_id") or "").strip()
    if not subject_id:
        return jsonify({"error": "subject_id is required"}), 400

    with SUBJECTS_LOCK:
        subjects = load_subjects()
        target = next((x for x in subjects if str(x.get("id")) == subject_id), None)
        if target is None:
            return jsonify({"error": "invalid subject_id"}), 400

        affected_roots = []
        busy = []
        for root in DATA_ROOT.iterdir():
            if not root.is_dir():
                continue
            meta = _read_json_path(root / "session.json", {})
            if str(meta.get("subject_id") or "") != subject_id:
                continue
            sid = str(meta.get("session_id") or root.name)
            live = SESSIONS.get(sid)
            if live is not None and (
                live.recording
                or live.pending_segments
                or live.postprocess_status == "running"
            ):
                busy.append(sid)
            affected_roots.append((root, sid, meta))

        if busy:
            return jsonify({
                "error": "stop active sessions / processing before deleting this subject",
                "busy_sessions": busy,
            }), 409

        save_subjects([
            item for item in subjects
            if str(item.get("id")) != subject_id
        ])

        moved = 0
        for root, sid, meta in affected_roots:
            meta["subject_id"] = ""
            meta["updated_at"] = _now_iso()
            _write_json_path(root / "session.json", meta)
            live = SESSIONS.get(sid)
            if live is not None:
                with live.lock:
                    live.subject_id = ""
                    _sync_final_navigation_metadata(live, meta)
            moved += 1

    print(f"[SUBJECT DELETE] {subject_id} sessions_to_unclassified={moved}", flush=True)
    return jsonify({
        "ok": True,
        "subject_id": subject_id,
        "name": str(target.get("name") or ""),
        "moved_sessions": moved,
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
            "Local Clova V8.1-alpha.1 UI is missing: /workspace/web/index_v6.html",
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
    global batisay_model
    global batisay_processor

    print(
        "[1/3] Loading Qwen3-ASR...",
        flush=True,
    )

    qwen_asr = Qwen3ASRModel.LLM(
        model=QWEN_ASR_MODEL,
        gpu_memory_utilization=0.15,
        max_new_tokens=96,
        enforce_eager=True,
    )

    print(
        "[2/3] Loading BatiSay-ko-large...",
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

    batisay_processor = (
        AutoProcessor
        .from_pretrained(
            BATISAY_MODEL
        )
    )

    _rebuild_batisay_pipeline()

    print(
        "[3/3] Audio enhancement backend...",
        flush=True,
    )
    if DENOISE_ENABLED and DENOISE_BIN.is_file() and os.access(DENOISE_BIN, os.X_OK):
        print(
            "[DENOISE READY] DeepFilterNet2 v0.5.6 -> clean WAV -> BatiSay",
            flush=True,
        )
    elif DENOISE_ENABLED:
        print(
            "[DENOISE WARN] deep-filter binary unavailable; adaptive Wiener fallback will be used",
            DENOISE_BIN,
            flush=True,
        )
    else:
        print("[DENOISE] disabled", flush=True)

    print(
        "[READY] Qwen3-ASR realtime + RAW-first BatiSay + optional DeepFilterNet + Adaptive Professor ASR",
        flush=True,
    )
    print(
        "[TIMELINE READY]", TIMELINE_SCHEMA_VERSION,
        "basis=accepted_capture_samples",
        flush=True,
    )
    print(
        "[QWEN3.8] removed since V7.9.3 · V8.1-alpha.1 · no llama-server dependency",
        flush=True,
    )
    print(
        "[LoRA]", "PEFT ready" if PEFT_AVAILABLE else "PEFT unavailable",
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

    # V8.1-alpha.1 PDF annotation + V8.0 workspace / playback auto-sync frontend support + append-only recording-time page events
    demo.app.add_url_rule(
        "/api/pdfs", "api_pdfs", api_pdfs, methods=["GET"]
    )
    demo.app.add_url_rule(
        "/api/pdf/import", "api_pdf_import", api_pdf_import, methods=["POST"]
    )
    demo.app.add_url_rule(
        "/api/pdf/file", "api_pdf_file", api_pdf_file, methods=["GET"]
    )
    demo.app.add_url_rule(
        "/api/pdf/page", "api_pdf_page", api_pdf_page, methods=["GET"]
    )
    demo.app.add_url_rule(
        "/api/pdf/view-state", "api_pdf_view_state", api_pdf_view_state, methods=["POST"]
    )
    demo.app.add_url_rule(
        "/api/pdf/events", "api_pdf_events", api_pdf_events, methods=["GET"]
    )
    demo.app.add_url_rule(
        "/api/pdf/semantic-timeline", "api_pdf_semantic_timeline", api_pdf_semantic_timeline, methods=["GET"]
    )
    demo.app.add_url_rule(
        "/api/annotation/anchor", "api_annotation_anchor", api_annotation_anchor, methods=["POST"]
    )
    demo.app.add_url_rule(
        "/api/annotations", "api_annotations", api_annotations, methods=["GET"]
    )
    demo.app.add_url_rule(
        "/api/annotation/stroke", "api_annotation_stroke", api_annotation_stroke, methods=["POST"]
    )
    demo.app.add_url_rule(
        "/api/annotation/erase", "api_annotation_erase", api_annotation_erase, methods=["POST"]
    )

    # V7.9.3 Adaptive Professor ASR
    demo.app.add_url_rule(
        "/api/subject/professor",
        "api_subject_professor",
        api_subject_professor,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/professor/status",
        "api_professor_status",
        api_professor_status,
        methods=["GET"],
    )

    demo.app.add_url_rule(
        "/api/professor/train",
        "api_professor_train",
        api_professor_train,
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

    # V7 transcript / library management
    demo.app.add_url_rule(
        "/api/segment/delete",
        "api_delete_segment",
        api_delete_segment,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/segment/restore",
        "api_restore_segment",
        api_restore_segment,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/session/delete",
        "api_delete_session",
        api_delete_session,
        methods=["POST"],
    )

    demo.app.add_url_rule(
        "/api/subject/delete",
        "api_delete_subject",
        api_delete_subject,
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
