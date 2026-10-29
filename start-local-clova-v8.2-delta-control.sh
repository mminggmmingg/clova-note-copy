#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Local Clova V8.2-delta-3 Control Launcher
#
# Starts:
#   1) Host control + native PipeWire capture controller :8765
#   2) Local Clova ROCm Docker backend/web UI           :8000
#
# V8.2-delta-3 freezes the stable gamma audio path and routes Qwen preview, BatiSay committed recognition, and Professor LoRA adaptation through ASR adapters. Chrome only
# controls the session/UI; pw-record on the HOST captures PCM.
# ============================================================

VERSION="v8.2-delta-control"
CLOVA_DIR="$HOME/clova-note-copy"
RUNTIME_DIR="$CLOVA_DIR/.runtime-v8.2-delta"
IMAGE="${CLOVA_V8_2_DELTA_IMAGE:-local-clova:rocm-v8-2-gamma-hotfix6}"
CONTAINER="local-clova-v8-2-delta"
LOG_DIR="$CLOVA_DIR/logs"
CLOVA_LOG="$LOG_DIR/local-clova-v8-2-delta.log"
CONTROL_PORT="8765"
CONTROL_SCRIPT="$CLOVA_DIR/clova_host_control_v8_2_delta.py"
CONTROL_LOG="$LOG_DIR/clova-host-control-v8-2-delta.log"
CONTROL_PID_FILE="$LOG_DIR/clova-host-control-v8-2-delta.pid"
TOKEN_FILE="$RUNTIME_DIR/clova-control-token"
mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

