# Local Clova V8.2-epsilon 개발/디버깅 핸드오프

작성일: 2026-10-29 (이전판: V8.2-gamma, 2026-09-15 — git 히스토리에 보존)  
목적: **다음 세션/LLM이 현재 코드 상태에서 바로 이어서 개발·디버깅할 수 있도록**, 실제 코드·로그·백업 기준으로 구조·결정·남은 문제를 정리한다.

> 이 문서는 2026-10-29에 코드(`run_clova_v8_2_gamma.py`, 런처, 데몬), `backups/` 타임스탬프, `logs/`, 컨테이너 로그를 직접 확인해서 작성했다.  
> 직접 확인하지 못한 것은 "미확인"으로 표시했다.

---

## 0. 현재 상태 요약

현재 Local Clova는 **V8.2-epsilon (epsilon.4)** 이고, 실사용 중이다 (세션 57개, 마지막 녹음 2026-10-28~29).

- **ASR = Whisper Large-v3 하나뿐.** whisper.cpp HIP 서버(FP16, `:8178`)를 host에서 띄우고, segment마다 독립적으로 전사한다 (`-mc 0`, 이전 텍스트 context 없음).
  - Qwen3-ASR, BatiSay는 **더 이상 로드되지 않는다.** 코드/필드는 옛 세션 호환용으로만 남아 있다.
  - 미리보기(preview)도 Whisper로 한다 (epsilon.2 live preview, epsilon.2.1 bounded preview).
  - 단어 단위 타임스탬프 → word audio map (epsilon.3 word click).
- **오디오 캡처:** HOST PipeWire `pw-record` **스테레오** (Hotfix 6) → `lecture_raw.wav` (authoritative) → RAW-backed inference cursor.
- **오디오 frontend:** GStreamer `webrtcdsp`(Hotfix 5, 실패)는 버리고 **`pywebrtc_audio`** (WebRTC APM Python 바인딩)로 교체됨 (Hotfix 6). 기본 `AUDIO_FRONTEND=webrtc`, 실패 시 세션 단위로 fixed gain fallback (VAD +11 / ASR +6 dB).
- **VAD gain 기본값은 이제 0 dB.** webrtc AGC가 레벨을 맞춰주기 때문.
- 2026-09-16 `v8.2-gamma-stable` 스냅샷: 1h 강의 drill PASS (stereo capture, RAW 연속성, textbox 연속 생성, resume, pywebrtc frontend).
- 10월 실사용 로그: 세션당 1.0~2.1시간 녹음, 종료 시 `backlog_sec=0.0`, `dropped_asr_chunks=0`. 캡처/추론 경로는 안정적.

현재 실행:

```bash
cd ~/clova-note-copy
./start-local-clova.sh
```

> ⚠️ **옛 문서의 `--vad-db 11`을 쓰지 말 것.** webrtc 모드에서는 `--vad-db`가 AGC 출력 **위에** 추가로 곱해진다. +11 dB를 더하면 gamma 때 +13 dB와 같은 포화(clipping → Silero 확률 붕괴)가 날 수 있다. +11 dB는 frontend가 실패했을 때 자동 fallback 값일 뿐이다.

---

## 1. 프로젝트 철학 / 절대 지켜야 할 invariant

> **STT 모델은 소모품이고 Local Clova의 데이터/타임라인 구조가 본체다.**  
> **UI engines are replaceable. Local Clova Core is the product.**  
> **Audio is infrastructure, not UI. Browser may fail; recording may not.**

epsilon에서 Qwen/BatiSay → Whisper로 바꾼 것 자체가 이 철학대로 진행된 사례다.

오디오 원칙:

1. `lecture_raw.wav`는 authoritative capture. 가능한 한 bit-faithful하게 보존.
2. gain, NS, AGC, limiter, DeepFilter는 **derivative path에서만** 적용.
3. UI/ASR/VAD crash가 RAW 녹음을 중단시키면 안 됨.
4. `recording_time`은 브라우저 timestamp가 아니라 **캡처 sample count / 16000**.
5. RAW와 metadata가 어긋나면 RAW가 우선 (RAW > metadata → forward reconcile, RAW < metadata → FAIL).

---

## 2. 위치 / 환경

