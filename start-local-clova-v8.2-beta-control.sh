#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Local Clova V8.2-beta Control Launcher
#
# Starts:
#   1) Host control + native PipeWire capture controller :8765
#   2) Local Clova ROCm Docker backend/web UI           :8000
#
# V8.2-beta removes browser microphone capture. Chrome only
# controls the session/UI; pw-record on the HOST captures PCM.
# ============================================================

VERSION="v8.2-beta-control"
CLOVA_DIR="$HOME/clova-note-copy"
RUNTIME_DIR="$CLOVA_DIR/.runtime-v8.2-beta"
IMAGE="${CLOVA_V8_2_BETA_IMAGE:-local-clova:rocm-v8-2-beta}"
CONTAINER="local-clova-v8-2-beta"
LOG_DIR="$CLOVA_DIR/logs"
CLOVA_LOG="$LOG_DIR/local-clova-v8-2-beta.log"
CONTROL_PORT="8765"
CONTROL_SCRIPT="$CLOVA_DIR/clova_host_control_v8_2_beta.py"
CONTROL_LOG="$LOG_DIR/clova-host-control-v8-2-beta.log"
CONTROL_PID_FILE="$LOG_DIR/clova-host-control-v8-2-beta.pid"
TOKEN_FILE="$RUNTIME_DIR/clova-control-token"
mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

info(){ printf '\n\033[1;36m[Local Clova]\033[0m %s\n' "$*"; }
warn(){ printf '\n\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\n\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

web_ready(){ curl -fsS --max-time 2 http://127.0.0.1:8000/ >/dev/null 2>&1; }
control_body(){ curl -fsS --max-time 2 http://127.0.0.1:${CONTROL_PORT}/health 2>/dev/null || true; }
control_ready(){ local body; body="$(control_body)"; [[ "$body" == *'"version": "v8.2-beta-control"'* ]] || [[ "$body" == *'"version":"v8.2-beta-control"'* ]]; }

command -v docker >/dev/null 2>&1 || fail "docker not found"
command -v curl >/dev/null 2>&1 || fail "curl not found"
command -v python3 >/dev/null 2>&1 || fail "python3 not found"
command -v pw-record >/dev/null 2>&1 || fail "pw-record not found (PipeWire tools are required for V8.2-beta)"
[[ -d "$CLOVA_DIR" ]] || fail "Clova directory missing: $CLOVA_DIR"
[[ -f "$CLOVA_DIR/run_clova_v8_2_beta.py" ]] || fail "Missing V8.2-beta backend"
[[ -f "$CLOVA_DIR/native_audio_daemon_v8_2_beta.py" ]] || fail "Missing V8.2-beta native audio daemon"
[[ -f "$CONTROL_SCRIPT" ]] || fail "Missing V8.2-beta host controller"
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
  info "Starting V8.2-beta host/native-capture controller..."
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
  info "Starting Local Clova V8.2-beta container..."
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
    -e DENOISE_BIN="/workspace/tools/deep-filter" \
    -e STT_AUDIO_SOURCE_DEFAULT="raw" \
    -e DENOISE_ENABLED="1" -e DENOISE_TIMEOUT_SEC="90" \
    -e DENOISE_POST_FILTER="1" -e DENOISE_PF_BETA="0.04" -e DENOISE_ATTEN_LIM_DB="100" \
    -e LORA_MIN_SAMPLES="12" -e LORA_MIN_NEW_SAMPLES="8" \
    -e LORA_TRAIN_EPOCHS="1" -e LORA_TRAIN_MAX_STEPS="240" -e LORA_TRAIN_LR="1e-4" \
    "$IMAGE" bash -lc 'cd /workspace && exec python3 /workspace/run_clova_v8_2_beta.py' >/dev/null
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

info "Local Clova V8.2-beta ready"
cat <<EOF

============================================================
 Local Clova V8.2-beta · RAW-backed Inference Separation
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
 Master clock: native PipeWire captured samples / 16000.
 Inference: independent cursor re-reads durable PCM from lecture_raw.wav.
 Test stall : CLOVA_TEST_ASR_STALL_SEC=${CLOVA_TEST_ASR_STALL_SEC:-0} (0 = disabled).
============================================================
EOF
