# Local Clova V8.3 계획 — STT 엔진 재평가 + 자체 UI 전환

작성일: 2026-11-01  
기준 버전: V8.2-epsilon.4 (+ 2026-10-29 수정분, [핸드오프 문서](LOCAL_CLOVA_V8_2_EPSILON_HANDOFF_2026-10-29.md))  
근거:

- STT: [reports/한국어 강의 STT 모델 조사.md](reports/한국어%20강의%20STT%20모델%20조사.md) (출처 포함 보고서), 원자료 `research_notes/한국어 강의 STT 모델 조사/`
- UI: `research_notes/자체 UI 스택 조사/native_ui_stack_options.md`, 현재 코드 분석(아래 2.1)

이 문서는 **무엇을 어떤 순서로 해서 언제 결정할지**를 정한다. 모델 수치와 출처는 보고서에 있다.

---

## 0. 요약

| 축 | 결론 | 첫 작업 |
|---|---|---|
| STT | 1순위 후보는 **Qwen3-ASR-1.7B(기본판 + TeamUNIVA 한국어 파인튜닝판) + Qwen3-ForcedAligner-0.6B**. 2순위 batisay-ko v1.1(whisper.cpp 드롭인), 3순위 Nemotron 3.5 Transcribe(상한 탐색), 프리뷰용 Nemotron 3.5 Streaming 0.6B / NPU Whisper turbo / SenseVoice. 진짜 병목은 정확도보다 **gfx1151에서 재현 가능하게 도는가**. | 평가 세트 만들기 → 실행 가능성 관문 → 같은 세그먼트로 비교 |
| UI | **Qt 6 / QML**(PySide6로 시작). 펜 압력·터치는 Qt 6와 GTK 4가 가장 낫고, PDF는 Qt PDF(PDFium) + 자체 필기 레이어가 가장 현실적. Tauri는 WebKitGTK 펜 압력 0 보고로 탈락. | ZBook에서 펜/터치/PDF 스파이크 → 기존 Flask API에 붙는 QML 셸 |
| 순서 | STT 평가와 UI 전환은 서로 독립. UI는 **Flask API를 계약으로 고정**하고 프론트만 바꾸므로 STT 결정을 기다릴 필요가 없다. | 두 트랙 병행 |

지켜야 할 것은 그대로다: `lecture_raw.wav` authoritative, 캡처는 ASR/UI와 독립, 데이터 형식(session.json, transcript.jsonl, pdf/annotation events) 유지, Adaptive Segmenter 불변.

---

## 1. STT 트랙

### 1.1 보고서에서 가져온 핵심 사실

