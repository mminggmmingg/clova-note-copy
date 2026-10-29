#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Local Clova V8.0-beta.5 Control Launcher
#
# V8.0-beta.5 keeps Qwen3.8 removed; no host llama-server is started.
# Starts only:
#   1) Host shutdown controller :8765
#   2) Local Clova ROCm Docker  :8000
#
# Inside Docker:
#   - Qwen3-ASR realtime preview
#   - Continuous immutable lecture_raw.wav
#   - RAW-first BatiSay segment STT + optional DeepFilterNet
#   - Professor-specific PEFT/LoRA adapters
# ============================================================

VERSION="v8.0-beta.5-control"
CLOVA_DIR="$HOME/clova-note-copy"
RUNTIME_DIR="$CLOVA_DIR/.runtime-v8.0-beta.5"
IMAGE="${CLOVA_V8_BETA5_IMAGE:-local-clova:rocm-v8-beta5}"
CONTAINER="local-clova-v8-beta5"
LOG_DIR="$CLOVA_DIR/logs"
CLOVA_LOG="$LOG_DIR/local-clova-v8-beta5.log"
CONTROL_PORT="8765"
CONTROL_SCRIPT="$RUNTIME_DIR/clova_host_control_v8_beta5.py"
CONTROL_LOG="$LOG_DIR/clova-host-control-v8-beta5.log"
CONTROL_PID_FILE="$LOG_DIR/clova-host-control-v8-beta5.pid"
TOKEN_FILE="$RUNTIME_DIR/clova-control-token"
mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

