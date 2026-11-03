# Local Clova

강의 녹음 → 실시간 한국어 STT → PDF/필기 타임라인을 로컬에서 돌리는 클로바노트 스타일 앱 (Ubuntu 26.04, AMD gfx1151 / ROCm).

- 오디오 캡처: HOST PipeWire `pw-record` (stereo) → `lecture_raw.wav` (authoritative)
- 오디오 frontend: pywebrtc APM (derivative only)
- VAD: Silero 6.2.1 + Adaptive Segmenter
- ASR: Whisper Large-v3 (whisper.cpp HIP 서버) 단일 모델 — final + preview + word timestamps
- UI: Flask + 브라우저 (`web/`). 네이티브 Qt UI(`ui_native/`, PySide6 6.12)로 전환 중 — 지금은 강의 열람, 단어 재생, 녹음 시작·정지·재개까지. 화면 테마 3개(종이 노트·스튜디오·클래식 라이트)는 설정(Ctrl+,)에서 고른다

현재 구조, 결정 사항, 남은 문제는 [LOCAL_CLOVA_V8_2_EPSILON_HANDOFF_2026-10-29.md](LOCAL_CLOVA_V8_2_EPSILON_HANDOFF_2026-10-29.md) 참고.
다음 버전(V8.3) 계획은 [LOCAL_CLOVA_V8_3_PLAN_2026-11-01.md](LOCAL_CLOVA_V8_3_PLAN_2026-11-01.md), STT 모델 조사는 [reports/](reports/)에 있다.

## 실행

```bash
./start-local-clova.sh
```

`start-local-clova.sh` → `start-local-clova-v8.2-epsilon-control.sh` →

- host: `clova_host_control_v8_2_gamma.py` (:8765) + `native_audio_daemon_v8_2_beta.py`
- host: whisper.cpp `whisper-server` (:8178)
- Docker: `run_clova_v8_2_gamma.py` (:8000)

백엔드 파일 이름은 `*_gamma.py`지만 내용은 V8.2-epsilon이다.

네이티브 UI (처음 한 번: `python3 -m venv .venv-ui && .venv-ui/bin/pip install PySide6==6.12.0`):

```bash
.venv-ui/bin/python -m ui_native        # 앱이 떠 있을 때 (:8000)
tools/run-native-ui-dev.sh              # 앱 없이: ASR/GPU 없는 읽기 전용 개발 백엔드(:8001)와 함께
```

## 리포에 포함되지 않은 것

`.gitignore`로 제외됨. 실행하려면 직접 준비해야 함.

- 모델 가중치: `models/whispercpp/ggml-large-v3.bin` 등 `models/`, `Qwen3-ASR-1.7B/`, `batisay-ko-large/`
- 외부 소스: `external/whisper.cpp` (HIP 빌드), `external/VibeVoice`
- `tools/deep-filter` (DeepFilterNet 바이너리)
- 개인 데이터: `data/`, `pdfs/`, `audio/`, `bench_results/`
- 런타임/로그/백업: `.runtime-*/`, `logs/`, `backups/`