- 같은 Whisper Large-v3의 KsponSpeech CER이 출처마다 11–23%로 흔들린다. **같은 표 안에서만 비교**해야 하고, 최종 판정은 우리 강의로만 할 수 있다.
- 같은 채점기(kocer) 기준 자발화(KsponSpeech) CER: TeamUNIVA Qwen3 ko **6.08/6.46**, Qwen3-ASR-1.7B 8.69/8.57, Whisper Large-v3 11.06/11.85. 대신 Qwen3는 저음질 전화 음성에서 크게 무너진다(10.69 vs 4.97). 강의실 원거리 마이크에서 어느 쪽인지는 직접 재야 안다.
- Whisper 한국어 파인튜닝(batisay 등)은 한국어를 얻고 **영어 용어를 잃는 경향**(음차, 영어 WER 폭증). TeamUNIVA Qwen3 ko는 LibriSpeech 2.50 → 2.77로 영어를 거의 유지.
- **Qwen3-ForcedAligner-0.6B**는 어떤 ASR 출력이든 단어 시간을 다시 매길 수 있고, 한국어 경계 오차 37.2 ms. → ASR을 안 바꿔도 click-to-play를 개선할 수 있다.
- gfx1151 Linux에서 ASR이 돈다는 보고가 있는 경로는 **whisper.cpp HIP, CTranslate2 ROCm**뿐. Qwen3-ASR/Nemotron/VibeVoice를 이 칩에서 돌린 보고는 없음. AMD가 검증한 dtype은 fp16뿐(bf16 NaN 이슈 열려 있음). vLLM gfx1151은 같은 요청 결과가 달라지는 버그가 열려 있어 ASR에 부적합.
- Qwen3-ASR 예전 실험 경로(네이티브 스트리밍 + vLLM)는 의사 스트리밍·타임스탬프 없음·반복 보고가 있는 경로였다. Transformers 경로는 FA2 없으면 **8초 넘는 입력에 잘못된 어텐션**(PR #103 미병합) — 우리 세그먼트(1–28초) 대부분이 해당. 재평가는 세그먼트별 오프라인 + 수정 적용으로 해야 한다.
- 현행 whisper.cpp HIP Large-v3: 20초 세그먼트 7.02초(RTF 0.35), 대부분 빔 디코딩. CTranslate2 ROCm으로 같은 모델이 2–4배 빨라질 여지.
- 적응은 교수별보다 **강의 전체 pooled + 과목 용어 TTS 문장** 쪽이 효과가 크다는 2026 연구. 체크포인트는 학습 손실이 아니라 보류 강의로 고른다.

### 1.2 우리 데이터의 현실 — 정답 세트가 없다

- Whisper로 전사된 세션 30개, 세그먼트 8,495개 중 **사람이 고친 세그먼트 0개**. 교정 데이터는 BatiSay 시절 한 세션의 37개와 Professor 학습 풀 36개뿐.
- 보고서의 평가 프로토콜은 "사람이 교정한 세그먼트"를 정답으로 쓰므로, **평가 세트를 먼저 만들어야 한다**. 이 단계 없이는 어떤 엔진이 나은지 판정할 수 없다.

### 1.3 단계

| 단계 | 내용 | 끝나는 조건 | 사람 작업 |
|---|---|---|---|
| **S0 평가 세트** (세트 생성 완료, 라벨링 진행 전 — 아래 진행 상황) | 10–15개 강의에서 강의 단위·고정 seed로 300–500개 세그먼트 추출. 그중 100개는 **Whisper 출력 없이** 듣고 전사(블라인드, 참조 편향 측정용), 나머지는 앱 편집 기능으로 교정. 비음성 세트: 사람이 지울 세그먼트 + `lecture_raw.wav`의 판서·웅성거림 구간 100개. 단어 시작점 수작업 표시 30개 세그먼트(300–500 단어). LoRA용 강의는 처음부터 따로 뗀다. | `eval/` 매니페스트(세그먼트 경로, 정답, 블라인드 여부, 강의 id) 확정 | 교정 약 4–6시간, 블라인드 100개 약 2시간, 타임스탬프 표시 약 1–2시간 |
| **S1 평가 하네스** | 엔진 플러그인을 받아 같은 VAD 절단 WAV를 넣고 결과를 저장하는 스크립트. 채점: 원시/정규화 CER(kocer 고정 버전), 영어 용어 재현율·음차율, 비음성 출력률, 반복 루프율(앱의 `detect_whisper_repetition_loop()`), 타임스탬프 오차(부호 포함), RTF p50/p95, 강의 단위 쌍 부트스트랩 CI. | 현행 Whisper Large-v3로 기준선 표가 나옴 | — |
| **S2 대조군** | (a) Whisper Large-v3 + Qwen3-ForcedAligner(타임스탬프만), (b) Whisper Large-v3 on CTranslate2 ROCm(속도만), (c) 디코딩 옵션(beam 1 vs 5) | 이득이 모델/정렬기/런타임 중 어디서 오는지 분리 | — |
| **S3 batisay v1.1** | 저장소의 batisay-ko-large는 `version.json` 기준 2026-07 목록(최신 ko-turbo)을 갖고 있지만 받아 둔 가중치가 v1.1인지 확인 필요. whisper.cpp에 모델만 교체해 바로 평가 | 표에 한 줄 추가 | — |
| **S4 Qwen3-ASR 관문** | TheRock PyTorch 2.14(gfx1151 휠) fp16 + PR #103 적용으로 세그먼트 100개를 **비결정성 없이** 처리하는지. 실패 시 llama.cpp mtmd GGUF(ASR만)로 재시도. 통과하면 기본판·TeamUNIVA판·0.6B를 전체 평가 + ForcedAligner 결합 | 관문 통과/실패 기록 → 통과 시 평가표 | — |
| **S5 Nemotron 3.5 Transcribe 관문** | 반나절 제한: gfx1151에서 fp16(또는 bf16) 로드, 세그먼트 100개 완주 가능 여부. 약 68 GB(bf16) | 가능/불가만 기록, 가능할 때만 평가 | — |
| **S6 프리뷰 분리** | 프리뷰를 final과 다른 장치로: NPU(FastFlowLM Whisper turbo, v1.0.10+), CPU(SenseVoice-Small sherpa-onnx, Nemotron Streaming GGUF). 녹음 재생 시뮬레이션으로 지연 p95와 final 지연 변화 측정 | 프리뷰 타임아웃 0, final RTF 악화 없음 | — |
| **S7 결정** | 채택 기준(보고서 표): 정규화 CER 상대 10% 이상 개선 + CI가 0 미포함, 영어 용어 정확 재현율 −2%p 이내, 비음성 환각·루프율 현행 이하, final p95 RTF ≤ 0.35, 2시간 강의 2편 + 24시간 부하에서 크래시·비결정성 0 | 엔진 결정 → 운영 전환 | 결정 |

S0와 S1은 병행 가능. S2/S3는 S1 직후 바로. S4/S5는 실행 가능성 검사라 S0와 동시에 시작해도 된다.

#### S0 진행 상황 (2026-11-03)

평가 세트 `ko-lecture-v1`을 만들었다. 위치는 `data/eval/ko-lecture-v1/`이고 강의 음성과 텍스트라서 git에 올리지 않는다.

- **구성:** 과목 4개에서 강의 3개씩, 모두 12개(seed 20261103, 세그먼트 50개 미만 테스트 세션 제외).
  - 블라인드 100, 교정 300, 비음성 후보 100. 오디오 합계 94분.
  - 음성 세그먼트는 앱이 저장한 VAD 절단 WAV를 그대로 복사했다(2.4–28.1초, 중앙값 12.1초).
  - 비음성 후보는 세그먼트 사이 3초 이상 빈 구간에서 `lecture_raw.wav`를 모노로 잘라 만들었다(2.1–9.4초).
- **이 12개 강의는 평가 전용이다.** LoRA 학습 데이터에서 빼야 하고, 목록은 `set.json`의 `lectures`에 있다.
- **예상 사람 작업:**
  - 교정 300개(오디오 약 60분): 5–7시간
  - 블라인드 100개(약 20분): 2–3시간
  - 비음성 100개: 약 20분
- **단어 시작점 표시(30 세그먼트):** 파형 화면이 필요해서 S0-b로 뒤로 미뤘다.

라벨링 방법:

```bash
cd ~/clova-note-copy
python3 tools/eval-label-server.py data/eval/ko-lecture-v1
# 브라우저에서 http://127.0.0.1:8790/
```

- 순서는 블라인드 → 교정 → 비음성. 블라인드 항목에는 Whisper 텍스트가 서버에서부터 전달되지 않는다.
- 저장은 `labels.jsonl`에 한 줄씩 추가되고, 항목마다 마지막 줄이 유효하다. 중간에 꺼도 이어서 할 수 있다.
- 단축키:
  - `Ctrl+Enter`: 저장하고 다음
  - `Ctrl+Space`: 재생/정지
  - `Alt+←`: 2초 뒤로
  - `Alt+R`: 처음부터
- 전사 규칙은 화면 아래 "전사 규칙"에 있다. 들리는 대로 적고, 영어로 말한 단어는 영어 철자로 쓴다. 띄어쓰기와 문장부호는 채점 때 정규화한다.
- 새 세트 만들기: `python3 tools/eval-build-set.py --name <이름>`. 같은 이름의 기존 세트는 덮어쓰지 않는다.

### 1.4 엔진 구조 정리 (V8.3에서 같이)

현재 `asr/` 레지스트리는 delta 시절(Qwen/BatiSay) 그대로이고 백엔드는 Whisper를 직접 호출한다(핸드오프 7.3). 평가 하네스와 운영이 같은 인터페이스를 쓰도록 정리한다.

```text
AsrEngine.transcribe(wav_path) -> {text, chunks?, model, params}
Aligner.align(wav_path, text) -> [{word, start, end}]          # 선택
Preview.transcribe_window(pcm, sr) -> text                      # 저장 안 함
```

- `asr/profiles/default.yaml`에서 final / aligner / preview 슬롯을 고른다. 운영 기본값은 지금과 같은 whisper.cpp.
- 반복 루프 가드(`_whisper_final_with_loop_retry`)는 엔진 공통 후처리로 옮긴다(재시도 파라미터만 엔진별).
- 프로세스 경계: 엔진은 지금처럼 별도 서버(HTTP) 또는 워커 프로세스. Flask 프로세스 안에서 모델을 올리지 않는다.

### 1.5 Professor LoRA

- 엔진이 정해진 뒤에 다시 연결한다(지금은 BatiSay 어댑터를 만들고 아무도 안 쓴다).
- 방식: 교수별 쪼개기 대신 **pooled 어댑터 + 과목 용어 TTS 문장 + 일반 한국어 리플레이**, 선택은 보류 강의의 정규화 CER과 용어 재현율.
- Whisper 계열이면 PEFT 학습 → 병합 → ggml 변환(변환 후 재검증 필수). Qwen3-ASR이면 공식은 전체 SFT, LoRA는 커스텀 PEFT + vLLM 어댑터 서빙(단 vLLM gfx1151 비결정성 버그 때문에 Transformers 서빙 우선).
- gfx1151 학습은 fp16/fp32 혼합으로 작은 실험부터(파인튜닝 실패·bf16 NaN 보고 있음).

### 1.6 받아야 할 것 (다운로드는 사용자 승인 후)

| 항목 | 크기(대략) | 단계 |
|---|---|---|
| Qwen3-ASR-1.7B, Qwen3-ASR-0.6B, Qwen3-ForcedAligner-0.6B | 약 4 GB + 1.5 GB + 1.5 GB | S2, S4 |
| TeamUNIVA/qwen3_asr_1.7b_ko | 약 4 GB | S4 |
| batisay-ko-large / ko-turbo v1.1 ggml | 약 1.1–1.7 GB / 0.55 GB(q5_0) | S3 |
| CTranslate2 ROCm 휠 v4.8.x + faster-whisper, Large-v3 CT2 변환본 | 약 3 GB | S2 |
| TheRock PyTorch 2.14 gfx1151 휠 | 수 GB | S4 |
| Nemotron 3.5 Transcribe 30B-A4B | 약 68 GB(bf16) | S5 |
| Nemotron 3.5 ASR Streaming 0.6B, SenseVoice-Small, FastFlowLM | 각 1–2 GB 내외 | S6 |
| kocer (정규화 채점기) | 작음 | S1 |

크기는 모델 카드 기준 추정이며 받기 전에 확인한다.

---

## 2. 자체 UI 트랙

### 2.1 현재 UI (코드 분석, 2026-11-01)

- 백엔드 API **35개**(Flask, Docker 안). 그룹: 녹음 수명주기(start/resume/finish/recording-status/native clock/chunk), 라이브러리(library, subject, session meta/delete), 세그먼트(segments, audio, edit, delete, restore), PDF(pdfs, import, file, page PNG 렌더, view-state, events, semantic timeline), 필기(annotations, stroke, erase, anchor), Professor(status, train), 앱 종료.
- UI: `web/app_v6.js` **4,197줄, 함수 181개**. 영역별 대략: 라이브러리 680줄, PDF 640줄, 재생 520줄, 전사 목록 500줄, 필기 400줄, 녹음 120줄, 기타 1,100줄.
- PDF는 **서버가 페이지를 PNG로 렌더링**해 보낸다. 재생은 WebAudio 갭리스, 필기는 pointer 이벤트(압력 미사용), 상태는 polling(2026-10-29 복원한 500 ms status poll).
- 세션 데이터는 파일 기반: `session.json`, `transcript.jsonl`, `segments/*.wav`, `lecture_raw.wav`, `pdf_events.jsonl`, `annotation_events.jsonl`, `manual_edits.json`, `deleted_segments.json`, `vad_telemetry.jsonl`. 공용: `subjects.json`, `professors.json`, `pdfs/<pdf_id>/`.
- 알려진 UI 문제: 앱 종료 후 남는 종료 화면(전체 `backdrop-filter: blur` + 무한 회전 스피너)이 GPU를 계속 씀(2026-11-01 측정 gfx 약 17%). V8.3 이전에 바로 고칠 수 있는 작은 수정.

### 2.2 스택 선택

| 스택 | Wayland 펜 압력/터치 | PDF + 필기 | 판단 |
|---|---|---|---|
| **Qt 6 / QML** | 압력·기울기·버튼을 컴포지터에서 직접 받음(소스 확인) | Qt PDF(PDFium, LGPLv3) + `PdfMultiPageView`, 필기는 자체 레이어 | **채택** |
| GTK 4 / libadwaita | Rnote가 Wayland 압력 동작 실증 | Poppler + 자체 스트로크(Rnote 방식) | 대안. 2024 렌더러 전환 후 AMD/분수 배율 버그 이력 |
| Tauri 2 (WebKitGTK) | 펜 압력 항상 0 보고(2024-04), DMABUF 렌더러 문제 | 기존 JS 재사용 | 탈락(중간 단계로도 이득 적음: 이후 QML로 못 가져감) |
| Flutter | 펜을 손가락으로 인식한 버그, 압력은 서드파티 플러그인 | pdfrx 등 | 비추천 |
| Slint / egui / iced | 압력 필드 없음 / 확인 안 됨 | 직접 구현 | 비추천 |

- 언어: **PySide6로 시작**(백엔드와 같은 Python, 가장 빠름). Rust 코어는 별도 데몬으로 나중에. CXX-Qt 0.10(2026-08), Qt 공식 Rust 바인딩은 2026-10-27 기술 프리뷰라 UI 프로세스를 Rust로 쓰기엔 이르다.
- Qt 버전: 시스템 패키지(Ubuntu 26.04, Qt 6.10) 대신 **pip PySide6 휠**(6.12 LTS)로 고정해 OS 업데이트와 분리.
- 미검증(스파이크에서 확인): ZBook 펜 실제 압력, Qt Multimedia 갭리스 재생 가능 여부, 분수 배율.

### 2.3 단계 (Flask API를 계약으로 고정한 점진 전환)

| 단계 | 내용 | 끝나는 조건 |
|---|---|---|
| **U0 스파이크(1–2일)** | ZBook에서 `libinput debug-events`로 펜/터치 확인 → 작은 QML 앱: 펜 압력 필기, 두 손가락 팬/핀치, Qt PDF로 강의 PDF 표시, 600개 항목 ListView 스크롤 | 펜 압력·제스처·PDF·긴 목록 모두 OK면 Qt 확정, 아니면 GTK 4로 같은 스파이크 |
| **U1 읽기 전용 셸** | QML 앱이 기존 Flask API로 라이브러리, 세션 열기, 전사 목록, 단어 클릭 재생(일단 `/api/segment/audio`), 상태 표시. WebEngine 없이. 브라우저 UI는 그대로 유지(fallback) | 기존 세션을 네이티브로 열람 가능 |
| **U2 녹음 제어** | start/resume/stop, 캡처 상태(`/api/recording/status`), 라이브 프리뷰, 캡처 정지 경고, 앱 종료 화면(정적, GPU 0) | 브라우저 없이 녹음 한 세션 완주 |
| **U3 PDF + 필기** | Qt PDF로 클라이언트 렌더(서버 PNG 렌더 대체), 펜 압력 포함 스트로크를 기존 `annotation_events.jsonl` 형식 + 확장 필드(pressure)로 `/api/annotation/*`에 기록, PDF 페이지 이벤트도 기존 API | 기존 세션의 필기가 그대로 보이고 새 필기가 같은 형식으로 저장 |
| **U4 재생/타임라인** | 네이티브 갭리스 재생(Qt Multimedia 또는 PipeWire 직접), 재생 위치 ↔ 전사/PDF/필기 동기화 | WebAudio 재생과 같은 동작 |
| **U5 실시간 갱신** | polling → Unix 소켓(`$XDG_RUNTIME_DIR`) 이벤트 스트림(JSON lines) 또는 SSE. 세그먼트 확정/프리뷰/캡처 상태를 push | 녹음 중 polling 0 |
| **U6 코어 분리** | Flask를 "Local Clova Core" 데몬으로 정리(처음엔 Python 유지, 같은 API를 Unix 소켓으로도 제공). Docker는 ML 워커(ASR/LoRA)만. 이후 필요하면 Rust로 | 브라우저 UI 은퇴 결정 |

#### 진행 상황 (2026-11-03): STT는 보류, UI 트랙 먼저

**환경 확인**

- OS는 Ubuntu **26.04.1 LTS**다(문서의 24.04는 오기). 시스템 Qt는 6.10.2.
- UI는 프로젝트 venv `.venv-ui/`(git 제외)에 **PySide6 6.12.0 / Qt 6.12.0**으로 고정했다. QtQuick, Multimedia(FFmpeg 9.0.1), Pdf 모듈 모두 확인.
- 터치스크린 ELAN2513은 멀티터치를 지원한다. 압력을 내는 펜 장치는 없다(ABS_PRESSURE·BTN_TOOL_PEN 없음).
  - 기존 UI도 한 손가락 필기라서, U0의 핵심 위험이던 펜 압력은 해당 없음.
  - U0는 별도 스파이크 대신 U1~U3 안에서 터치·PDF를 바로 확인한다.

**U1 읽기 전용 셸(1차)**

- 코드는 `ui_native/`(`__main__.py`, `api.py`, `qml/Main.qml`).
  - 왼쪽은 과목별 강의 목록과 검색.
  - 오른쪽은 전사 카드: 시간, SEG 번호, 반복 의심/에러 표시.
  - 단어를 탭하면 그 위치부터 재생하고, 재생 중인 단어를 강조한다. 이어 재생, 하단 재생 바 포함.
  - 데이터는 기존 Flask API만 쓴다(`/api/library`, `/api/segments`, `/api/segment/audio`).
- 개발용 백엔드: `run_clova_v8_2_gamma.py`의 라우트 등록을 `register_routes(app)`로 분리했다. 동작은 그대로다.
  - `tools/dev-ui-backend.py`가 ASR·캡처·GPU 없이 실제 라우트를 띄운다(컨테이너, 프로젝트 읽기 전용 마운트, 127.0.0.1:8001).
  - `tools/run-native-ui-dev.sh` 하나로 개발용 백엔드와 UI를 함께 실행한다.
- 검증(offscreen 렌더 + 음소거 재생 자동 테스트):
  - 라이브러리와 전사 화면이 렌더링된다.
  - 단어 탭(1.53초)과 재생 중 다른 세그먼트로의 이동(2.0초)이 정확히 그 위치에서 재생된다.
  - 세그먼트가 끝나면 다음 세그먼트로 이어진다.
  - 재생 중인 단어가 강조된다.
- 알게 된 것:
  - Qt 6.12 FFmpeg 백엔드는 소스를 바꿀 때 이전 미디어의 LoadedMedia를 먼저 다시 알리고, 새 미디어를 불러오는 동안의 seek는 버린다. → LoadingMedia 다음의 첫 Loaded/Buffered에서 seek하도록 처리.
  - 영어·한글이 섞인 단어는 폰트가 달라 높이가 어긋났다. → 앱 기본 폰트를 Noto Sans CJK KR로 통일.
- 2026-11-03 디자인 재작업: 첫 버전이 보기 좋지 않다는 피드백을 받고 웹 UI(`web/app_v6.css`)의 디자인을 그대로 가져왔다.
  - 방법: 실제 데이터로 웹 UI를 띄워 계산된 스타일을 뽑았다.
  - 화면 구성:
    - 사이드바: 브랜드 마크, 검색, 학기 → 과목(접기, 교수, 개수) → 강의(점, 날짜), 하단 On-device 표시와 다크/라이트 전환
    - 헤더: 과목 pill, 엔진 배지, 제목, 전체 재생
    - 전사: 72px 시간 열과 인라인 재생, SEG 번호와 엔진 칩, 14.5px 본문
    - 재생 중인 문장: accent 테두리, 왼쪽 막대, NOW PLAYING
    - 재생 중인 단어: 노란 하이라이트
    - 빈 화면 히어로
  - 파일: `qml/Theme.qml`(디자인 토큰, singleton), `Sidebar.qml`, `TranscriptRow.qml`, `EmptyState.qml`, `Icon.qml`
  - 웹과 일부러 다르게 한 점:
    - 히어로의 무한 회전·파형 애니메이션은 넣지 않았다(GPU를 계속 씀).
    - 재생 바는 불투명하게 띄우고, 전사 목록 아래쪽을 배경색으로 페이드했다.
    - QML `font.pixelSize`는 정수만 받아서, 웹의 소수 px(11.5, 8.5 등)는 같은 크기의 pointSize(px × 0.75)로 옮겼다.
  - 실행 옵션 `--theme dark|light`. 기본은 데스크톱 설정을 따른다(웹과 같음).
- 2026-11-03 노트북 테마를 기본으로: 사용자가 웹 UI의 노트북 테마 화면을 보여주며 "이걸로 하자"고 결정했다. (같은 날 아래 "디자인 개편"의 테마 3개로 바뀌었다. 손글씨 폰트는 본문 글꼴 선택지로 남았다.)
  - 방법: 웹을 노트북 테마로 띄워 계산된 스타일과 의사요소(테이프)를 뽑아 옮겼다.
  - 화면 요소:
    - 종이 버튼(그라데이션, 아래 립, 그림자, 살짝 기울기), 테이프
    - 브랜드 카드와 색 막대
    - 새 세션, 라이브러리 +, 앱 종료, 테마 순환(노트북 → 다크 → 라이트, QtCore Settings로 기억)
    - 헤더 PDF 타일과 추가 타일, 재개(초록)·전체 재생(주황)·정보
    - 히어로 카드
    - 전체화면 버튼(동작함), 사이드바 접기/펴기(동작함)
  - 전사:
    - 공책 줄(손글씨 줄 높이 = 글자 × 1.52)과 빨간 여백선
    - 손글씨 크기는 웹과 같이 창 너비에 따라 21~25px
    - 재생 중 문장은 테이프 붙은 노란 포스트잇(#fff0a6)과 "재생 중", 재생 중 단어는 노란 하이라이트
  - 사이드바 순서: 웹 `renderSidebar()`와 같다. 학기 최신순, 과목은 한글 우선 가나다순, 빈 과목은 "아직 세션이 없습니다.", 분류 없는 강의는 "기타".
  - 아직 연결 안 된 버튼(PDF 보기/추가, 정보)은 누르면 "다음 단계에서 연결" 안내만 띄운다. U3에서 연결한다. 새 세션, 재개, 앱 종료, 과목 만들기는 U2에서 연결했다.
  - 손글씨 폰트 Nanum Pen Script(OFL, google/fonts의 `ofl/nanumpenscript`)를 `ui_native/fonts/`에 넣었다. 앱 시작 때 등록하고, Qt에서 보이는 패밀리 이름은 "Nanum Pen"이다. 파일이 없으면 기본 폰트로 표시한다.
  - 손글씨 크기는 웹과 같다. 같은 21px에서 "암산으로" 너비가 웹 46px, Qt 45.3px. 1728px 너비 화면에서는 약 24px로 보인다.

**U2 녹음 제어(2026-11-03)**

- 네이티브 UI는 제어만 한다. 오디오는 지금처럼 호스트 캡처 데몬이 받는다. 그래서 창을 닫아도 녹음은 계속되고, 다시 열면 녹음 중인 세션을 그대로 이어서 보여준다(웹처럼 "재연결"을 누를 필요 없음).
- API는 웹과 같은 것만 쓴다(`api.py`):
  - 시작 `/api/start`: 제목, 과목, client_id. denoise 2, STT 소스 raw는 웹 기본값과 같다.
  - 재개 `/api/resume`, 정지 `/api/finish`. 정지는 캡처 데몬이 RAW를 flush하느라 최대 25초 걸릴 수 있어 타임아웃을 60초로 뒀다.
  - 상태 `/api/recording/status`, 과목 생성 `/api/subject`, 앱 종료 `/api/app/shutdown`.
  - 4xx/5xx면 응답의 `error` 문구를 그대로 토스트로 보여준다.
  - client_id는 설치마다 하나(`native-<uuid>`, QSettings)다. 웹은 탭마다 하나다. 앱을 다시 켜도 자기 녹음에 재연결할 수 있다.
- 화면:
  - 새 세션 대화상자: 과목(최신 학기 먼저), 제목, "● 녹음 시작". 과목 옆 +로 바로 과목을 만들 수 있다. Ctrl+N.
  - 과목 만들기 대화상자: 아이콘, 과목명, 학기(현재 학기 기본), 교수.
  - 헤더: 녹음 중이면 "● 녹음 중 12:34" 배지(캡처 시간)와 빨간 정지 버튼, 아니면 초록 재개 버튼.
  - 전사: 처리 중 문장은 흐린 글씨와 "WHISPER · 처리 중" 칩, 아래에 실시간 인식 카드(LIVE, 손글씨). 새 문장이 오면 맨 아래를 따라가고, 위로 스크롤하면 멈췄다가 끝으로 내리면 다시 따라간다.
  - 캡처 경고: PCM 정지, heartbeat 끊김, 상태 요청 6번 연속 실패(백엔드가 꺼져 있으면 약 3초)면 헤더 아래 빨간 띠와 "CAPTURE ERROR" 배지.
  - 정지 뒤 남은 처리 중 문장은 1.5초마다 다시 읽어 확정되는 걸 보여준다.
  - 앱 종료: 확인 대화상자 → 종료 요청 → 정적 "종료 완료" 화면(스피너 없음) → 1.6초 뒤 창이 닫힌다.
- 웹과 같은 갱신 방식: 상태는 500ms마다 폴링하고, 전사는 확정/처리 중 개수가 바뀔 때만 다시 읽는다.
- GPU: 녹음 중 계속 움직이는 애니메이션이 없다. 녹음 점은 상태 응답마다 깜빡임만 바꾼다(초당 2번 다시 그림). 대화상자 뒤는 블러 없이 어둡게만 한다.
- 막아 둔 것: 녹음 중 새 세션 시작, 다른 세션이 녹음 중일 때 시작/재개(그 세션을 열어 줌), 녹음 중 앱 종료, 마지막 문장 처리 중 재개.
- 검증(offscreen, 가짜 녹음 백엔드, 노트북·다크 테마):
  - 시작 → 실시간 카드와 처리 중 문장 → 캡처 정지 경고와 해제 → 정지(처리 중 1개) → 처리 완료 → 재개 → 정지 → 과목 만들기 → 앱 종료(창이 스스로 닫힘)까지 모두 통과. QML 경고 0.
  - 녹음 중 새 세션과 앱 종료는 막혔다.
  - U1 단어 탭 재생 회귀 테스트도 통과.
  - 실제 마이크와 Whisper로 한 세션 완주: 사용자가 실제 스택(:8000)에서 확인했다(2026-11-03).

**디자인 개편: 테마 3개, 설정에서 선택(2026-11-03)**

- 사용자 판단: 기존 화면(노트북/다크/라이트)이 "너무 구리다". 평이 좋은 앱 디자인을 조사해 시안 3개를 만들었고(Design 캔버스 "Local Clova 디자인 시안", PDF 화면 시안 포함), 사용자가 "3개 다 좋으니 설정에서 선택하게 하자"고 결정했다.
  - 조사에서 가져온 원칙: 장식을 줄이고(Granola, Craft), 구조는 보이기보다 느껴지게(Linear), 본문 타이포그래피가 주인공(Bear), 실시간 문장과 확정 문장은 모양을 다르게.
  - 버린 것: 테이프·기울기·종이 립, 문장마다 붙던 SEG 번호와 엔진 칩(엔진은 세션 정보로), 8–10px 저대비 글씨.
- 테마(`Theme.mode`, 레이아웃 파일이 테마마다 하나):
  - 종이 노트 `paper`(기본, `PaperLayout.qml`): 따뜻한 바탕(#F6F3ED)에 흰 페이지 카드, 명조 제목·본문(Noto Serif CJK KR), 아래 가운데 어두운 녹음 알약(점, 시간, 입력 레벨, 마이크 상태, 정지)과 재생 알약(재생, 위치 막대, 속도).
  - 스튜디오 `studio`(`StudioLayout.qml`): 어두운 작업실(#121214), 경로 막대, 녹음 바(모노 시간, 입력 레벨, "마이크 정상 · −18 dB", 정지 Ctrl .), 전사 옆 세션 정보 패널(과목·교수·날짜·길이·문장·엔진, 자료, 단축키), 아래 재생 막대(10초 앞뒤, 속도, 이어 재생).
  - 클래식 라이트 `classic`(`ClassicLayout.qml`): 과목 | 강의 목록 | 본문 3단, 과목은 글자 배지, 강의 카드는 날짜·길이·문장 수, 본문 위에 큰 녹음 카드(시간 40px, 입력 레벨, 둥근 정지 버튼)와 재생 카드.
- 설정 대화상자(사이드바 아래 조절 아이콘, Ctrl+,): 테마 3개(미리보기 그림), 본문 글꼴(테마 기본·명조·고딕·손글씨), 앱 종료. 고르면 바로 바뀌고 QtCore Settings(`ui/theme`, `ui/bodyFont`)에 남는다. 예전 값(notebook/dark/light)은 paper/studio/classic으로 옮긴다. `--theme paper|studio|classic`은 그 실행에만 적용.
- 실제 데이터만 쓴다:
  - 입력 레벨 막대는 `/api/recording/status`의 `vad_input_rms_dbfs_1s`를 폴링마다 하나씩 쌓은 것(최근 160개). 움직이는 애니메이션 없이 새 값이 올 때만 다시 그린다.
  - 강의 카드의 길이·문장 수는 `/api/library`의 `recording_time_sec`, `segment_count`.
- 재생: 세그먼트 오디오는 그대로 쓰고, 강의 전체 시간으로 위치 막대·10초 앞뒤·속도(1→1.25→1.5→2→0.75)를 붙였다. 위치를 옮기면 그 시간이 든 세그먼트를 찾아 그 안에서 시작한다(갭리스는 여전히 U4).
- 공용 부품: `ActionButton`, `ModalCard`, `FormField`, `SearchField`, `Banner`, `LevelMeter`, `Scrubber`, `TranscriptView`(목록, 실시간 문장 + 정적 커서), `TranscriptRow`, `SessionInfo`, `Sidebar`(종이·스튜디오), `SubjectList`·`LectureList`(클래식), `SettingsDialog`, `ThemePreview`.
- 고친 것: 목록을 가운데 맞추는 여백이 처음 배치(폭 0) 때의 contentX에 고정돼 본문이 왼쪽으로 잘리던 문제, 페이지 머리말이 PDF 목록이 온 뒤 커지면서 첫 화면이 조금 내려가 있던 문제.
- 검증(offscreen, 세 테마 모두): U2 흐름 전체(시작 → 실시간·처리 중 → 캡처 정지 경고 → 정지 → 처리 완료 → 녹음 중 설정 열기 → 테마 즉시 전환 → 재개 → 정지 → 과목 만들기 → 앱 종료) 통과, QML 경고 0. 개발 백엔드의 실제 강의로 단어 탭 재생, 강의 시간 이동(98.6초 → 6번째 문장 2초 지점), 10초 뒤로, 속도 1.5× 확인.

- 아직 안 한 것:
  - 새 디자인을 실제 화면(Wayland, GPU 렌더러)에서 확인. 검증은 offscreen 소프트웨어 렌더러로만 했다.
  - 실제 화면(Wayland)에서의 터치 스크롤 감각과 HiDPI 확인
  - U3 PDF·필기(시안의 PDF 화면 3개가 기준), U4 갭리스 재생(지금은 세그먼트 단위 재생 + 이어 재생)

실행:

```bash
cd ~/clova-note-copy
tools/run-native-ui-dev.sh                 # 앱이 꺼져 있을 때: 개발용 백엔드(:8001)로
.venv-ui/bin/python -m ui_native           # ./start-local-clova.sh로 앱이 떠 있을 때(:8000)
```

원칙:

- 각 단계마다 **브라우저 UI와 네이티브 UI가 같은 데이터를 읽고 쓴다**. 형식 변경은 필드 추가만.
- 오디오는 IPC로 보내지 않는다(세그먼트 파일 공유 또는 PipeWire 직접).
- 모든 이벤트는 한 시계(`recording_time` = 캡처 샘플 수)를 쓴다.

### 2.4 API 쪽에서 미리 할 일

- 상태/세그먼트 push 채널(U5) 설계: `{"type": "segment", ...}`, `{"type": "preview", ...}`, `{"type": "capture", ...}`.
- `/api/segments`는 전체 목록 대신 `since=<segment>` 증분 조회를 추가(긴 강의에서 갱신 비용).
- 필기 이벤트에 `pressure`, `tilt` 선택 필드 추가(기존 클라이언트는 무시).
- 인증: 로컬 전용(127.0.0.1 / Unix 소켓 권한)으로 충분. LAN 노출은 2026-10-29에 막았다.

---

## 3. 진행 순서와 결정할 것

권장 순서:

1. (바로) 종료 화면 GPU 수정 — 작은 UI 수정
2. **S0 평가 세트 시작**(사람 작업이 가장 오래 걸림) + **U0 스파이크** 병행
3. S1 하네스 → S2 대조군 → S3 batisay → S4/S5 관문 → S6 프리뷰
4. U1 → U2 (STT 결정과 무관하게 진행)
5. S7 엔진 결정 → 운영 전환 + Professor LoRA 재연결
6. U3 → U6

사용자가 정할 것:

- 1.6의 모델/런타임 **다운로드 승인**(Nemotron 68 GB 포함 여부)
- S0 평가 세트 규모(300 vs 500 세그먼트)와 블라인드 전사 100개를 직접 할지
- 상용 천장 측정(교정 세그먼트 100–200개를 CLOVA Speech API로 보내기)을 할지 — 강의 음성을 외부로 보내는 일이라 기본은 **안 함**
- UI 언어를 PySide6로 시작하는 데 동의하는지(대안: C++ Qt)
- 전환 중 브라우저 UI를 언제 은퇴시킬지(U6 이후 제안)
