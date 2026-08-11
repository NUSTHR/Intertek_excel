#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
RUNTIME_DIR="${SHARE_TEST_RUNTIME_DIR:-${PROJECT_ROOT}/.runtime/share-test}"
BACKEND_LOG="${RUNTIME_DIR}/backend.log"
FRONTEND_LOG="${RUNTIME_DIR}/frontend.log"
TUNNEL_LOG="${RUNTIME_DIR}/cloudflared.log"
PUBLIC_URL_FILE="${RUNTIME_DIR}/public-url.txt"
COOKIE_JAR="${RUNTIME_DIR}/.auth-cookies"
AUTH_HEADERS="${RUNTIME_DIR}/.auth-headers"
PUBLIC_TEST_STORAGE="${RUNTIME_DIR}/storage"
PUBLIC_TEST_DATABASE="${RUNTIME_DIR}/excel-workspace.sqlite3"
BACKEND_PORT=8090
FRONTEND_PORT=5174
BACKEND_PID=""
FRONTEND_PID=""
TUNNEL_PID=""

mkdir -p "${RUNTIME_DIR}"
chmod 700 "${RUNTIME_DIR}"
mkdir -p "${PUBLIC_TEST_STORAGE}"
: >"${BACKEND_LOG}"
: >"${FRONTEND_LOG}"
: >"${TUNNEL_LOG}"
chmod 600 "${BACKEND_LOG}" "${FRONTEND_LOG}" "${TUNNEL_LOG}"

cleanup() {
  trap - EXIT INT TERM
  rm -f "${COOKIE_JAR}" "${AUTH_HEADERS}"
  for process_id in "${TUNNEL_PID}" "${FRONTEND_PID}" "${BACKEND_PID}"; do
    if [[ -n "${process_id}" ]] && kill -0 "${process_id}" >/dev/null 2>&1; then
      kill "${process_id}" >/dev/null 2>&1 || true
    fi
  done
  for process_id in "${TUNNEL_PID}" "${FRONTEND_PID}" "${BACKEND_PID}"; do
    if [[ -n "${process_id}" ]]; then
      wait "${process_id}" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT TERM

find_node() {
  if [[ -n "${NODE_BIN:-}" ]] && [[ -x "${NODE_BIN}" ]]; then
    printf '%s\n' "${NODE_BIN}"
    return
  fi
  if command -v node >/dev/null 2>&1; then
    command -v node
    return
  fi
  local bundled_node="/Users/intertek/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
  if [[ -x "${bundled_node}" ]]; then
    printf '%s\n' "${bundled_node}"
    return
  fi
  return 1
}

find_cloudflared() {
  if [[ -n "${CLOUDFLARED_BIN:-}" ]] && [[ -x "${CLOUDFLARED_BIN}" ]]; then
    printf '%s\n' "${CLOUDFLARED_BIN}"
    return
  fi
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return
  fi
  if [[ -x "${PROJECT_ROOT}/.tools/cloudflared" ]]; then
    printf '%s\n' "${PROJECT_ROOT}/.tools/cloudflared"
    return
  fi
  return 1
}

port_is_busy() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="$3"
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl --fail --silent --show-error --max-time 5 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for ${label}: ${url}"
  return 1
}

show_log_tail() {
  local label="$1"
  local path="$2"
  echo "${label} log (${path}):"
  tail -n 30 "${path}" 2>/dev/null || true
}