info(){ printf '\n\033[1;36m[Local Clova]\033[0m %s\n' "$*"; }
warn(){ printf '\n\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\n\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

usage(){
  cat <<'EOF'
Usage:
  ./start-local-clova.sh [options]

Options:
  --audio-frontend <mode>  webrtc (default) or fixed
  --vad-db <dB>            Extra Silero gain after frontend. Default: 0
  --vad-gain-db <dB>       Alias for --vad-db
  --asr-db <dB>            Extra Qwen/BatiSay gain. WebRTC default: 0
  -h, --help               Show this help and exit

Examples:
  ./start-local-clova.sh
  ./start-local-clova.sh --audio-frontend fixed --vad-db 11 --asr-db 6

Notes:
  - New recordings use 16 kHz stereo authoritative lecture_raw.wav.
  - WebRTC mode processes stereo first, then downmixes to mono for VAD/ASR.
  - WebRTC defaults to VAD 0 dB / ASR 0 dB; AGC2 handles level adaptation.
  - fixed +11/+6 remains the known-good fallback/control.
  - Existing mono lecture_raw.wav sessions resume in mono without conversion.
EOF
}

# CLI value overrides the environment variable.
AUDIO_FRONTEND="${AUDIO_FRONTEND:-webrtc}"
VAD_INPUT_GAIN_DB="${VAD_INPUT_GAIN_DB:-0.0}"
ASR_INPUT_GAIN_DB="${MODEL_INPUT_GAIN_DB:-}"
while (($#)); do
  case "$1" in
    --audio-frontend)
      (($# >= 2)) || fail "$1 requires webrtc or fixed"
      AUDIO_FRONTEND="$2"; shift 2 ;;
    --audio-frontend=*)
      AUDIO_FRONTEND="${1#*=}"; shift ;;
    --vad-db|--vad-gain-db)
      (($# >= 2)) || fail "$1 requires a dB value"
      VAD_INPUT_GAIN_DB="$2"; shift 2 ;;
    --vad-db=*|--vad-gain-db=*)
      VAD_INPUT_GAIN_DB="${1#*=}"; shift ;;
    --asr-db)
      (($# >= 2)) || fail "$1 requires a dB value"
      ASR_INPUT_GAIN_DB="$2"; shift 2 ;;
    --asr-db=*)
      ASR_INPUT_GAIN_DB="${1#*=}"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      fail "unknown option: $1 (use --help)" ;;
  esac
done

case "$AUDIO_FRONTEND" in
  webrtc|fixed) ;;
  *) fail "--audio-frontend must be webrtc or fixed" ;;
esac

if [[ -z "$ASR_INPUT_GAIN_DB" ]]; then
  if [[ "$AUDIO_FRONTEND" == "webrtc" ]]; then ASR_INPUT_GAIN_DB="0.0"; else ASR_INPUT_GAIN_DB="6.0"; fi
fi

python3 - "$VAD_INPUT_GAIN_DB" "$ASR_INPUT_GAIN_DB" <<'PY' >/dev/null || fail "invalid gain value"
import math, sys
for raw in sys.argv[1:]:
    try:
        x = float(raw)
    except Exception:
        raise SystemExit(1)
    if not math.isfinite(x) or x < -30.0 or x > 30.0:
        raise SystemExit(1)
PY

web_ready(){ curl -fsS --max-time 2 http://127.0.0.1:8000/ >/dev/null 2>&1; }
control_body(){ curl -fsS --max-time 2 http://127.0.0.1:${CONTROL_PORT}/health 2>/dev/null || true; }
control_ready(){ local body; body="$(control_body)"; [[ "$body" == *'"version": "v8.2-delta-control"'* ]] || [[ "$body" == *'"version":"v8.2-delta-control"'* ]]; }

command -v docker >/dev/null 2>&1 || fail "docker not found"
command -v curl >/dev/null 2>&1 || fail "curl not found"
command -v python3 >/dev/null 2>&1 || fail "python3 not found"
command -v pw-record >/dev/null 2>&1 || fail "pw-record not found (PipeWire tools are required for V8.2-delta)"
[[ -d "$CLOVA_DIR" ]] || fail "Clova directory missing: $CLOVA_DIR"
[[ -f "$CLOVA_DIR/run_clova_v8_2_delta.py" ]] || fail "Missing V8.2-delta backend"
[[ -f "$CLOVA_DIR/native_audio_daemon_v8_2_beta.py" ]] || fail "Missing V8.2-beta native audio daemon"
[[ -f "$CONTROL_SCRIPT" ]] || fail "Missing V8.2-delta host controller"
[[ -f "$CLOVA_DIR/professor_lora_v7_9.py" ]] || fail "Missing V7.9 LoRA trainer"
[[ -f "$CLOVA_DIR/batisay-ko-large/config.json" ]] || fail "BatiSay model missing"
[[ -f "$CLOVA_DIR/batisay-ko-large/model.safetensors.index.json" ]] || fail "BatiSay index missing"
[[ -f "$CLOVA_DIR/batisay-ko-large/model-00001-of-00002.safetensors" ]] || fail "BatiSay shard 1 missing"
[[ -f "$CLOVA_DIR/batisay-ko-large/model-00002-of-00002.safetensors" ]] || fail "BatiSay shard 2 missing"
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "Docker image '$IMAGE' is missing. Keep/build the V8.1-alpha.1 image first."

if [[ ! -s "$TOKEN_FILE" ]]; then
  python3 - <<'PY' > "$TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(32))
PY
  chmod 600 "$TOKEN_FILE"
fi
CONTROL_TOKEN="$(cat "$TOKEN_FILE")"

# A stale controller from another Local Clova version would own :8765.
if ! control_ready; then
  existing="$(control_body)"
  if [[ -n "$existing" ]]; then
    fail "Port :${CONTROL_PORT} is already owned by another controller. Stop the previous Local Clova stack first."
  fi
fi

if control_ready; then
  info "Host/native-capture controller already running on :${CONTROL_PORT}"
else
  if [[ -s "$CONTROL_PID_FILE" ]]; then
    OLD="$(cat "$CONTROL_PID_FILE" 2>/dev/null || true)"
    if [[ "$OLD" =~ ^[0-9]+$ ]] && kill -0 "$OLD" 2>/dev/null; then
      kill "$OLD" 2>/dev/null || true
      sleep .4
    fi
  fi
  info "Starting V8.2-delta host/native-capture controller..."
  nohup env CLOVA_AUDIO_TARGET="${CLOVA_AUDIO_TARGET:-}" \
    CLOVA_TEST_ASR_STALL_SEC="${CLOVA_TEST_ASR_STALL_SEC:-0}" \
    CLOVA_TEST_ASR_STALL_AFTER_SEC="${CLOVA_TEST_ASR_STALL_AFTER_SEC:-5}" \
    python3 "$CONTROL_SCRIPT" \
      --project "$CLOVA_DIR" \
      --token-file "$TOKEN_FILE" \
      --container "$CONTAINER" \
      --port "$CONTROL_PORT" \
      >"$CONTROL_LOG" 2>&1 &
  echo $! > "$CONTROL_PID_FILE"
  for _ in $(seq 1 50); do control_ready && break; sleep .2; done
  control_ready || { tail -n 100 "$CONTROL_LOG" >&2 || true; fail "Host/native-capture controller failed"; }
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  info "Clova container already running: $CONTAINER"
else
  docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" && docker rm -f "$CONTAINER" >/dev/null
  info "Starting Local Clova V8.2-delta container..."
  RENDER_GID="$(getent group render 2>/dev/null | cut -d: -f3 || true)"
  VIDEO_GID="$(getent group video 2>/dev/null | cut -d: -f3 || true)"
  docker run -d \
    --name "$CONTAINER" \
    --device=/dev/kfd --device=/dev/dri \
    --group-add "${VIDEO_GID:-44}" --group-add "${RENDER_GID:-992}" \
    --ipc=host --shm-size 16G --security-opt seccomp=unconfined \
    --add-host=host.docker.internal:host-gateway \
    -v "$CLOVA_DIR:/workspace" -p 8000:8000 \
    -e HOST_CONTROL_URL="http://host.docker.internal:${CONTROL_PORT}" \
    -e CLOVA_CONTROL_TOKEN="$CONTROL_TOKEN" \
    -e NATIVE_CAPTURE_TIMEOUT_SEC="8" \
    -e AUDIO_FRONTEND="$AUDIO_FRONTEND" \
    -e AUDIO_FRONTEND_SAVE_DERIVATIVE="${AUDIO_FRONTEND_SAVE_DERIVATIVE:-1}" \
    -e AUDIO_FRONTEND_FALLBACK_VAD_DB="11.0" \
    -e AUDIO_FRONTEND_FALLBACK_ASR_DB="6.0" \
    -e MODEL_INPUT_GAIN_DB="$ASR_INPUT_GAIN_DB" \
    -e VAD_INPUT_GAIN_DB="$VAD_INPUT_GAIN_DB" \
    -e VAD_RESET_ON_SPEECH_END="${VAD_RESET_ON_SPEECH_END:-1}" \
    -e VAD_TELEMETRY_ENABLED="${VAD_TELEMETRY_ENABLED:-1}" \
    -e DENOISE_BIN="/workspace/tools/deep-filter" \
    -e STT_AUDIO_SOURCE_DEFAULT="raw" \
    -e DENOISE_ENABLED="1" -e DENOISE_TIMEOUT_SEC="90" \
    -e DENOISE_POST_FILTER="1" -e DENOISE_PF_BETA="0.04" -e DENOISE_ATTEN_LIM_DB="100" \
    -e LORA_MIN_SAMPLES="12" -e LORA_MIN_NEW_SAMPLES="8" \
    -e LORA_TRAIN_EPOCHS="1" -e LORA_TRAIN_MAX_STEPS="240" -e LORA_TRAIN_LR="1e-4" \
    "$IMAGE" bash -lc 'cd /workspace && exec python3 /workspace/run_clova_v8_2_delta.py' >/dev/null
fi

info "Waiting for web server on :8000..."
for _ in $(seq 1 240); do
  web_ready && break
  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    docker logs --tail 200 "$CONTAINER" >&2 || true
    fail "Clova container exited during startup"
  fi
  sleep 1
done
web_ready || { docker logs --tail 200 "$CONTAINER" >&2 || true; fail "Web server did not become ready"; }
docker logs "$CONTAINER" > "$CLOVA_LOG" 2>&1 || true
SILERO_VAD_VERSION="$(docker exec -i "$CONTAINER" python3 - <<'PY' 2>/dev/null || true
import importlib.metadata
try:
    print(importlib.metadata.version("silero-vad"))
except Exception:
    print("unknown")
PY
)"
SILERO_VAD_VERSION="${SILERO_VAD_VERSION:-unknown}"

info "Local Clova V8.2-delta-3 ready"
cat <<EOF

============================================================
 Local Clova V8.2-delta-3 · Full ASR + Adaptation Migration
============================================================
 Web UI       : http://127.0.0.1:8000
 Container    : $CONTAINER
 Docker image : $IMAGE
 Capture      : HOST PipeWire/pw-record (browser microphone OFF)
 Audio target : ${CLOVA_AUDIO_TARGET:-default PipeWire source}
 Qwen3.8      : REMOVED (no :8083 server)
 Backend log  : docker logs -f $CONTAINER
 Control log  : $CONTROL_LOG

 Invariant: Chrome/PDF/annotation/ASR stalls must not stop lecture_raw.wav capture.
 Master clock: native PipeWire audio frames / 16000.
 Inference: independent cursor re-reads durable PCM from lecture_raw.wav.
 ASR layer : Qwen preview=adapter · BatiSay committed=adapter · Professor LoRA=adapter.
 Frontend   : ${AUDIO_FRONTEND} · stereo RAW=2ch on new sessions
 VAD gain   : ${VAD_INPUT_GAIN_DB} dB · ASR gain: ${ASR_INPUT_GAIN_DB} dB
 Silero VAD : ${SILERO_VAD_VERSION} · reset_on_speech_end=${VAD_RESET_ON_SPEECH_END:-1} · telemetry=${VAD_TELEMETRY_ENABLED:-1}
 Test stall : CLOVA_TEST_ASR_STALL_SEC=${CLOVA_TEST_ASR_STALL_SEC:-0} (0 = disabled).
============================================================
EOF
