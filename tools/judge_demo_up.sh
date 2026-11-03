#!/usr/bin/env bash
# Publish (or republish) the KRAKADYL judge demo: backend + frontend over
# public HTTPS via ngrok. Rerunnable: stops the previous demo first, reseeds
# a clean case, and prints the new public URLs.
#
# Required environment (hashes only — never a token, never committed):
#   KRAKADYL_OPERATOR_TOKENS='<identity=sha256,...>'  # from tools/operator_token.py
# META_API_KEY is read from the repo .env (gitignored). No secret is printed.
#
# Processes are detached (setsid) and survive the publishing shell; they do
# NOT survive a reboot — rerun this script after one. Logs: /tmp/krakadyl-demo/.
set -u -o pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_DIR=/tmp/krakadyl-demo
API_PORT=8010
WEB_PORT=4173
LOCAL_CORS="http://localhost:5173,http://127.0.0.1:5173"
mkdir -p "$DEMO_DIR/data"

: "${KRAKADYL_OPERATOR_TOKENS:?set KRAKADYL_OPERATOR_TOKENS to the hashes line from tools/operator_token.py}"
[ -f "$REPO/.env" ] || { echo "missing $REPO/.env (META_API_KEY)" >&2; exit 1; }
set -a; . "$REPO/.env"; set +a
: "${META_API_KEY:?META_API_KEY not set in $REPO/.env}"
command -v ngrok >/dev/null || { echo "ngrok not installed" >&2; exit 1; }

stop_demo() {
  for pattern in "uvicorn.*krakadyl.api.app.*$API_PORT" "ngrok.*krakadyl-tunnels.yml" "vite preview.*$WEB_PORT"; do
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do kill "$pid" 2>/dev/null || true; done
  done
  sleep 2
  for pattern in "uvicorn.*krakadyl.api.app.*$API_PORT" "ngrok.*krakadyl-tunnels.yml" "vite preview.*$WEB_PORT"; do
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do kill -9 "$pid" 2>/dev/null || true; done
  done
}

wait_for() { # $1 = url, $2 = tries
  for _ in $(seq 1 "$2"); do
    if curl -sSf --max-time 2 "$1" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

start_backend() { # $1 = CORS origins
  (cd "$REPO" && setsid -f env \
    KRAKADYL_DATA_DIR="$DEMO_DIR/data" \
    KRAKADYL_OPERATOR_TOKENS="$KRAKADYL_OPERATOR_TOKENS" \
    META_API_KEY="$META_API_KEY" \
    KRAKADYL_ENABLE_SAM=1 \
    KRAKADYL_ENABLE_DEV_ROUTES=1 \
    KRAKADYL_CORS_ORIGINS="$1" \
    "$REPO/.venv/bin/uvicorn" krakadyl.api.app:app \
    --host 127.0.0.1 --port "$API_PORT" --workers 1 \
    </dev/null >>"$DEMO_DIR/backend.log" 2>&1)
}

echo "==> stopping previous demo (if any)"
stop_demo
rm -rf "$DEMO_DIR/data"; mkdir -p "$DEMO_DIR/data"
: >"$DEMO_DIR/backend.log"; : >"$DEMO_DIR/ngrok.log"

echo "==> starting backend (first boot, local CORS until the frontend URL is known)"
start_backend "$LOCAL_CORS"
wait_for "http://127.0.0.1:$API_PORT/openapi.json" 30 || { echo "backend failed to boot; tail:"; tail -n 20 "$DEMO_DIR/backend.log"; exit 1; }

cat >"$DEMO_DIR/krakadyl-tunnels.yml" <<YAML
version: "2"
tunnels:
  krakadyl-api:
    proto: http
    addr: $API_PORT
  krakadyl-web:
    proto: http
    addr: $WEB_PORT
YAML

echo "==> starting ngrok agent (api + web tunnels)"
setsid -f ngrok start --all --config "$DEMO_DIR/krakadyl-tunnels.yml" </dev/null >>"$DEMO_DIR/ngrok.log" 2>&1
wait_for "http://127.0.0.1:4040/api/tunnels" 30 || { echo "ngrok API never came up; tail:"; tail -n 20 "$DEMO_DIR/ngrok.log"; exit 1; }

TUNNELS_JSON="$(curl -ss --max-time 5 http://127.0.0.1:4040/api/tunnels)"
API_URL="$(python3 -c "import json,sys; print(next(t['public_url'] for t in json.load(sys.stdin)['tunnels'] if t['name']=='krakadyl-api'))" <<<"$TUNNELS_JSON")"
WEB_URL="$(python3 -c "import json,sys; print(next(t['public_url'] for t in json.load(sys.stdin)['tunnels'] if t['name']=='krakadyl-web'))" <<<"$TUNNELS_JSON")"
[ -n "$API_URL" ] && [ -n "$WEB_URL" ] || { echo "could not read both tunnel URLs; tail:"; tail -n 20 "$DEMO_DIR/ngrok.log"; exit 1; }
echo "    api: $API_URL"
echo "    web: $WEB_URL"

echo "==> building frontend against the public backend URL"
(cd "$REPO/frontend" && VITE_API_BASE="$API_URL" npm run build >"$DEMO_DIR/frontend-build.log" 2>&1) || { echo "frontend build failed; tail:"; tail -n 20 "$DEMO_DIR/frontend-build.log"; exit 1; }

echo "==> starting frontend preview + restarting backend with the real CORS origin"
(cd "$REPO/frontend" && setsid -f npm run preview -- --port "$WEB_PORT" --host 127.0.0.1 </dev/null >>"$DEMO_DIR/preview.log" 2>&1)
wait_for "http://127.0.0.1:$WEB_PORT/" 30 || { echo "preview failed to boot; tail:"; tail -n 20 "$DEMO_DIR/preview.log"; exit 1; }
for pid in $(pgrep -f "uvicorn.*krakadyl.api.app.*$API_PORT" 2>/dev/null); do kill "$pid" 2>/dev/null || true; done
sleep 2
: >"$DEMO_DIR/backend.log"
start_backend "$WEB_URL"
wait_for "http://127.0.0.1:$API_PORT/openapi.json" 30 || { echo "backend failed to reboot with demo CORS; tail:"; tail -n 20 "$DEMO_DIR/backend.log"; exit 1; }

BACKEND_PID="$(pgrep -f "uvicorn.*krakadyl.api.app.*$API_PORT" | head -n 1)"
echo "==> deployed backend env carries (names only):"
tr '\0' '\n' <"/proc/$BACKEND_PID/environ" | cut -d= -f1 | grep -E "^(META_API_KEY|KRAKADYL_OPERATOR_TOKENS|KRAKADYL_CORS_ORIGINS|KRAKADYL_ENABLE_SAM|KRAKADYL_ENABLE_DEV_ROUTES)$" | sort

echo ""
echo "Judge demo is live:"
echo "  workspace: $WEB_URL   (log in with the investigator-A token)"
echo "  api:       $API_URL"
echo "Tokens are delivered separately, never printed here."
