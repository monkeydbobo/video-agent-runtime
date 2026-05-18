#!/usr/bin/env bash
# ArcReel 本地开发：一键启动前后端
# author: wanghaobo
#
# 默认行为：
#   - 后端 → http://127.0.0.1:1241   日志 /tmp/arcreel-dev/backend.log
#   - 前端 → http://localhost:5173   日志 /tmp/arcreel-dev/frontend.log
#   - PID  → /tmp/arcreel-dev/{backend,frontend}.pid
#
# 可通过环境变量覆盖：BACKEND_PORT / FRONTEND_PORT / BACKEND_HOST / RUNTIME_DIR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BACKEND_PORT="${BACKEND_PORT:-1241}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
RUNTIME_DIR="${RUNTIME_DIR:-/tmp/arcreel-dev}"
REQUIRED_NODE_MAJOR_MIN_20="20.19.0"
REQUIRED_NODE_MAJOR_MIN_22="22.12.0"

mkdir -p "${RUNTIME_DIR}"
BACKEND_LOG="${RUNTIME_DIR}/backend.log"
FRONTEND_LOG="${RUNTIME_DIR}/frontend.log"
BACKEND_PID_FILE="${RUNTIME_DIR}/backend.pid"
FRONTEND_PID_FILE="${RUNTIME_DIR}/frontend.pid"

