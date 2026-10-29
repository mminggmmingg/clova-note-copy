#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Local Clova V8.2-epsilon Whisper Single-ASR Launcher
#
# Starts:
#   1) Host control + native PipeWire capture controller :8765
#   2) Local Clova ROCm Docker backend/web UI           :8000
#
# V8.2-gamma keeps V8.2-beta native capture and adds the ASR plugin interface. Chrome only
# controls the session/UI; pw-record on the HOST captures PCM.
# ============================================================

VERSION="v8.2-epsilon-whisper"
CLOVA_DIR="$HOME/clova-note-copy"
RUNTIME_DIR="$CLOVA_DIR/.runtime-v8.2-epsilon"
IMAGE="${CLOVA_V8_2_EPSILON_IMAGE:-local-clova:rocm-v8-2-gamma-hotfix6}"
CONTAINER="local-clova-v8-2-epsilon"
LOG_DIR="$CLOVA_DIR/logs"
CLOVA_LOG="$LOG_DIR/local-clova-v8-2-epsilon.log"
CONTROL_PORT="8765"
CONTROL_SCRIPT="$CLOVA_DIR/clova_host_control_v8_2_gamma.py"
CONTROL_LOG="$LOG_DIR/clova-host-control-v8-2-gamma.log"
CONTROL_PID_FILE="$LOG_DIR/clova-host-control-v8-2-gamma.pid"
TOKEN_FILE="$RUNTIME_DIR/clova-control-token"
WHISPER_PORT="${WHISPER_PORT:-8178}"
WHISPER_CPP_DIR="$CLOVA_DIR/external/whisper.cpp"
WHISPER_SERVER_BIN="$WHISPER_CPP_DIR/build/bin/whisper-server"
WHISPER_MODEL="$CLOVA_DIR/models/whispercpp/ggml-large-v3.bin"
WHISPER_LOG="$LOG_DIR/whisper-large-v3-server.log"
WHISPER_PID_FILE="$LOG_DIR/whisper-large-v3-server.pid"
mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