info(){ printf '\n\033[1;36m[Local Clova]\033[0m %s\n' "$*"; }
warn(){ printf '\n\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\n\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

web_ready(){ curl -fsS --max-time 2 http://127.0.0.1:8000/ >/dev/null 2>&1; }
control_ready(){
  local body
  body="$(curl -fsS --max-time 2 http://127.0.0.1:${CONTROL_PORT}/health 2>/dev/null || true)"
  [[ "$body" == *'"version": "v8.0-beta.5-control"'* ]] || [[ "$body" == *'"version":"v8.0-beta.5-control"'* ]]
}

command -v docker >/dev/null 2>&1 || fail "docker not found"
command -v curl >/dev/null 2>&1 || fail "curl not found"
command -v python3 >/dev/null 2>&1 || fail "python3 not found"
[[ -d "$CLOVA_DIR" ]] || fail "Clova directory missing: $CLOVA_DIR"
[[ -f "$CLOVA_DIR/run_clova_v8_beta5.py" ]] || fail "Missing V8.0-beta.5 backend"
[[ -f "$CLOVA_DIR/professor_lora_v7_9.py" ]] || fail "Missing V7.9 LoRA trainer"
[[ -f "$CLOVA_DIR/batisay-ko-large/config.json" ]] || fail "BatiSay model missing"
[[ -f "$CLOVA_DIR/batisay-ko-large/model.safetensors.index.json" ]] || fail "BatiSay index missing"
[[ -f "$CLOVA_DIR/batisay-ko-large/model-00001-of-00002.safetensors" ]] || fail "BatiSay shard 1 missing"
[[ -f "$CLOVA_DIR/batisay-ko-large/model-00002-of-00002.safetensors" ]] || fail "BatiSay shard 2 missing"
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "Docker image '$IMAGE' is missing. Re-run install-clova-v8.0-beta.5.sh to build the PEFT layer."

if [[ ! -s "$TOKEN_FILE" ]]; then
  python3 - <<'PY' > "$TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(32))
PY
  chmod 600 "$TOKEN_FILE"
fi
CONTROL_TOKEN="$(cat "$TOKEN_FILE")"

cat > "$CONTROL_SCRIPT" <<'PY'
#!/usr/bin/env python3
import json, os, signal, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION="v8.0-beta.5-control"
HOST="0.0.0.0"
PORT=8765
CONTAINER="local-clova-v8-beta5"
ROOT=Path(__file__).resolve().parent
TOKEN=(ROOT/"clova-control-token").read_text(encoding="utf-8").strip()

def log(msg): print(f"[Clova Host Control] {msg}", flush=True)

def shutdown_stack():
    try:
        subprocess.run(["docker","stop","-t","8",CONTAINER], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Local Clova Docker stopped")
    finally:
        # V8.0-beta.5 has no Qwen3.8 host process to stop.
        threading.Timer(0.4, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_json(self, status, obj):
        body=json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path=="/health": return self.send_json(200,{"ok":True,"version":VERSION})
        self.send_json(404,{"error":"not found"})
    def do_POST(self):
        if self.path!="/shutdown": return self.send_json(404,{"error":"not found"})
        if self.headers.get("X-Clova-Token","") != TOKEN: return self.send_json(403,{"error":"forbidden"})
        self.send_json(202,{"ok":True,"status":"shutting_down","version":VERSION})
        threading.Thread(target=shutdown_stack,daemon=True).start()

if __name__=="__main__":
    log(f"{VERSION} listening on {HOST}:{PORT}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
PY
chmod 700 "$CONTROL_SCRIPT"

if control_ready; then
  info "Host shutdown controller already running on :${CONTROL_PORT}"
else
  if [[ -s "$CONTROL_PID_FILE" ]]; then
    OLD="$(cat "$CONTROL_PID_FILE" 2>/dev/null || true)"
    if [[ "$OLD" =~ ^[0-9]+$ ]] && kill -0 "$OLD" 2>/dev/null; then kill "$OLD" 2>/dev/null || true; sleep .4; fi
  fi
  info "Starting host shutdown controller..."
  nohup python3 "$CONTROL_SCRIPT" >"$CONTROL_LOG" 2>&1 &
  echo $! > "$CONTROL_PID_FILE"
  for _ in $(seq 1 50); do control_ready && break; sleep .2; done
  control_ready || { tail -n 80 "$CONTROL_LOG" >&2 || true; fail "Host shutdown controller failed"; }
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  info "Clova container already running: $CONTAINER"
else
  docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" && docker rm -f "$CONTAINER" >/dev/null
  info "Starting Local Clova V8.0-beta.5 Master Timeline container..."
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
    -e DENOISE_BIN="/workspace/tools/deep-filter" \
    -e STT_AUDIO_SOURCE_DEFAULT="raw" \
    -e DENOISE_ENABLED="1" -e DENOISE_TIMEOUT_SEC="90" \
    -e DENOISE_POST_FILTER="1" -e DENOISE_PF_BETA="0.04" -e DENOISE_ATTEN_LIM_DB="100" \
    -e LORA_MIN_SAMPLES="12" -e LORA_MIN_NEW_SAMPLES="8" \
    -e LORA_TRAIN_EPOCHS="1" -e LORA_TRAIN_MAX_STEPS="240" -e LORA_TRAIN_LR="1e-4" \
    "$IMAGE" bash -lc 'cd /workspace && exec python3 /workspace/run_clova_v8_beta5.py' >/dev/null
fi

info "Waiting for web server on :8000..."
for _ in $(seq 1 240); do
  web_ready && break
  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    docker logs --tail 180 "$CONTAINER" >&2 || true
    fail "Clova container exited during startup"
  fi
  sleep 1
done
web_ready || { docker logs --tail 180 "$CONTAINER" >&2 || true; fail "Web server did not become ready"; }
docker logs "$CONTAINER" > "$CLOVA_LOG" 2>&1 || true

info "Local Clova V8.0-beta.5 ready"
cat <<EOF

============================================================
 Local Clova V8.0-beta.5 · Master Recording Timeline
============================================================
 Web UI       : http://127.0.0.1:8000
 Container    : $CONTAINER
 Docker image : $IMAGE
 Qwen3.8      : REMOVED (no :8083 server)
 Live log     : docker logs -f $CONTAINER

 Master clock -> continuous capture -> VAD/SEG -> RAW-first BatiSay + PDF workspace
 Internal-mic profile: NS/AGC ON, echo cancellation OFF; RAW segment remains the default BatiSay source.
 V7.9.3 word alignment / Professor LoRA remains unchanged.
============================================================
EOF
