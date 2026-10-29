import io
import os
import json
import uuid
from pathlib import Path

import librosa
import numpy as np
import requests
import soundfile as sf
import torch

from flask import Flask, jsonify, request
from silero_vad import (
    load_silero_vad,
    get_speech_timestamps,
)

from transformers import (
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
    pipeline,
)


# =========================================================
# CONFIG
# =========================================================

SR = 16000

WHISPER_MODEL = "/workspace/whisper-large-v3"

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "http://172.17.0.1:8083",
).rstrip("/")

DATA_ROOT = Path(
    "/workspace/data/offline-tests"
)

DATA_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)


# 문장 분리용
VAD_THRESHOLD = 0.50

# 이 정도 쉬면 "문장 끝" 후보
MIN_SILENCE_MS = 800

MIN_SPEECH_MS = 250

# 음절 잘림 방지
SPEECH_PAD_MS = 200

# 교수님이 20초 이상 안 쉬면 강제 분할
MAX_SPEECH_SEC = 20.0


# =========================================================
# APP
# =========================================================

app = Flask(__name__)


# =========================================================
# LOAD MODELS
# =========================================================

print(
    "[1/2] Loading Silero VAD...",
    flush=True,
)

vad_model = load_silero_vad(
    onnx=True
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

processor = AutoProcessor.from_pretrained(
    WHISPER_MODEL
)

whisper_pipe = pipeline(
    "automatic-speech-recognition",
    model=whisper_model,
    tokenizer=processor.tokenizer,
    feature_extractor=
        processor.feature_extractor,
    torch_dtype=torch.float16,
    device=0,
)

print(
    "[READY] Whisper + Silero",
    flush=True,
)


# =========================================================
# LLAMA.CPP
# =========================================================

def discover_llm_model():

    try:

        r = requests.get(
            f"{LLM_BASE_URL}/v1/models",
            timeout=10,
        )

        r.raise_for_status()

        data = r.json()

        model_id = (
            data.get("data", [{}])[0]
            .get("id")
        )

        if model_id:

            print(
                "[LLM MODEL]",
                model_id,
                flush=True,
            )

            return model_id

    except Exception as e:

        print(
            "[LLM MODEL DISCOVERY ERROR]",
            repr(e),
            flush=True,
        )

    return "Qwen3.8-Flash-Next"


LLM_MODEL = discover_llm_model()


SYSTEM_PROMPT = """
You are an ASR transcription correction engine.

You receive speech recognition output from Whisper.

Your task is ONLY to correct transcription errors.

Allowed:
- correct obvious speech-recognition errors
- restore technical English terminology
- correct Korean/English mixed transcription
- normalize mathematical notation when strongly supported
- add punctuation
- correct names and domain-specific terminology when context
  strongly supports the correction

Forbidden:
- summarize
- explain
- add new facts
- remove substantive information
- rewrite the lecturer's wording into nicer prose
- invent content that was not spoken

Preserve fillers and uncertainty when they carry meaning.

If you are uncertain whether a word is wrong,
keep the Whisper transcription.

Output ONLY the corrected current transcript.
No explanation.
""".strip()


def llm_correct(
    title,
    whisper_raw,
    previous,
):

    user_prompt = f"""
SESSION TITLE:
{title}

PREVIOUS CONFIRMED TRANSCRIPT:
{previous if previous else "(none)"}

CURRENT WHISPER TRANSCRIPT:
{whisper_raw}

Correct only the CURRENT WHISPER TRANSCRIPT.

The session title and previous transcript are context only.
Do not copy information from them unless it clearly resolves
an ASR recognition error.
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
        "stream": False,
    }

    print(
        "[LLM] correcting...",
        flush=True,
    )

    try:

        r = requests.post(
            f"{LLM_BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=120,
        )

        r.raise_for_status()

        result = r.json()

        corrected = (
            result["choices"][0]
            ["message"]["content"]
        ).strip()

        if not corrected:
            return whisper_raw, "whisper"

        # -----------------------------------------------
        # hallucination guard
        # -----------------------------------------------

        ratio = (
            len(corrected)
            / max(1, len(whisper_raw))
        )

        if (
            ratio < 0.55
            or ratio > 1.65
        ):

            print(
                "[LLM REJECT]"
                f" length ratio={ratio:.2f}",
                flush=True,
            )

            return (
                whisper_raw,
                "whisper",
            )

        print(
            "[LLM CORRECTED]",
            corrected,
            flush=True,
        )

        return corrected, "llm"

    except Exception as e:

        print(
            "[LLM ERROR]",
            repr(e),
            flush=True,
        )

        return whisper_raw, "whisper"


# =========================================================
# AUDIO
# =========================================================

def load_audio(file_bytes):

    audio, sr = sf.read(
        io.BytesIO(file_bytes),
        dtype="float32",
        always_2d=False,
    )

    if audio.ndim > 1:

        audio = audio.mean(
            axis=1
        )

    if sr != SR:

        print(
            f"[RESAMPLE] {sr} -> {SR}",
            flush=True,
        )

        audio = librosa.resample(
            audio,
            orig_sr=sr,
            target_sr=SR,
        )

    audio = np.asarray(
        audio,
        dtype=np.float32,
    )

    return audio


def split_sentences(audio):

    wav_tensor = torch.from_numpy(
        audio
    )

    timestamps = (
        get_speech_timestamps(
            wav_tensor,

            vad_model,

            threshold=
                VAD_THRESHOLD,

            sampling_rate=
                SR,

            min_speech_duration_ms=
                MIN_SPEECH_MS,

            min_silence_duration_ms=
                MIN_SILENCE_MS,

            speech_pad_ms=
                SPEECH_PAD_MS,

            max_speech_duration_s=
                MAX_SPEECH_SEC,

            return_seconds=False,
        )
    )

    segments = []

    for ts in timestamps:

        start = int(
            ts["start"]
        )

        end = int(
            ts["end"]
        )

        if end <= start:
            continue

        segment = audio[
            start:end
        ].copy()

        segments.append({
            "start_sample": start,
            "end_sample": end,

            "start_sec":
                start / SR,

            "end_sec":
                end / SR,

            "audio":
                segment,
        })

    return segments


# =========================================================
# WHISPER
# =========================================================

def whisper_transcribe(audio):

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
# API
# =========================================================

@app.post("/v1/audio/transcriptions")
def transcriptions():

    if "file" not in request.files:

        return jsonify({
            "error":
                "file is required"
        }), 400


    title = (
        request.form.get(
            "title",
            ""
        )
        or ""
    ).strip()

    if not title:

        return jsonify({
            "error":
                "title is required"
        }), 400


    upload = request.files[
        "file"
    ]

    file_bytes = upload.read()

    audio = load_audio(
        file_bytes
    )


    print()
    print(
        "==================================",
        flush=True,
    )

    print(
        "[TITLE]",
        title,
        flush=True,
    )

    print(
        "[AUDIO]",
        f"{len(audio) / SR:.2f}s",
        flush=True,
    )


    segments = split_sentences(
        audio
    )


    print(
        "[VAD]",
        len(segments),
        "sentence candidates",
        flush=True,
    )


    # VAD가 아무것도 못 잡으면
    # 전체 파일을 하나의 문장으로 처리
    if not segments:

        segments = [{
            "start_sample": 0,
            "end_sample":
                len(audio),

            "start_sec": 0.0,
            "end_sec":
                len(audio) / SR,

            "audio":
                audio,
        }]


    response_segments = []

    confirmed = []


    for idx, seg in enumerate(
        segments,
        start=1,
    ):

        print()
        print(
            f"[SEGMENT {idx}] "
            f"{seg['start_sec']:.2f}"
            f" -> "
            f"{seg['end_sec']:.2f}",
            flush=True,
        )


        whisper_raw = (
            whisper_transcribe(
                seg["audio"]
            )
        )


        previous = "\n".join(
            confirmed[-3:]
        )


        final_text, source = (
            llm_correct(
                title=title,
                whisper_raw=
                    whisper_raw,
                previous=previous,
            )
        )


        if final_text:

            confirmed.append(
                final_text
            )


        response_segments.append({
            "segment": idx,

            "start":
                round(
                    seg["start_sec"],
                    3,
                ),

            "end":
                round(
                    seg["end_sec"],
                    3,
                ),

            "whisper_raw":
                whisper_raw,

            "llm_corrected":
                final_text
                if source == "llm"
                else None,

            "text":
                final_text,

            "source":
                source,
        })


    final_transcript = "\n".join(
        confirmed
    )


    # -----------------------------------------------
    # 테스트 결과 저장
    # -----------------------------------------------

    test_id = uuid.uuid4().hex[:10]

    out = {
        "id":
            test_id,

        "title":
            title,

        "model":
            "whisper-large-v3"
            "+qwen3.8-flash-next",

        "text":
            final_transcript,

        "segments":
            response_segments,
    }


    output_path = (
        DATA_ROOT
        / f"{test_id}.json"
    )

    output_path.write_text(
        json.dumps(
            out,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


    print()
    print(
        "[FINAL]",
        final_transcript,
        flush=True,
    )

    print(
        "[SAVED]",
        output_path,
        flush=True,
    )


    return jsonify(out)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print(
        "[LLM BASE URL]",
        LLM_BASE_URL,
        flush=True,
    )

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )
