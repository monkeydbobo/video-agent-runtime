#!/usr/bin/env bash
# ArcReel 本地开发：停止前后端
# author: wanghaobo

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-/tmp/arcreel-dev}"
BACKEND_PORT="${BACKEND_PORT:-1241}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

log()  { printf '\033[1;34m[dev]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dev]\033[0m %s\n' "$*" >&2; }

# 按 PID 文件停；丢了就 fallback 到端口
stop_by_pid_or_port() {
  local label="$1" pid_file="$2" port="$3"
  local stopped=0

  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && ps -p "${pid}" >/dev/null 2>&1; then
      log "停止 ${label} (pid=${pid})"
      kill "${pid}" 2>/dev/null || true
      # 给 5 秒优雅退出，否则 KILL
      local waited=0
      while (( waited < 5 )) && ps -p "${pid}" >/dev/null 2>&1; do
        sleep 1; waited=$((waited + 1))
      done
      ps -p "${pid}" >/dev/null 2>&1 && kill -9 "${pid}" 2>/dev/null || true
      stopped=1
    fi
    rm -f "${pid_file}"
  fi

  # 兜底：端口仍占用 → 按端口杀
  local listening
  listening="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "${listening}" ]]; then
    warn "${label} 端口 ${port} 仍被占用 (pid=${listening})，强制 kill"
    kill -9 ${listening} 2>/dev/null || true
    stopped=1
  fi

  if (( stopped == 0 )); then
    log "${label} 未在运行"
  fi
}

stop_by_pid_or_port backend  "${RUNTIME_DIR}/backend.pid"  "${BACKEND_PORT}"
stop_by_pid_or_port frontend "${RUNTIME_DIR}/frontend.pid" "${FRONTEND_PORT}"

log "完成"