```text
프로젝트 홈 : /home/parks-zbook/clova-note-copy   (~/parksThink, /mnt/parksThink 아님)
GitHub      : github.com/mminggmmingg/clova-note-copy (private)
OS          : Ubuntu 24.04, kernel 7.0 (HWE)
Laptop      : HP ZBook Ultra G1a
GPU/APU     : AMD Ryzen AI Max+ PRO 395 / gfx1151 (ROCm, whisper.cpp는 HIP)
Audio       : PipeWire / pw-record
```

GitHub 리포에는 소스만 있다. 모델 가중치, `external/`, `data/`, `pdfs/`, `logs/`, `backups/`, `.runtime-*/`는 `.gitignore`로 제외돼 있다.

---

## 3. 실행 구조 (epsilon)

`start-local-clova.sh` → `start-local-clova-v8.2-epsilon-control.sh` 가 세 개를 띄운다:

| 구성 | 위치 | 파일 / 포트 |
|---|---|---|
| Host controller + native capture | host | `clova_host_control_v8_2_gamma.py` `:8765` → `native_audio_daemon_v8_2_beta.py` (`pw-record`) |
| Whisper 서버 | host | `external/whisper.cpp/build/bin/whisper-server`, `models/whispercpp/ggml-large-v3.bin`, `:8178` |
| Backend + Web UI | Docker `local-clova-v8-2-epsilon` (image `local-clova:rocm-v8-2-gamma-hotfix6`) | `run_clova_v8_2_gamma.py` `:8000`, `web/` |

> ⚠️ **파일 이름 버전 ≠ 실제 버전.** epsilon은 `*_gamma.py` 파일 위에서 개발됐다.  
> - 실제 실행되는 최신 백엔드: `run_clova_v8_2_gamma.py` (2026-09-22 수정, epsilon 코드 포함)  
> - `run_clova_v8_2_delta.py`: 9/16 delta 실험에서 멈춘 **죽은 가지**. 런처에서 안 씀.  
> - 런처 안에도 "V8.2-gamma" 문구가 여러 군데 남아 있음.

whisper.cpp 서버 옵션:

```text
-l ko -mc 0 -fa -bs 5 -bo 5 -t 4 --host 0.0.0.0 --port 8178
```

`-mc 0`(context 없음)은 9/18 90분 통파일 stress test에서 본 long-form 반복 루프를 막기 위한 것.

컨테이너 주요 env (런처 기준):

```text
VAD_INPUT_GAIN_DB=<--vad-db, 기본 0>
MODEL_INPUT_GAIN_DB=0.0
WHISPER_SERVER_URL=http://host.docker.internal:8178
STT_AUDIO_SOURCE_DEFAULT=raw
DENOISE_ENABLED=0
VAD_RESET_ON_SPEECH_END=1
VAD_TELEMETRY_ENABLED=1
```

종료 시 host controller가 Docker를 멈추고 whisper 서버에 SIGTERM을 보낸다 (epsilon hotfix4 shutdown).

---

## 4. 파이프라인

```text
Digital Mic
   ↓
PipeWire / pw-record --raw --rate=16000 --channels=2 --format=s16  [HOST]
   ↓
native_audio_daemon_v8_2_beta.py
   ├─→ lecture_raw.wav (stereo)        ← authoritative
   ├─→ exact sample counter → recording_time
   └─→ RAW-backed inference cursor → POST /api/chunk
                                         ↓
                                pywebrtc APM (stereo, derivative)
                                  └─ 실패 시 fixed_fallback (VAD +11 / ASR +6 dB)
                                         ↓
                                Silero VAD 6.2.1 (threshold 0.5, speech_end reset)
                                         ↓
                                Adaptive Segmenter
                                  ├─→ Whisper preview (bounded, latest-only, 비영구)
                                  └─→ segment WAV → Whisper final + word timestamps
                                         ↓
                                     textbox / word audio map
```

---

## 5. 2026-09-15 이후 변경 이력

`backups/` 디렉터리 타임스탬프 기준.