if [[ ! -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
  echo "Backend virtual environment is missing: ${BACKEND_DIR}/.venv"
  exit 1
fi
PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"

if ! NODE_BIN_RESOLVED="$(find_node)"; then
  echo "Node.js was not found. Set NODE_BIN to an executable Node.js path."
  exit 1
fi
if ! CLOUDFLARED_BIN_RESOLVED="$(find_cloudflared)"; then
  echo "cloudflared was not found. Run ./scripts/install-cloudflared.sh first."
  exit 1
fi
if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  echo "Frontend dependencies are missing: ${FRONTEND_DIR}/node_modules"
  exit 1
fi
if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
  echo "Backend configuration is missing: ${BACKEND_DIR}/.env"
  exit 1
fi
if ! command -v curl >/dev/null 2>&1 || ! command -v lsof >/dev/null 2>&1; then
  echo "This script requires curl and lsof."
  exit 1
fi
if port_is_busy "${BACKEND_PORT}" || port_is_busy "${FRONTEND_PORT}"; then
  echo "Ports ${BACKEND_PORT} and ${FRONTEND_PORT} must be free before starting."
  echo "Stop existing backend/frontend processes, then run this script again."
  exit 1
fi

if [[ -n "${HOME:-}" ]]; then
  for config_path in "${HOME}/.cloudflared/config.yml" "${HOME}/.cloudflared/config.yaml"; do
    if [[ -f "${config_path}" ]]; then
      echo "Quick Tunnel cannot run while this Cloudflare config exists: ${config_path}"
      echo "Temporarily move that file or use a named Cloudflare Tunnel."
      exit 1
    fi
  done
fi

(
  cd "${BACKEND_DIR}"
  "${PYTHON_BIN}" - <<'PY'
from app.core.config import get_settings

settings = get_settings()
errors = []
if settings.auth_admin_password == "admin" or len(settings.auth_admin_password) < 16:
    errors.append("AUTH_ADMIN_PASSWORD must be a generated value with at least 16 characters")
if not settings.auth_cookie_secure:
    errors.append("AUTH_COOKIE_SECURE must be true")
if settings.auth_expose_reset_token:
    errors.append("AUTH_EXPOSE_RESET_TOKEN must be false")
if settings.auth_cookie_samesite.strip().lower() not in {"lax", "strict"}:
    errors.append("AUTH_COOKIE_SAMESITE must be lax or strict for this test setup")
if errors:
    raise SystemExit("Unsafe public-test configuration: " + "; ".join(errors))
print("Public-test configuration checks passed.")
PY
)

echo "Starting FastAPI backend on 127.0.0.1:${BACKEND_PORT}..."
(
  cd "${BACKEND_DIR}"
  EXCEL_DATABASE_PATH="${PUBLIC_TEST_DATABASE}" \
  EXCEL_STORAGE_ROOT="${PUBLIC_TEST_STORAGE}" \
    exec "${PYTHON_BIN}" -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}"
) >"${BACKEND_LOG}" 2>&1 &
BACKEND_PID="$!"

if ! wait_for_url "http://127.0.0.1:${BACKEND_PORT}/ready" "backend readiness" 90; then
  show_log_tail "Backend" "${BACKEND_LOG}"
  exit 1
fi

echo "Starting Vite frontend on 127.0.0.1:${FRONTEND_PORT}..."
(
  cd "${FRONTEND_DIR}"
  exec "${NODE_BIN_RESOLVED}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port "${FRONTEND_PORT}"
) >"${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID="$!"

if ! wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/health" "frontend proxy health" 60; then
  show_log_tail "Frontend" "${FRONTEND_LOG}"
  exit 1
fi

PUBLIC_URL=""
TUNNEL_READY=false
for ((tunnel_attempt = 1; tunnel_attempt <= 6; tunnel_attempt += 1)); do
  echo "Starting Cloudflare Quick Tunnel (attempt ${tunnel_attempt}/6)..."
  : >"${TUNNEL_LOG}"
  "${CLOUDFLARED_BIN_RESOLVED}" tunnel --protocol http2 --url "http://127.0.0.1:${FRONTEND_PORT}" >"${TUNNEL_LOG}" 2>&1 &
  TUNNEL_PID="$!"
  PUBLIC_URL=""

  for ((attempt = 1; attempt <= 30; attempt += 1)); do
    PUBLIC_URL="$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "${TUNNEL_LOG}" | head -n 1 || true)"
    if [[ -n "${PUBLIC_URL}" ]]; then
      break
    fi
    if ! kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if [[ -n "${PUBLIC_URL}" ]] && wait_for_url "${PUBLIC_URL}/health" "public tunnel health" 15; then
    TUNNEL_READY=true
    break
  fi

  if kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    kill "${TUNNEL_PID}" >/dev/null 2>&1 || true
  fi
  wait "${TUNNEL_PID}" >/dev/null 2>&1 || true
  TUNNEL_PID=""
done

if [[ "${TUNNEL_READY}" != true ]]; then
  echo "Cloudflare did not publish a reachable Quick Tunnel after 6 attempts."
  show_log_tail "Cloudflared" "${TUNNEL_LOG}"
  exit 1
fi

ADMIN_EMAIL="$(
  cd "${BACKEND_DIR}"
  "${PYTHON_BIN}" - <<'PY'
from app.core.config import get_settings

settings = get_settings()
print(settings.auth_admin_email)
PY
)"
ADMIN_PASSWORD="$(
  cd "${BACKEND_DIR}"
  "${PYTHON_BIN}" - <<'PY'
