# Local Clova V8.2-gamma 개발/디버깅 핸드오프

작성일: 2026-09-15  
목적: **다른 ChatGPT 세션/LLM이 바로 이어서 개발·디버깅할 수 있도록, 현재까지의 구조·결정·버그·실험 결과·다음 작업을 한 문서에 정리**한다.

---

## 0. 가장 중요한 현재 상태 요약

현재 Local Clova는 **V8.2-gamma** 단계다.

핵심 상태:

- 브라우저 마이크 캡처는 제거됨.
- 오디오 캡처는 **HOST PipeWire / `pw-record`** 기반 native capture.
- `lecture_raw.wav`가 authoritative source.
- `recording_time`은 **실제로 캡처된 sample count / 16000** 기준.
- ASR inference는 `lecture_raw.wav`를 durable spool로 다시 읽는 **RAW-backed inference cursor** 방식.
- Chrome/PDF/annotation/ASR이 느려져도 RAW 녹음은 계속되어야 함.
- Silero VAD telemetry 추가 완료.
- Silero 버전: **6.2.1**.
- `speech_end` 시 VAD state reset 정책 추가 완료.
- VAD gain과 ASR gain 분리 완료.
- 현재 실측상 **VAD +11 dB가 가장 안정적인 baseline**.
- +12 dB도 후보지만 아직 +11보다 장시간 검증이 덜 됨.
- **+13 dB는 포화(clipping)로 Silero probability가 붕괴하므로 사용 금지.**
- ASR gain은 현재 **+6 dB**.
- WebRTC/GStreamer audio frontend를 넣으려 했으나 **Hotfix 5 설치 중 `webrtcdsp` plugin이 없어서 실패**. 이 부분은 아직 미완성/미해결.

현재 권장 fallback 실행:

```bash
cd ~/clova-note-copy
./start-local-clova.sh --vad-db 11
```

ASR gain 기본값은 launcher 기준 +6 dB.

---

# 1. 프로젝트 철학 / 절대 지켜야 할 invariant

Local Clova의 핵심 철학:

> **STT 모델은 소모품이고 Local Clova의 데이터/타임라인 구조가 본체다.**

또한 native UI 전환 철학:

> **UI engines are replaceable. Local Clova Core is the product.**  
> **The UI is only a view of the timeline.**

신뢰성 원칙:

> **Audio is infrastructure, not UI.**  
> **recording_time belongs to captured samples, not browser.**  
> **Browser may fail; recording may not.**

절대 깨면 안 되는 오디오 원칙:

1. `lecture_raw.wav`는 authoritative capture.
2. RAW는 가능한 한 bit-faithful하게 보존.
3. VAD/ASR용 gain, NS, AGC 등은 **derivative path**에서만 적용.
4. UI/ASR/VAD crash가 RAW 녹음을 중단시키면 안 됨.
5. `recording_time`은 브라우저 timestamp가 아니라 **캡처 sample count 기반**.

---

# 2. 프로젝트 위치 / 환경

프로젝트 홈:

```text
/home/parks-zbook/clova-note-copy
```

중요:

- **`~/parksThink`가 아니다.**
- `/mnt/parksThink`도 Local Clova runtime path가 아니다.
- 다른 프로젝트 경로를 Local Clova에 재도입하지 말 것.

주 환경:

```text
OS: Ubuntu 24.04
Laptop: HP ZBook Ultra G1a
Audio: PipeWire / pw-record
GPU/APU: AMD Ryzen AI Max+ PRO 395 / gfx1151
```

현재 Chrome:

```text
Google Chrome 153.0.8010.36
```

브라우저는 현재 UI용일 뿐, microphone PCM capture는 담당하지 않는다.

---

# 3. 현재 전체 파이프라인

현재 V8.2-gamma의 안정화된 구조:

```text
Digital Mic
   ↓
PipeWire / pw-record  [HOST]
   ↓
native_audio_daemon_v8_2_beta.py
   ├─→ lecture_raw.wav              ← authoritative
   ├─→ exact sample counter
   │      ↓
   │   recording_time
   │
   └─→ RAW-backed inference cursor
          ↓
      Flask /api/chunk
          ↓
      VAD input derivative
          ↓
      Silero VAD 6.2.1
          ↓
      Adaptive Segmenter
        ├─→ Qwen3-ASR preview
        └─→ BatiSay committed
              ↓
           textbox
```

