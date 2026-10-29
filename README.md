# Local Clova

강의 녹음 → 실시간 한국어 STT → PDF/필기 타임라인을 로컬에서 돌리는 클로바노트 스타일 앱 (Ubuntu 24.04, AMD gfx1151 / ROCm).

- 오디오 캡처: HOST PipeWire `pw-record` → `lecture_raw.wav` (authoritative)
- VAD: Silero 6.2.1 + Adaptive Segmenter
- ASR: Qwen3-ASR 1.7B (preview) / BatiSay-ko-large (committed) / Professor LoRA (adaptation)
- UI: Flask + 브라우저 (`web/`)

현재 구조, 결정 사항, 미해결 이슈는 [LOCAL_CLOVA_V8_2_GAMMA_HANDOFF_2026-09-15.md](LOCAL_CLOVA_V8_2_GAMMA_HANDOFF_2026-09-15.md) 참고.

## 실행

```bash
./start-local-clova.sh --vad-db 11
```

`start-local-clova.sh` → `start-local-clova-v8.2-epsilon-control.sh` → `run_clova_v8_2_gamma.py` (Docker) + `native_audio_daemon_v8_2_beta.py` + `clova_host_control_v8_2_gamma.py` (host).

## 리포에 포함되지 않은 것

`.gitignore`로 제외됨. 실행하려면 직접 준비해야 함.

- 모델 가중치: `Qwen3-ASR-1.7B/`, `batisay-ko-large/`, `models/` (whisper.cpp, VibeVoice, ASR 후보들)
- 외부 소스: `external/whisper.cpp`, `external/VibeVoice`
- `tools/deep-filter` (DeepFilterNet 바이너리)
- 개인 데이터: `data/`, `pdfs/`, `audio/`, `bench_results/`
- 런타임/로그/백업: `.runtime-*/`, `logs/`, `backups/`