from app.core.config import get_settings

print(get_settings().auth_admin_password)
PY
)"
LOGIN_PAYLOAD="$(printf '{"email":"%s","password":"%s"}' "${ADMIN_EMAIL}" "${ADMIN_PASSWORD}")"
LOGIN_STATUS="$(
  printf '%s' "${LOGIN_PAYLOAD}" | curl --silent --show-error \
    --output /dev/null \
    --dump-header "${AUTH_HEADERS}" \
    --cookie-jar "${COOKIE_JAR}" \
    --write-out '%{http_code}' \
    --request POST \
    --header 'Content-Type: application/json' \
    --data-binary @- \
    "${PUBLIC_URL}/api/auth/login"
)"
if [[ "${LOGIN_STATUS}" != "200" ]]; then
  echo "Public authentication check failed with HTTP ${LOGIN_STATUS}."
  exit 1
fi
SESSION_COOKIE_HEADER="$(grep -i '^set-cookie: excelai_session=' "${AUTH_HEADERS}" | head -n 1 || true)"
if [[ -z "${SESSION_COOKIE_HEADER}" ]] || ! grep -qi '; secure' <<<"${SESSION_COOKIE_HEADER}"; then
  echo "Public authentication did not return a Secure session cookie."
  exit 1
fi
CSRF_TOKEN="$(awk '$6 == "excelai_csrf" {print $7}' "${COOKIE_JAR}" | tail -n 1)"
if [[ -z "${CSRF_TOKEN}" ]]; then
  echo "Public authentication did not return a CSRF cookie."
  exit 1
fi
LOGOUT_STATUS="$(curl --silent --show-error \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request POST \
  --cookie "${COOKIE_JAR}" \
  --header "X-CSRF-Token: ${CSRF_TOKEN}" \
  "${PUBLIC_URL}/api/auth/logout")"
if [[ "${LOGOUT_STATUS}" != "204" ]]; then
  echo "Public CSRF/logout check failed with HTTP ${LOGOUT_STATUS}."
  exit 1
fi
rm -f "${COOKIE_JAR}" "${AUTH_HEADERS}"

printf '%s\n' "${PUBLIC_URL}" >"${PUBLIC_URL_FILE}"
chmod 600 "${PUBLIC_URL_FILE}"

echo
echo "Temporary public test environment is ready."
echo "Public URL: ${PUBLIC_URL}"
echo "Health, login, Secure Cookie, CSRF, and frontend proxy checks passed."
echo "Data isolation: ${PUBLIC_TEST_STORAGE}"
echo "Admin email: ${ADMIN_EMAIL}"
echo "The generated admin password remains in backend/.env and is not printed."
echo "Runtime logs: ${RUNTIME_DIR}"
echo "Press Ctrl+C to stop the tunnel, frontend, and backend."

while true; do
  if ! kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    show_log_tail "Backend" "${BACKEND_LOG}"
    exit 1
  fi
  if ! kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
    show_log_tail "Frontend" "${FRONTEND_LOG}"
    exit 1
  fi
  if ! kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    show_log_tail "Cloudflared" "${TUNNEL_LOG}"
    exit 1
  fi
  sleep 2
done