log()  { printf '\033[1;34m[dev]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dev]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. 检查端口是否被占用（含已有的 dev 进程）
# ---------------------------------------------------------------------------
check_port_free() {
  local port="$1" label="$2" pid_file="$3"
  local pid_in_file=""
  [[ -f "${pid_file}" ]] && pid_in_file="$(cat "${pid_file}" 2>/dev/null || true)"

  local listening_pid
  listening_pid="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true)"

  if [[ -n "${listening_pid}" ]]; then
    if [[ -n "${pid_in_file}" && "${listening_pid}" == "${pid_in_file}" ]]; then
      log "${label} 已在运行（pid=${listening_pid}, 端口 ${port}），跳过启动"
      return 1
    fi
    die "端口 ${port} 被其它进程占用 (pid=${listening_pid})，请先停止它或换端口（${label^^}_PORT=xxxx）"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# 1. 加载 nvm，并切到满足 vite 要求的 Node（20.19+ 或 22.12+）
# ---------------------------------------------------------------------------
load_node() {
  if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck source=/dev/null
    . "${NVM_DIR}/nvm.sh"
  fi

  local current
  current="$(node -v 2>/dev/null | sed 's/^v//')" || current=""

  if node_version_ok "${current}"; then
    log "Node ${current} 满足要求"
    return
  fi

  warn "当前 Node=${current:-未安装}，不满足 Vite 要求（>=${REQUIRED_NODE_MAJOR_MIN_20} 或 >=${REQUIRED_NODE_MAJOR_MIN_22}）"

  if ! command -v nvm >/dev/null 2>&1; then
    die "未检测到 nvm，请手动安装合适版本：https://github.com/nvm-sh/nvm"
  fi

  # 优先使用已安装的兼容版本
  local installed
  installed="$(nvm ls --no-alias 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | sort -V | uniq || true)"
  while IFS= read -r v; do
    [[ -z "${v}" ]] && continue
    if node_version_ok "${v#v}"; then
      log "切换到已安装的 Node ${v}"
      nvm use "${v}" >/dev/null
      return
    fi
  done <<< "${installed}"

  log "未发现可用版本，nvm install 22"
  nvm install 22
  nvm use 22 >/dev/null
}

node_version_ok() {
  local v="$1"
  [[ -z "${v}" ]] && return 1
  python3 - <<PY "${v}" "${REQUIRED_NODE_MAJOR_MIN_20}" "${REQUIRED_NODE_MAJOR_MIN_22}"
import sys
def parse(s): return tuple(int(x) for x in s.split('.'))
v, min20, min22 = parse(sys.argv[1]), parse(sys.argv[2]), parse(sys.argv[3])
sys.exit(0 if (v[0] == 20 and v >= min20) or (v[0] >= 22 and (v[0] > 22 or v >= min22)) else 1)
PY
}

# ---------------------------------------------------------------------------
# 2. 后端依赖
# ---------------------------------------------------------------------------
ensure_backend() {
  cd "${PROJECT_ROOT}"

  if [[ ! -d ".venv" ]]; then
    log "未发现 .venv，执行 uv sync 创建并安装依赖"
    command -v uv >/dev/null 2>&1 || die "未检测到 uv，请先安装：https://docs.astral.sh/uv/"
    uv sync
  fi

  if ! .venv/bin/python -c "import fastapi" >/dev/null 2>&1; then
    log "venv 缺少核心依赖，执行 pip install -e ."
    .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
    .venv/bin/python -m pip install -e . >/dev/null
  fi

  log "执行 alembic upgrade head"
  .venv/bin/alembic upgrade head >/dev/null
}

# ---------------------------------------------------------------------------
# 3. 前端依赖
# ---------------------------------------------------------------------------
ensure_frontend() {
  cd "${PROJECT_ROOT}/frontend"

  if [[ ! -d "node_modules" ]]; then
    log "未发现 node_modules，执行 pnpm install"
    command -v pnpm >/dev/null 2>&1 || die "未检测到 pnpm，请先安装：npm i -g pnpm"
    pnpm install
  fi
}

# ---------------------------------------------------------------------------
# 4. 启动
# ---------------------------------------------------------------------------
start_backend() {
  check_port_free "${BACKEND_PORT}" backend "${BACKEND_PID_FILE}" || return 0

  log "启动后端 → http://${BACKEND_HOST}:${BACKEND_PORT}"
  cd "${PROJECT_ROOT}"
  : > "${BACKEND_LOG}"
  nohup .venv/bin/uvicorn server.app:app \
      --reload \
      --reload-dir server --reload-dir lib \
      --host "${BACKEND_HOST}" \
      --port "${BACKEND_PORT}" \
      > "${BACKEND_LOG}" 2>&1 &
  echo $! > "${BACKEND_PID_FILE}"
  disown || true
}

start_frontend() {
  check_port_free "${FRONTEND_PORT}" frontend "${FRONTEND_PID_FILE}" || return 0

  log "启动前端 → http://localhost:${FRONTEND_PORT}"
  cd "${PROJECT_ROOT}/frontend"
  : > "${FRONTEND_LOG}"
  nohup pnpm dev --port "${FRONTEND_PORT}" > "${FRONTEND_LOG}" 2>&1 &
  echo $! > "${FRONTEND_PID_FILE}"
  disown || true
}

# ---------------------------------------------------------------------------
# 5. 等服务就绪
# ---------------------------------------------------------------------------
wait_ready() {
  local port="$1" label="$2" timeout="${3:-30}"
  local elapsed=0
  while (( elapsed < timeout )); do
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      log "${label} 已就绪（端口 ${port}）"
      return 0
    fi
    sleep 1; elapsed=$((elapsed + 1))
  done
  warn "${label} 等待 ${timeout}s 后仍未就绪，请查看日志：tail -f ${RUNTIME_DIR}/${label}.log"
  return 1
}

# ---------------------------------------------------------------------------
# 6. 输出汇总（含 AUTH_PASSWORD）
# ---------------------------------------------------------------------------
print_summary() {
  local password=""
  if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    password="$(grep -E '^AUTH_PASSWORD=' "${PROJECT_ROOT}/.env" | head -n1 | cut -d= -f2-)"
  fi

  cat <<EOF

================ ArcReel Dev ================
后端  : http://${BACKEND_HOST}:${BACKEND_PORT}      pid=$(cat "${BACKEND_PID_FILE}" 2>/dev/null || echo -)  log=${BACKEND_LOG}
前端  : http://localhost:${FRONTEND_PORT}            pid=$(cat "${FRONTEND_PID_FILE}" 2>/dev/null || echo -)  log=${FRONTEND_LOG}
登录  : admin / ${password:-（首次启动后查看 .env 中 AUTH_PASSWORD）}
设置  : http://localhost:${FRONTEND_PORT}/settings  （配置 API Key）
停止  : bash ${SCRIPT_DIR}/stop.sh
状态  : bash ${SCRIPT_DIR}/status.sh
日志  : tail -f ${BACKEND_LOG}    /    tail -f ${FRONTEND_LOG}
=============================================
EOF
}

# ---------------------------------------------------------------------------
main() {
  log "项目根目录：${PROJECT_ROOT}"
  load_node
  ensure_backend
  ensure_frontend
  start_backend
  start_frontend
  wait_ready "${BACKEND_PORT}"  backend  60 || true
  wait_ready "${FRONTEND_PORT}" frontend 30 || true
  print_summary
}

main "$@"