V8.2-gamma 이후 목표는 ASR plugin adapter 구조로 production execution을 옮기는 것이지만, **지금은 audio/VAD 안정화가 먼저**다.

---

# 4. ASR 역할 분리

현재 역할:

```text
Preview / Realtime : Qwen3-ASR 1.7B
Committed          : BatiSay-ko-large
Adaptation         : Professor LoRA
```

중요:

- Qwen은 realtime preview.
- BatiSay는 committed transcript.
- Professor LoRA는 human correction 기반 adaptation.
- Human LOCK precedence 유지.
- Qwen3.8 whole-session postprocess는 V7.9.3부터 제거됨.
- **Qwen3.8 :8083 server를 자동 복원하지 말 것.**

---

# 5. V8.0 ~ V8.1 중요한 역사

## V8.0-alpha

주요 변화:

- `recording_time` 도입.
- accepted/captured samples가 master clock.
- pause gap을 recording_time에 잘못 포함하지 않음.

## V8.0 PDF 계열

- PDF persistent storage.
- `clova://pdf/<pdf_id>/page/<n>`.
- PDF event append-only timeline.
- playback PDF auto-sync.
- semantic timeline.

## V8.1 annotation

- pen / highlighter / eraser.
- one-finger draw, two-finger pan/pinch.
- `annotation_events.jsonl` append-only.
- drawing anchor:
  - recording 중 → `live_recording`
  - playback 중 → `playback`
  - 둘 다 아니면 → `page_only`, `lecture_time=null`

이 영역은 현재 정상이며, V8.2 audio 안정화 작업 중 **건드리지 않는 것이 원칙**.

---

# 6. 장시간 오디오 깨짐 문제와 native capture 전환

## 과거 문제

약 40~65분 이후:

- micro-stutter
- 반복 음절
- 예: “각 각각의”, “그 그래픽스”
- playback 자체가 끊김
- STT도 이상해짐

문제 세션 대표:

```text
20260908-055338-65e87006
SEG 453
3948.4–3974.0s
```

분석 결과:

- `lecture_raw`
- raw crop
- segment
- clean

모두 깨져 있었음.

따라서 당시 문제는 VAD/DeepFilter/STT가 아니라 **capture 단계에서 이미 발생**.

## 구 브라우저 capture 구조

```text
getUserMedia
→ AudioContext 48k
→ ScriptProcessorNode(4096)
→ browser-side 16k resample
→ Float32 concat
→ 250ms POST /api/chunk
```

Qwen inference도 request path와 강하게 연결돼 있었음.

## 커널 이슈

구 kernel:

```text
6.17.0-1032-oem
```

에서 ACP/PDM ALSA EIO 및 AMD-Vi IO_PAGE_FAULT가 관찰됨.

HWE kernel:

```text
7.0.0-31-generic
```

으로 direct ALSA capture EIO 문제는 사라짐.

하지만 browser capture crackle은 남아 있었음.

## 결정적 A/B

동시에:

- Local Clova browser capture
- `pw-record`

를 돌렸을 때:

- Local Clova는 crackle
- `pw-record`는 clean

따라서 kernel 7.0 이후 남은 주 원인은 browser/Local Clova capture architecture로 판단.

---

# 7. V8.2-alpha native capture

artifact 역사:

```text
/mnt/data/clova-v8.2-alpha-bundle.zip
```

핵심 구조:

```text
Digital Mic
  → PipeWire / pw-record HOST
  → native_audio_daemon_v8_2_alpha.py
      ├→ lecture_raw.wav immediately
      ├→ exact sample counter → recording_time
      └→ isolated inference queue
```

브라우저 capture API 제거:

- `getUserMedia` 제거
- AudioContext capture 제거
- ScriptProcessor capture 제거
- browser resample/pump 제거

브라우저는 `/api/recording/status` polling.

---

# 8. V8.2-alpha에서 발생한 버그들

## 8.1 PermissionError

증상:

```text
PermissionError: [Errno 13] .../lecture_raw.wav
```

원인:

- Docker root가 session dir 생성
- host daemon은 `parks-zbook` 권한으로 실행

해결:

- current session ownership handoff
- global chmod는 사용하지 않음

artifact:

```text
/mnt/data/clova-v8.2-alpha-permission-hotfix.zip
```

---

## 8.2 `pw-record --raw` unsupported

사용자 환경의 `pw-record`가 `--raw`를 지원하지 않았음.

해결:

- `--raw` 지원 여부 autodetect
- unsupported면 해당 옵션 없이 실행

artifact:

```text
/mnt/data/clova-v8.2-alpha-hotfix2.zip
```

---

## 8.3 녹음 UI는 살아 있는데 audio/text가 멈추는 문제

원인 후보를 추적하다가 native daemon 내부에:

```python
stderr=subprocess.PIPE
```

를 사용하면서 stderr를 drain하지 않는 문제가 발견됨.

가능한 failure:

```text
pw-record stderr pipe full
→ pw-record write block
→ daemon heartbeat는 살아 있음
→ UI에는 녹음 중으로 보임
→ 실제 PCM 정지
```

해결 hotfix3:

- pw-record stderr를 file로 routing/drain
- `last_pcm_age_sec`
- sample progress watchdog
- `capture_stalled`
- false “Recording” 대신 capture error
- hidden auto restart는 하지 않음

artifact:

```text
/mnt/data/clova-v8.2-alpha-hotfix3.zip
```

이후 약 40분 drill에서 기존 장시간 crackle/stop이 재현되지 않았음.

---

# 9. V8.2-beta: RAW-backed inference

V8.2-beta에서 가장 큰 변화:

기존 bounded RAM queue를 inference source로 쓰지 않고,

```text
lecture_raw.wav 자체를 durable inference spool
```

로 사용.

구조:

```text
Mic → PipeWire/pw-record → native capture
   ├→ lecture_raw.wav authoritative
   ├→ recording_time
   └→ inference cursor re-reads durable RAW
       → /api/chunk
       → VAD/Qwen/BatiSay
```

장점:

- STT stall 시 RAW 녹음은 계속.
- inference cursor는 나중에 catch-up 가능.

상태 필드:

```text
inference_cursor_sample
inference_backlog_samples
inference_backlog_sec
capture_dropped_chunks
```

---

# 10. V8.2-beta UI lag 버그

장시간 실행 후 browser가 극도로 느려졌지만 capture/inference는 정상.

원인:

- 500ms `/api/recording/status` poll
- 700ms `/api/segments`
- `refreshSelectedSession()`
- `showSession()`이 transcript DOM 전체 rebuild
- PDF/drawing rerender
- duplicate `renderPdfViewer()`

즉 transcript가 커질수록 browser rerender storm.

해결:

- recording 중 700ms full-session refresh 제거
- segment/pending count 변화 시에만 full refresh
- duplicate PDF render 제거
- cache bust

artifact:

```text
/mnt/data/clova-v8.2-beta-ui-hotfix1.zip
```

SHA-256:

```text
23874dba0dc9c0ef4bab526e1aa3fdc2fc484cda0d5df37a823e89349b185bf9
```

적용 후 사용자가 “이제 정상작동한다”고 확인.

---

# 11. V8.2-gamma ASR Plugin Interface

artifact:

```text
/mnt/data/clova-v8.2-gamma-bundle.zip
```

SHA-256:

```text
4fed160c5f1e91fefa573e31efde205c0cf20b436d61d1db19cef6de6e5cf8f8
```

추가 구조:

```text
asr/
├── base.py
├── schema.py
├── registry.py
├── profiles/default.yaml
└── engines/
```

중요:

- gamma는 **interface only**.
- production execution은 아직 legacy direct Qwen/BatiSay path.
- 실제 adapters로 execution을 옮기는 것은 **V8.2-delta 목표**.

---

# 12. 모델 입력 gain hotfix

사용자가 직접 들었을 때 입력이 너무 작다고 판단.

결정:

- RAW는 절대 증폭하지 않음.
- VAD/ASR용 derivative에만 gain 적용.
- browser playback에도 monitor gain 적용.

artifact:

```text
/mnt/data/clova-v8.2-gamma-gain-hotfix1.zip
```

SHA-256:

```text
cee0c221e9d4f0a0b611bcdae5b984faa204eba4d88549d8253d256fd523569e
```

당시 기본:

```text
MODEL_INPUT_GAIN_DB = +6 dB
```

적용 대상:

- Silero VAD
- Qwen preview
- BatiSay primary/fallback

이후 VAD gain과 ASR gain은 분리됨.

---

# 13. Resume clock mismatch 버그

증상:

resume 시:

```text
wav_frames   = 11076270
start_sample = 11019342
```

차이:

```text
56,928 samples ≈ 3.558 sec
```

원인:

- RAW writer는 계속 기록
- metadata clock checkpoint는 약간 뒤처질 수 있음
- 기존 resume code가 `RAW frames == metadata start_sample`을 강제

올바른 원칙:

```text
RAW > metadata
→ RAW가 실제 캡처의 truth
→ clock을 RAW 끝으로 forward reconcile

RAW < metadata
→ metadata가 존재하지 않는 audio를 가리킴
→ FAIL
```

artifact:

```text
/mnt/data/clova-v8.2-gamma-resume-hotfix2.zip
```

이후 stop 시에도 final RAW frame count를 metadata로 reconcile하도록 수정.

중요 원칙:

> **recording_time metadata보다 실제 `lecture_raw.wav`가 우선한다.**

---

# 14. “textbox가 멈춤” 문제의 결정적 디버깅

장시간 사용 중 textbox 생성이 다시 멈추는 현상이 발생.

처음에는 다음을 의심:

- capture stall
- inference cursor stall
- HTTP /api/chunk stall
- VAD state stuck
- segmentation bug

하지만 실제 로그에서:

```text
capture_alive=true
capture_stalled=false
capture_last_pcm_age_sec ≈ 0.00~0.12
inference_backlog_sec ≈ 0.1~0.2
recording_samples 증가
inference_cursor_sample 증가
/api/chunk 200 계속
```

즉:

```text
Mic/PipeWire       정상
RAW growth         정상
Inference cursor   정상
HTTP transport     정상
```

그런데:

```text
vad_active=false
unfixed_text=""
segment_count 고정
```

따라서 VAD layer로 범위를 좁힘.

---

# 15. RAW 자체 음량 검사

문제 당시 RAW 마지막 10초 분석:

```text
rate      : 16000
channels  : 1
width     : 2
RMS dBFS  : -12.754
PEAK dBFS : -8.664
zero %    : 0.0
```

결론:

- mic/PipeWire/raw는 정상.
- 무음 source 문제가 아님.
- 실제로 충분히 큰 음성이 RAW에 존재.

따라서 VAD frontend 문제로 확정적으로 이동.

---

# 16. Silero VAD telemetry hotfix

사용자가 제안/승인한 항목:

1. Silero probability telemetry
2. installed Silero version 확인
3. speech_end 시 reset 정책 검토/적용
4. VAD와 ASR +6 dB gain 분리 A/B

artifact:

```text
/mnt/data/clova-v8.2-gamma-vad-hotfix3.zip
```

추가 기능:

- `vad_telemetry.jsonl`
- 1초 수준 summary
- probability last/mean/max/min
- threshold-above ratio
- input RMS/peak dBFS
- speech start/end
- reset count
- Silero version

Silero version:

```text
6.2.1
```

reset policy:

```text
speech_end
```

주의:

- `speech_end`에서 Silero internal state만 reset.
- Adaptive Segmenter의 기존 silence threshold는 유지.
- segment commit 시 기존 reset도 유지.

---

# 17. VAD gain CLI 옵션

artifact:

```text
/mnt/data/clova-v8.2-gamma-vad-cli-hotfix4.zip
```

지원:

```bash
./start-local-clova.sh --vad-db 0
./start-local-clova.sh --vad-db 3
./start-local-clova.sh --vad-db 11
./start-local-clova.sh --vad-db 12
./start-local-clova.sh --vad-db 13
```

또는 alias:

```bash
./start-local-clova.sh --vad-gain-db 11
```

VAD gain과 ASR gain은 독립.

---

# 18. +13 dB VAD에서 발생한 결정적 saturation

사용자는 +13 dB에서 초반에는 인식이 좋아졌다고 느꼈지만 이후 멈춤.

telemetry:

```text
VAD gain = 13 dB
RMS ≈ -0.2 dBFS
Peak ≈ -0.131 dBFS
Silero p_mean ≈ 0.000~0.005
Silero p_max ≈ 0.000~0.015
above threshold ratio = 0.0
vad_active = false
segment_count 고정
```

중요:

`-0.131 dBFS`는 gain helper의 limiter ceiling:

```python
MODEL_INPUT_LIMIT = 0.985
```

에 해당.

즉:

```text
+13 dB
→ waveform이 0.985 ceiling에 지속적으로 붙음
→ 심한 clipping/saturation
→ Silero speech probability 붕괴
```

이것이 +13 dB stop의 직접 원인.

결론:

```text
+13 dB 이상 = 사용 금지 영역
```

---

# 19. +11 dB 실측 결과

사용자가:

```bash
./start-local-clova.sh --vad-db 11
```

으로 테스트.

결과:

Silero가 정상적으로 speech를 계속 잡음.

대표값:

```text
p_max = 0.944
above threshold ratio = 0.1875
```

강한 speech 구간:

```text
p ≈ 0.995~0.999
p_mean ≈ 0.72~0.98
p_max ≈ 0.99~1.00
```

실제 preview text:

```text
"삼천 원 작품."
"근데."
"근데 당연히."
```

segment count도 증가:

```text
318 → 319 → 320
```

VAD cycle:

```text
[VAD] start
→ speech probability 상승
→ [VAD] end
→ [VAD RESET] reason=speech_end
→ [SENTENCE QUEUED]
→ [VAD RESET] reason=segment_commit
```

정상 반복 확인.

## +11 dB의 주의점

Peak가 가끔:

```text
-0.131 dBFS
```

에 닿음.

즉 완전히 clipping-free는 아니지만,

- +11 dB에서는 Silero probability가 정상 유지
- +13 dB에서는 지속 saturation으로 probability 붕괴

차이가 분명함.

현재 실측 결론:

```text
VAD +11 dB = 현재 안정 baseline
VAD +12 dB = 공격적 후보
VAD +13 dB = 금지
ASR +6 dB  = 유지
Silero threshold = 0.5 유지
```

threshold를 아직 건드리지 않는 이유:

- gain과 threshold를 동시에 바꾸면 원인 분리가 어려움.
- 현재 +11만으로도 성능이 개선됨.

---

# 20. 웹에서는 왜 잘 됐고 native에서 문제가 생겼나

기존 browser mic 설정:

```js
echoCancellation: false
noiseSuppression: true
autoGainControl: true
```

즉 browser/WebRTC가 microphone input을 그대로 넘긴 것이 아니라:

```text
Mic
 ↓
WebRTC audio processing
 ├─ Noise Suppression
 └─ Auto Gain Control
 ↓
AudioContext
 ↓
Silero
```

형태로 어느 정도 정리한 뒤 전달했음.

native path:

```text
Mic
 ↓
PipeWire
 ↓
pw-record
 ↓
16k PCM
 ↓
fixed VAD gain
 ↓
Silero
```

따라서 browser에서 암묵적으로 해주던 adaptive frontend가 사라짐.

이 때문에:

- 작은 speech는 fixed gain이 필요해짐
- 너무 큰 fixed gain은 clipping 유발
- +11은 sweet spot
- +13은 saturation

으로 나타남.

장기적으로는 fixed gain보다 **adaptive frontend**가 더 적절.

---

# 21. WebRTC/GStreamer adaptive frontend 시도

목표:

```text
lecture_raw.wav untouched
   ↓
WebRTC-like DSP derivative
   ├─ Noise suppression
   ├─ Adaptive digital gain
   ├─ Limiter
   └─ High-pass
   ↓
Silero
```

원래는 Chromium 153 exact WebRTC revision까지 추적하려 했지만,
사용자가 “복잡하게 생각하지 말고 stable한 버전 아무거나 적용”을 선택.

따라서 **Ubuntu에서 안정적으로 쓸 수 있는 GStreamer `webrtcdsp`를 사용**하는 방향으로 단순화.

artifact:

```text
/mnt/data/clova-v8.2-gamma-audio-frontend-hotfix5.zip
```

의도된 실행:

```bash
./start-local-clova.sh --audio-frontend webrtc
```

fallback:

```bash
./start-local-clova.sh --audio-frontend fixed --vad-db 11 --asr-db 6
```

---

# 22. Hotfix 5 설치 실패 — 현재 가장 최신 미해결 버그

사용자가:

```bash
cd ~/Downloads
unzip clova-v8.2-gamma-audio-frontend-hotfix5.zip
cd v82gamma_audio_frontend_hotfix5
./apply-v8.2-gamma-audio-frontend-hotfix5.sh
```

실행.

Docker image build 자체는 성공:

```text
local-clova:rocm-v8-2-gamma-webrtcdsp
```

하지만 마지막 검증에서 실패:

```text
[Local Clova Audio Frontend Hotfix 5] Checking GStreamer webrtcdsp plugin...
No such element or plugin 'webrtcdsp'
```

즉:

```text
GStreamer runtime 설치는 되었을 수 있으나
webrtcdsp element가 실제 image 안에 존재하지 않음
```

현재 이 문제는 **아직 해결되지 않았다.**

중요:

- Hotfix 5를 “적용 성공”으로 간주하면 안 됨.
- WebRTC frontend가 실제로 동작한다고 가정하면 안 됨.
- 다음 세션에서 반드시 plugin packaging / availability부터 확인해야 함.

현재 안전한 fallback은:

```bash
cd ~/clova-note-copy
./start-local-clova.sh --vad-db 11
```

기존 fixed path를 사용하는 것.

---

# 23. 다음 세션에서 Hotfix 5 디버깅할 때 먼저 할 것

우선 현재 image 안에서 plugin/package 상태 확인.

예상 확인 명령:

```bash
docker run --rm \
  local-clova:rocm-v8-2-gamma-webrtcdsp \
  gst-inspect-1.0 --version
```

```bash
docker run --rm \
  local-clova:rocm-v8-2-gamma-webrtcdsp \
  gst-inspect-1.0 webrtcdsp
```

```bash
docker run --rm \
  local-clova:rocm-v8-2-gamma-webrtcdsp \
  bash -lc 'gst-inspect-1.0 | grep -i webrtc || true'
```

패키지 목록:

```bash
docker run --rm \
  local-clova:rocm-v8-2-gamma-webrtcdsp \
  bash -lc 'dpkg -l | grep -E "gstreamer|webrtc|audio-processing"'
```

plugin file 검색:

```bash
docker run --rm \
  local-clova:rocm-v8-2-gamma-webrtcdsp \
  bash -lc 'find /usr/lib -iname "*webrtc*" -o -iname "*dsp*" | head -100'
```

핵심 목표:

1. Ubuntu package build에서 `webrtcdsp`가 실제 포함되는지 확인.
2. 빠져 있다면 다른 stable package/source 선택.
3. Chromium exact clone 같은 복잡한 방향으로 되돌아가지 말 것.
4. 사용자는 **stable/simple**을 원함.

---

# 24. 향후 audio frontend 방향

원하는 최종 구조:

```text
Mic
 ↓
PipeWire / pw-record
 ↓
lecture_raw.wav                  ← authoritative
 ↓
RAW-backed inference cursor
 ↓
Adaptive Audio Frontend
 ├─ NS
 ├─ Adaptive gain
 ├─ Limiter
 └─ clipping guard
 ↓
Silero VAD
 ↓
Adaptive Segmenter
 ↓
Qwen / BatiSay
```

중요:

- hardware/system mic gain을 자동 변경하지 않는 방향이 더 안전.
- RAW가 외부 AGC에 의해 매 순간 레벨이 바뀌는 것은 provenance 관점에서 피하고 싶음.
- 따라서 adaptive digital processing은 derivative에 적용.

---

# 25. telemetry에 앞으로 추가하면 좋은 것

현재 telemetry:

```text
vad_probability
vad_probability_mean_1s
vad_probability_max_1s
vad_probability_above_threshold_ratio_1s
vad_input_rms_dbfs_1s
vad_input_peak_dbfs_1s
vad_reset_count
vad_active
```

추가 권장:

```text
vad_clipped_ratio_1s
vad_samples_at_limit_1s
vad_gain_reduction_db
frontend_mode
frontend_alive
frontend_fallback_reason
```

특히 `clipped_ratio`는 +11/+12/+13 경계 판단에 매우 중요.

예:

```text
[VAD HEALTH]
gain=11dB
rms=-1.8dBFS
peak=-0.13dBFS
clipped_ratio=2.1%
p_mean=0.72
p_max=0.999
```

vs

```text
gain=13dB
peak=-0.13dBFS
clipped_ratio=30%
p_max≈0.005
```