| 날짜 | 버전 | 내용 |
|---|---|---|
| 09-16 00:26 | gamma Hotfix 6 | **stereo capture + pywebrtc frontend.** GStreamer webrtcdsp(Hotfix 5) 대체. 데몬·백엔드·런처 수정 |
| 09-16 15:22 | gamma Hotfix 6.1 | stereo resume clock 수정 |
| 09-16 15:44 | **gamma stable** | `backups/v8.2-gamma-stable-20260916-154430/STABLE.txt` — 1h drill PASS |
| 09-16 16:13~21:43 | delta1~3 | BatiSay → Qwen → Professor LoRA를 `asr/engines/` adapter로 이전. `run_clova_v8_2_delta.py`와 delta 런처에서만 진행. **epsilon으로 이어지지 않음** |
| 09-18 | Whisper 벤치 | `bench_results/whispercpp` (large-v3 fp16 / q8_0 / q5_0), `whisper_stress` 15분·90분 |
| 09-22 00:31 | **epsilon** | Whisper Large-v3 단일 ASR. gamma stable 백엔드 위에서 시작 |
| 09-22 00:38~01:11 | epsilon hotfix1·3·4 | hotfix4 = shutdown 처리 (Docker 정지 + whisper SIGTERM) |
| 09-22 09:08 | epsilon.2 | Whisper live preview |
| 09-22 09:29 | epsilon.3 | Whisper word timestamps → word audio map, word click |
| 09-22 12:10 | epsilon.2.1 | bounded Whisper preview (window ≤6s, timeout ≤8s, 글자수/초 상한) |
| 09-29 16:10 | epsilon.4 | UI cleanup — Whisper 전용 production UI. 옛 세션용 legacy DOM 노드는 유지 |

---

## 6. 해결된 것 (옛 문서의 미해결 항목)

- **Hotfix 5 `webrtcdsp` 부재:** GStreamer 경로를 버리고 `pywebrtc_audio`로 교체해서 해결. 다시 GStreamer/Chromium clone 방향으로 가지 말 것.
- **adaptive frontend:** pywebrtc로 들어감. 1h drill PASS, 10월 실사용 OK.
- **V8.2-delta adapter 이전:** 별도 가지에서 끝냈지만, epsilon이 ASR을 Whisper 하나로 바꾸면서 사실상 대체됨.

---

## 7. 남은 문제 / 불일치 (2026-10-29 기준)

### 7.1 `NATIVE STATUS WARN FileNotFoundError` — 원인 확인됨

모든 세션 로그에 100~250회씩 찍힌다.

원인: `native_audio_daemon_v8_2_beta.py`의 `save_status()`를 **sender 스레드**(`clova-native-asr-raw-cursor`)와 **heartbeat 스레드**(`clova-native-clock`)가 동시에 부른다. `atomic_status()`가 둘 다 같은 `capture-<sid>.json.tmp`에 쓴 뒤 `replace()`하는데, 한쪽이 먼저 `.tmp`를 옮겨버리면 다른 쪽 `replace()`가 FileNotFoundError.

영향: 그 순간의 status 갱신 한 번이 빠질 뿐, PCM/RAW/추론에는 영향 없음 (dropped 0 확인). 하지만 로그 노이즈이고, 순서가 뒤바뀌면 오래된 snapshot이 새 snapshot을 덮을 수 있다.

수정 방향: `save_status()` 전체(snapshot + write)를 별도 `status_lock`으로 직렬화. `snapshot()`이 내부에서 `lock`을 잡으므로 같은 lock을 재사용하면 안 됨 (non-reentrant).

### 7.2 Professor LoRA가 production ASR과 끊겨 있음

- 학습(`_professor_train_worker`)은 여전히 `professor_lora_v7_9.py --base-model /workspace/batisay-ko-large`로 **BatiSay adapter**를 만든다.
- 그런데 epsilon production ASR은 Whisper이고 BatiSay는 로드되지 않는다.
- → 사람이 교정한 데이터가 쌓여도 현재 전사 품질에는 반영되지 않는다.
- 결정 필요: Whisper용 LoRA(whisper.cpp는 LoRA를 직접 못 씀 → HF Whisper로 학습 후 ggml 변환/merge)로 옮길지, 학습 데이터 수집만 유지할지.

### 7.3 ASR registry / profile이 옛 상태