info(){ printf '\n\033[1;36m[Local Clova]\033[0m %s\n' "$*"; }
warn(){ printf '\n\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\n\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

usage(){
  cat <<'EOF'
Usage:
  ./start-local-clova.sh [options]

Options:
  --vad-db <dB>          Set Silero VAD input gain in dB. Default: 0
  --vad-db=<dB>          Same as above
  --vad-gain-db <dB>     Alias for --vad-db
  -h, --help             Show this help and exit

Examples:
  ./start-local-clova.sh
  ./start-local-clova.sh --vad-db 3
  ./start-local-clova.sh --vad-db 6
  ./start-local-clova.sh --vad-db -3

Notes:
  - This changes only the Silero VAD input gain.
  - Whisper Large-v3 is the only production ASR.
  - lecture_raw.wav remains untouched.
EOF
}

# CLI value overrides the environment variable.
VAD_INPUT_GAIN_DB="${VAD_INPUT_GAIN_DB:-0.0}"
while (($#)); do
  case "$1" in
    --vad-db|--vad-gain-db)
      (($# >= 2)) || fail "$1 requires a dB value"
      VAD_INPUT_GAIN_DB="$2"
      shift 2
      ;;
    --vad-db=*|--vad-gain-db=*)
      VAD_INPUT_GAIN_DB="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1 (use --help)"
      ;;
  esac
done

python3 - "$VAD_INPUT_GAIN_DB" <<'PY' >/dev/null || fail "invalid --vad-db value: $VAD_INPUT_GAIN_DB"
import math, sys
try:
    x = float(sys.argv[1])
except Exception:
    raise SystemExit(1)
if not math.isfinite(x) or x < -30.0 or x > 30.0:
    raise SystemExit(1)
PY

web_ready(){ curl -fsS --max-time 2 http://127.0.0.1:8000/ >/dev/null 2>&1; }
control_body(){ curl -fsS --max-time 2 http://${BRIDGE_IP}:${CONTROL_PORT}/health 2>/dev/null || true; }
control_ready(){ local body; body="$(control_body)"; [[ "$body" == *'"version": "v8.2-gamma-control"'* ]] || [[ "$body" == *'"version":"v8.2-gamma-control"'* ]]; }
whisper_ready(){ curl -fsS --max-time 2 "http://${BRIDGE_IP}:${WHISPER_PORT}/" >/dev/null 2>&1; }
listen_addrs(){ ss -ltnH "sport = :$1" 2>/dev/null | awk '{print $4}' | sort -u | paste -sd' '; }

command -v docker >/dev/null 2>&1 || fail "docker not found"
command -v curl >/dev/null 2>&1 || fail "curl not found"
command -v python3 >/dev/null 2>&1 || fail "python3 not found"
command -v ss >/dev/null 2>&1 || fail "ss not found (iproute2)"
command -v pw-record >/dev/null 2>&1 || fail "pw-record not found (PipeWire tools are required for V8.2-gamma)"

# Single-laptop use: nothing listens on the LAN. The web UI is published on
# 127.0.0.1 only; the host controller and whisper-server listen on the Docker
# bridge gateway, which the container reaches as host.docker.internal.
BRIDGE_IP="$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)"
[[ "$BRIDGE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "could not determine the Docker bridge gateway IP"

# An instance started by an older launcher listens on 0.0.0.0. Reusing it would
# keep the LAN exposure, and killing it could cut a live recording, so stop here.
for port in "$CONTROL_PORT" "$WHISPER_PORT"; do
  addrs="$(listen_addrs "$port")"
  if [[ -n "$addrs" && "$addrs" != "${BRIDGE_IP}:${port}" ]]; then
    fail "Port :${port} is listening on '${addrs}' (older launcher). Shut down Local Clova from the app (or stop that process), then start again."
  fi
done
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  published="$(docker port "$CONTAINER" 8000/tcp 2>/dev/null | sort -u | paste -sd' ')"
  if [[ "$published" != "127.0.0.1:8000" ]]; then
    fail "Container $CONTAINER publishes :8000 on '${published}' (older launcher). Shut down Local Clova from the app, then start again."
  fi
fi
[[ -d "$CLOVA_DIR" ]] || fail "Clova directory missing: $CLOVA_DIR"
[[ -f "$CLOVA_DIR/run_clova_v8_2_gamma.py" ]] || fail "Missing V8.2-gamma backend"
[[ -f "$CLOVA_DIR/native_audio_daemon_v8_2_beta.py" ]] || fail "Missing V8.2-beta native audio daemon"
[[ -f "$CONTROL_SCRIPT" ]] || fail "Missing V8.2-gamma host controller"
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "Docker image '$IMAGE' is missing. Keep/build the V8.1-alpha.1 image first."
[[ -f "$WHISPER_MODEL" ]] || fail "Whisper Large-v3 model missing: $WHISPER_MODEL"
if [[ ! -x "$WHISPER_SERVER_BIN" ]]; then
  [[ -d "$WHISPER_CPP_DIR/build" ]] || fail "whisper.cpp build directory missing: $WHISPER_CPP_DIR/build"
  info "Building whisper-server target..."
  cmake --build "$WHISPER_CPP_DIR/build" --target whisper-server -j"$(nproc)" || fail "whisper-server build failed"
fi
[[ -x "$WHISPER_SERVER_BIN" ]] || fail "whisper-server binary missing: $WHISPER_SERVER_BIN"

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
  info "Starting V8.2-gamma host/native-capture controller..."
  nohup env CLOVA_AUDIO_TARGET="${CLOVA_AUDIO_TARGET:-}" \
    CLOVA_TEST_ASR_STALL_SEC="${CLOVA_TEST_ASR_STALL_SEC:-0}" \
    CLOVA_TEST_ASR_STALL_AFTER_SEC="${CLOVA_TEST_ASR_STALL_AFTER_SEC:-5}" \
    python3 "$CONTROL_SCRIPT" \
      --project "$CLOVA_DIR" \
      --token-file "$TOKEN_FILE" \
      --container "$CONTAINER" \
      --host "$BRIDGE_IP" \
      --port "$CONTROL_PORT" \
      >"$CONTROL_LOG" 2>&1 &
  echo $! > "$CONTROL_PID_FILE"
  for _ in $(seq 1 50); do control_ready && break; sleep .2; done
  control_ready || { tail -n 100 "$CONTROL_LOG" >&2 || true; fail "Host/native-capture controller failed"; }
fi

# Persistent whisper.cpp server: model is loaded once and every SEG request is
# independent (--no-context), preventing the long-form repetition loop seen in
# the 90-minute whole-file stress test.
if whisper_ready; then
  info "Whisper Large-v3 server already running on :${WHISPER_PORT}"
else
  if [[ -s "$WHISPER_PID_FILE" ]]; then
    OLD="$(cat "$WHISPER_PID_FILE" 2>/dev/null || true)"
    if [[ "$OLD" =~ ^[0-9]+$ ]] && kill -0 "$OLD" 2>/dev/null; then
      kill "$OLD" 2>/dev/null || true
      sleep .5
    fi
  fi
  info "Starting Whisper Large-v3 FP16 / whisper.cpp HIP server..."
  nohup "$WHISPER_SERVER_BIN" \
    -m "$WHISPER_MODEL" \
    -l ko -mc 0 -fa -bs 5 -bo 5 -t 4 \
    --host "$BRIDGE_IP" --port "$WHISPER_PORT" \
    >"$WHISPER_LOG" 2>&1 &
  echo $! > "$WHISPER_PID_FILE"
  for _ in $(seq 1 120); do whisper_ready && break; sleep .5; done
  whisper_ready || { tail -n 120 "$WHISPER_LOG" >&2 || true; fail "Whisper server failed"; }
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  info "Clova container already running: $CONTAINER"
else
  docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" && docker rm -f "$CONTAINER" >/dev/null
  info "Starting Local Clova V8.2-gamma container..."
  RENDER_GID="$(getent group render 2>/dev/null | cut -d: -f3 || true)"
  VIDEO_GID="$(getent group video 2>/dev/null | cut -d: -f3 || true)"
  docker run -d \
    --name "$CONTAINER" \
    --device=/dev/kfd --device=/dev/dri \
    --group-add "${VIDEO_GID:-44}" --group-add "${RENDER_GID:-992}" \
    --ipc=host --shm-size 16G --security-opt seccomp=unconfined \
    --add-host=host.docker.internal:"$BRIDGE_IP" \
    -v "$CLOVA_DIR:/workspace" -p 127.0.0.1:8000:8000 \
    -e HOST_CONTROL_URL="http://host.docker.internal:${CONTROL_PORT}" \
    -e CLOVA_CONTROL_TOKEN="$CONTROL_TOKEN" \
    -e NATIVE_CAPTURE_TIMEOUT_SEC="8" \
    -e MODEL_INPUT_GAIN_DB="0.0" \
    -e WHISPER_SERVER_URL="http://host.docker.internal:${WHISPER_PORT}" \
    -e WHISPER_TIMEOUT_SEC="120" \
    -e VAD_INPUT_GAIN_DB="$VAD_INPUT_GAIN_DB" \
    -e VAD_RESET_ON_SPEECH_END="${VAD_RESET_ON_SPEECH_END:-1}" \
    -e VAD_TELEMETRY_ENABLED="${VAD_TELEMETRY_ENABLED:-1}" \
    -e DENOISE_BIN="/workspace/tools/deep-filter" \
    -e STT_AUDIO_SOURCE_DEFAULT="raw" \
    -e DENOISE_ENABLED="0" -e DENOISE_TIMEOUT_SEC="90" \
    -e DENOISE_POST_FILTER="1" -e DENOISE_PF_BETA="0.04" -e DENOISE_ATTEN_LIM_DB="100" \
    -e LORA_MIN_SAMPLES="12" -e LORA_MIN_NEW_SAMPLES="8" \
    -e LORA_TRAIN_EPOCHS="1" -e LORA_TRAIN_MAX_STEPS="240" -e LORA_TRAIN_LR="1e-4" \
    "$IMAGE" bash -lc 'cd /workspace && exec python3 /workspace/run_clova_v8_2_gamma.py' >/dev/null
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

info "Local Clova V8.2-gamma ready"
cat <<EOF

============================================================
 Local Clova V8.2-epsilon · Whisper Single-ASR
============================================================
 Web UI       : http://127.0.0.1:8000
 Container    : $CONTAINER
 Docker image : $IMAGE
 Capture      : HOST PipeWire/pw-record
 Whisper      : Large-v3 FP16 / whisper.cpp HIP / :${WHISPER_PORT}
 Whisper log  : $WHISPER_LOG
 Backend log  : docker logs -f $CONTAINER
 Control log  : $CONTROL_LOG

 Invariant: lecture_raw.wav stays authoritative and capture is independent of ASR.
 Master clock: native PipeWire captured samples / 16000.
 ASR: one model only; each Adaptive Segment is transcribed independently.
 Previous-text context: OFF (--no-context).
 VAD gain: VAD_INPUT_GAIN_DB=${VAD_INPUT_GAIN_DB} dB.
 Silero VAD: ${SILERO_VAD_VERSION}.
============================================================
EOF