---

# 26. Adaptive Segmenter — 현재 유지해야 할 기존 동작

현재 backend V6.4 계열 Adaptive Segmenter를 V8.x가 계승.

Silero base silence:

```text
VAD_BASE_SILENCE_MS = 450
```

Adaptive thresholds:

```text
ADAPTIVE_SHORT_SILENCE_MS  = 1500
ADAPTIVE_MEDIUM_SILENCE_MS = 1000
ADAPTIVE_TARGET_SILENCE_MS = 600
ADAPTIVE_LARGE_SILENCE_MS  = 500
```

sentence-ending hint는 약 650ms까지 낮출 수 있지만 단독으로 boundary를 만들지는 않음.

```text
MAX_SENTENCE_SEC = 28.0
```

흐름:

```text
speech_end
→ adaptive_silence_active=true
→ silence duration accumulate
→ speech resumes: candidate cancel
→ threshold 넘으면 enqueue_sentence()
→ segment WAV save
→ BatiSay queue
→ _reset_live_sentence_state()
```

이 로직은 현재 정상 동작이 확인되었으므로 **audio frontend 수정 중 건드리지 말 것.**

---

# 27. word_audio_map / 학습 데이터 invariant

V7.9.3부터 유지해야 할 중요한 규칙:

- 하나의 original WAV 보존.
- token index/text/start/end refs.
- correction은 original token span을 source audio에 매핑.
- insertion은 utterance-only training.
- delete는 phrase target 없음.
- N→M replacement는 original N-token span crop + corrected M target.

이 부분은 V8.2 audio frontend와 무관하며 손대지 말 것.

---

# 28. 현재 artifacts 목록

중요 artifact:

```text
/mnt/data/clova-v8.2-alpha-bundle.zip
/mnt/data/clova-v8.2-alpha-permission-hotfix.zip
/mnt/data/clova-v8.2-alpha-hotfix2.zip
/mnt/data/clova-v8.2-alpha-hotfix3.zip
/mnt/data/clova-v8.2-beta-bundle.zip
/mnt/data/clova-v8.2-beta-ui-hotfix1.zip
/mnt/data/clova-v8.2-gamma-bundle.zip
/mnt/data/clova-v8.2-gamma-gain-hotfix1.zip
/mnt/data/clova-v8.2-gamma-resume-hotfix2.zip
/mnt/data/clova-v8.2-gamma-vad-hotfix3.zip
/mnt/data/clova-v8.2-gamma-vad-cli-hotfix4.zip
/mnt/data/clova-v8.2-gamma-audio-frontend-hotfix5.zip
```

Hotfix 5는 **plugin check 실패 상태**.

---

# 29. 다음 큰 로드맵

현재 위치:

```text
V8.2-gamma
   ↓
[Audio/VAD stabilization]   ← 현재
   ├─ native capture         ✅
   ├─ RAW-backed inference   ✅
   ├─ UI lag fix             ✅
   ├─ resume reconcile       ✅
   ├─ Silero telemetry       ✅
   ├─ speech_end reset       ✅
   ├─ VAD gain separation    ✅
   ├─ +11 dB baseline        ✅
   ├─ +13 saturation rootcause ✅
   └─ adaptive frontend      ⏳ Hotfix5 실패, 미완성
   ↓
V8.2-delta
   ↓
V8.2-eta / VibeVoice
   ↓
V8.2-final Core API
   ↓
V8.3 Native UI
```

---

# 30. V8.2-delta에서 할 일

Audio frontend가 안정화된 뒤에만 진행.

목표:

```text
asr/engines/qwen3_asr.py
asr/engines/batisay.py
asr/engines/professor_lora.py
```

으로 실제 production execution을 adapter화.

현재 gamma는 interface-only:

```text
migration_phase: interface_only
production_execution: legacy_direct_until_v8.2-delta
```

Delta에서 주의:

- native capture 변경 금지
- RAW-backed inference 변경 금지
- Adaptive Segmenter 변경 금지
- UI lag hotfix 보존
- VAD telemetry 보존
- gain/provenance 보존
- Professor/subject separation 보존
- Qwen3.8 postprocess 부활 금지

---

# 31. VibeVoice 계획

Delta 이후 adapter layer가 안정되면 VibeVoice를 별도 adapter로 추가.

원칙:

- BatiSay committed를 즉시 제거하지 않음.
- VibeVoice는 새 engine/profile slot으로 A/B.
- AMD ROCm/gfx1151 support risk가 있으므로 capture 안정화보다 우선하지 않음.

---

# 32. V8.3 Native UI 계획

최종 방향:

```text
local-clova-ui (Qt 6 / QML)
      │ Unix socket
      ▼
local-clova-core (Rust/C++)
├─ PipeWire
├─ recording_time
├─ sessions/timeline/playback/storage
│
├─ asr-qwen Python
├─ asr-vibevoice Python
└─ asr-batisay Python
```

목표:

```text
Chrome dependency = 0
WebAudio = 0
DOM = 0
JS capture = 0
```

단계:

1. Native Shell
2. Native PDF
3. Native Annotation
4. Timeline Integration
5. Native Playback
6. Web-Free final

---

# 33. 현재 권장 운영법

Hotfix 5가 실패한 상태에서는 adaptive frontend를 억지로 사용하지 말 것.

안전한 baseline:

```bash
cd ~/clova-note-copy
./start-local-clova.sh --vad-db 11
```

확인 포인트:

- RAW bytes 증가
- `recording_samples` 증가
- `capture_stalled=false`
- `inference_backlog_sec`가 작음
- `segment_count` 증가
- VAD probability가 speech에서 충분히 상승

VAD debug:

```bash
docker logs -f local-clova-v8-2-gamma 2>&1 \
  | grep -E '\[VAD CONFIG\]|\[VAD HEALTH\]|\[VAD RESET\]|\[VAD\]|\[SENTENCE QUEUED\]'
```

---

# 34. 반드시 기억할 디버깅 교훈

## 34.1 “녹음 중” UI만 믿지 말 것

반드시 확인:

```text
RAW bytes
recording_samples
capture_last_pcm_age_sec
inference_cursor_sample
inference_backlog_sec
```

## 34.2 RAW가 계속 커진다고 speech가 정상인 것은 아님

실제로 VAD saturation 때:

- RAW 정상
- inference 정상
- HTTP 정상
- VAD probability만 붕괴

였음.

## 34.3 gain은 클수록 좋은 것이 아님

```text
+11 dB = 좋은 sensitivity
+13 dB = clipping → Silero collapse
```

## 34.4 raw와 derivative를 분리할 것

다음 기능들은 derivative에만:

- gain
- AGC
- noise suppression
- limiter
- DeepFilter

RAW는 canonical source.

## 34.5 한 번에 하나의 변수만 바꿀 것

예:

- gain을 바꾸는 테스트 중 threshold까지 같이 바꾸지 않음.
- frontend를 바꾸는 테스트 중 segmenter를 바꾸지 않음.

---

# 35. 다음 세션에서 가장 먼저 해야 할 일

우선순위:

```text
1. Hotfix 5의 `webrtcdsp` plugin 부재 원인 확인
2. 복잡한 Chromium exact clone은 피하고 stable/simple frontend 선택
3. fixed +11 dB fallback을 항상 유지
4. adaptive frontend가 실제 동작하면 30~60분 drill
5. VAD clipping ratio telemetry 추가
6. 장시간 안정성 PASS 후 V8.2-delta
```

가장 중요한 것:

> **지금은 audio frontend가 마지막 미완성 안정화 영역이다.**

Delta로 넘어가기 전에 이 부분만 닫으면 된다.

---

# 36. 한 줄 핸드오프

다음 세션/LLM은 이렇게 이해하면 된다:

> Local Clova V8.2-gamma는 native PipeWire capture + RAW-backed inference까지 안정화되었고, 장시간 textbox stop의 핵심 원인은 Silero 앞 fixed VAD gain에서 +13 dB saturation이었으며 +11 dB는 안정 baseline으로 검증됐다. Silero 6.2.1 telemetry와 speech_end reset도 추가됐다. 지금 남은 일은 browser WebRTC가 해주던 adaptive audio frontend를 stable/simple한 방식으로 derivative path에 넣는 것이고, 시도한 GStreamer `webrtcdsp` Hotfix 5는 Docker build 후 `No such element or plugin 'webrtcdsp'`로 실패했다. 이 문제를 해결한 뒤 30~60분 drill → V8.2-delta ASR adapter migration으로 진행한다.