- `asr/profiles/default.yaml`, `asr/registry.py`, `asr/engines/{qwen3_asr,batisay,professor_lora}.py`는 delta 상태 (Qwen/BatiSay)를 설명한다.
- 백엔드는 `ASR_REGISTRY = None`이고 `/api/asr/registry`는 Whisper 정보를 하드코딩해서 돌려준다.
- 정리하거나 Whisper engine adapter를 추가해야 함.

### 7.4 Whisper preview 간헐적 timeout (경미)

2026-10-29 세션(329 segment)에서 `[WHISPER PREVIEW ERROR] ReadTimeout` 5회. 같은 시점 whisper 서버 로그에 `client disconnected, aborted processing` + `whisper_full_with_state: failed to decode`. preview는 비영구·latest-only라 final 전사에는 영향 없음. final과 preview가 같은 서버/lock을 공유하므로 final이 길 때 preview가 밀리는 것으로 추정 (미확인).

### 7.5 파일/버전 정리

- 루트에 버전별 사본이 매우 많음 (`run_clova_v3` ~ `v8_2_gamma`, launcher 20여 개). 이제 git이 있으니 현재 파일만 남기고 정리 가능.
- 현재 버전 파일 이름이 실제 버전과 안 맞음 (3절 참고).

---

## 8. 다음 할 일 (우선순위)

```text
1. NATIVE STATUS WARN race 수정 (7.1) — 작고 확실한 버그, 캡처 경로 영향 없음
2. Professor LoRA 방향 결정 (7.2) — Whisper adaptation으로 옮길지
3. ASR registry/profile을 epsilon 상태로 정리 (7.3)
4. 루트 버전 사본 정리 + 현재 파일 이름 정리 (7.5)
5. 장기 로드맵: V8.2-final Core API → V8.3 Native UI
```

VibeVoice: `external/VibeVoice` clone과 `models/vibevoice/`가 있다. 실제 adapter/A-B 진행 여부는 미확인. 원칙은 그대로 — 새 engine slot으로 A/B, 현재 production ASR을 즉시 제거하지 않음, gfx1151 지원 리스크 때문에 캡처 안정성보다 우선하지 않음.

---

## 9. 건드리지 말 것

- native capture (pw-record → RAW → sample clock) 경로
- RAW-backed inference cursor
- Adaptive Segmenter 파라미터 (아래 10절)
- VAD telemetry, speech_end reset
- PDF/annotation timeline (V8.0~V8.1)
- word_audio_map / 학습 데이터 invariant (아래 11절)
- Qwen3.8 `:8083` whole-session postprocess 부활 금지 (V7.9.3에서 제거)

---

## 10. Adaptive Segmenter (V6.4 계열, 변경 금지)

```text
VAD_THRESHOLD              = 0.50
VAD_BASE_SILENCE_MS        = 450
SPEECH_PAD_MS              = 120
ADAPTIVE_SHORT_SILENCE_MS  = 1500
ADAPTIVE_MEDIUM_SILENCE_MS = 1000
ADAPTIVE_TARGET_SILENCE_MS = 600
ADAPTIVE_LARGE_SILENCE_MS  = 500
PREROLL_SEC                = 0.35
MAX_SENTENCE_SEC           = 28.0
```

흐름:

```text
speech_end → adaptive_silence_active=true → silence 누적
→ speech 재개 시 candidate 취소
→ threshold 넘으면 enqueue_sentence() → segment WAV 저장 → Whisper final
→ _reset_live_sentence_state()
```

---

## 11. word_audio_map / 학습 데이터 invariant

- 하나의 original WAV 보존.
- token index/text/start/end refs.
- correction은 original token span을 source audio에 매핑.
- insertion은 utterance-only training.
- delete는 phrase target 없음.
- N→M replacement는 original N-token span crop + corrected M target.

epsilon.3부터 token 시간은 Whisper word timestamps에서 온다.

---

## 12. 운영 / 디버깅

확인 포인트:

```text
RAW bytes 증가, recording_samples 증가
capture_stalled=false, capture_last_pcm_age_sec 작음
inference_backlog_sec 작음
segment_count 증가
[AUDIO FRONTEND] ... pywebrtc started channels=2  (fallback 문구가 없어야 함)
```

로그:

```bash
docker logs -f local-clova-v8-2-epsilon 2>&1 \
  | grep -E '\[VAD CONFIG\]|\[VAD HEALTH\]|\[AUDIO FRONTEND|\[SEGMENT DONE\]|\[WHISPER'
tail -f ~/clova-note-copy/logs/whisper-large-v3-server.log
tail -f ~/clova-note-copy/logs/native-audio-v8.2-gamma-<session>.log
```

정상 `[VAD CONFIG]` 예 (2026-10-29):

```text
silero_vad=6.2.1 threshold=0.5 vad_gain_db=0.0 audio_frontend=webrtc pywebrtc=1 reset_policy=speech_end telemetry=1
```

---

## 13. 디버깅 교훈 (gamma에서 얻은 것, 여전히 유효)

1. **"녹음 중" UI만 믿지 말 것.** RAW bytes, `recording_samples`, `capture_last_pcm_age_sec`, `inference_cursor_sample`, `inference_backlog_sec`를 볼 것.
2. **RAW가 커진다고 speech 인식이 정상인 건 아님.** gamma에서 RAW/추론/HTTP 모두 정상인데 VAD 확률만 붕괴한 적 있음.
3. **gain은 클수록 좋은 게 아님.** fixed gain +13 dB → limiter(0.985, -0.131 dBFS)에 계속 붙음 → Silero 확률 0 근처로 붕괴. +11 dB가 fixed 모드의 안전선.
4. **RAW와 derivative를 분리할 것.** gain/AGC/NS/limiter/DeepFilter는 derivative에만.
5. **한 번에 변수 하나만 바꿀 것.** gain 테스트 중 threshold를 같이 바꾸지 않음.
6. **subprocess stderr를 PIPE로 두고 drain 안 하면** pw-record가 막혀서 PCM이 조용히 멈춘다 (alpha hotfix3). 파일로 보낼 것.
7. **브라우저 polling + 전체 DOM 재구성은 장시간 세션에서 렌더 폭풍**을 만든다 (beta UI hotfix1). 변화가 있을 때만 갱신.

---

## 14. gamma 이전 역사 (요약)

- **V8.0-alpha:** `recording_time` 도입, captured samples가 master clock.
- **V8.0 PDF:** persistent PDF, `clova://pdf/<id>/page/<n>`, append-only PDF event timeline, playback auto-sync, semantic timeline.
- **V8.1:** pen/highlighter/eraser annotation, `annotation_events.jsonl`, anchor = `live_recording` / `playback` / `page_only`.
- **장시간 crackle (40~65분):** capture 단계에서 이미 깨짐. kernel 6.17 → 7.0 HWE로 ALSA EIO 해결, 남은 crackle은 브라우저 `ScriptProcessorNode` 캡처 구조 탓 → V8.2-alpha native capture로 전환.
- **V8.2-alpha:** `pw-record` native capture, 브라우저 getUserMedia 제거. hotfix: 권한(Docker root 소유 세션 dir), `--raw` autodetect, stderr drain + stall watchdog.
- **V8.2-beta:** `lecture_raw.wav`를 durable inference spool로 쓰는 RAW-backed cursor. UI lag hotfix.
- **V8.2-gamma:** ASR plugin interface, model input gain (RAW는 증폭 안 함), resume clock reconcile, Silero telemetry, speech_end reset, VAD/ASR gain 분리, +13 dB saturation 원인 규명, +11 dB baseline.

자세한 gamma 내용은 git 히스토리의 `LOCAL_CLOVA_V8_2_GAMMA_HANDOFF_2026-09-15.md` 참고.

---

## 15. 한 줄 핸드오프

> Local Clova는 V8.2-epsilon.4다. host `pw-record` 스테레오 캡처 → `lecture_raw.wav`(authoritative) → RAW-backed cursor → pywebrtc APM derivative → Silero VAD → Adaptive Segmenter → **whisper.cpp Large-v3 단일 ASR**(final + bounded preview + word timestamps) 구조로 10월 실사용에서 안정적이다. 실행은 `./start-local-clova.sh` (VAD 0 dB; `--vad-db 11` 쓰지 말 것). 백엔드 파일 이름은 아직 `*_gamma.py`다. 남은 일은 native status 파일 race 수정, Professor LoRA를 Whisper 쪽으로 다시 연결할지 결정, ASR registry 정리, 버전 사본 정리다.
