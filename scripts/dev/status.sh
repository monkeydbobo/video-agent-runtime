#!/usr/bin/env bash
# ArcReel 本地开发：查看前后端运行状态
# author: wanghaobo

set -euo pipefail

RUNTIME_DIR="${RUNTIME_DIR:-/tmp/arcreel-dev}"
BACKEND_PORT="${BACKEND_PORT:-1241}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

check_one() {
  local label="$1" port="$2" pid_file="$3"
  local pid_in_file="" pid_on_port=""
  [[ -f "${pid_file}" ]] && pid_in_file="$(cat "${pid_file}" 2>/dev/null || true)"
  pid_on_port="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true)"

  local state="stopped"
  local pid="-"
  if [[ -n "${pid_on_port}" ]]; then
    state="running"
    pid="${pid_on_port}"
    if [[ -n "${pid_in_file}" && "${pid_in_file}" != "${pid_on_port}" ]]; then
      state="running(外部进程)"
    fi
  fi

  printf '%-9s %-18s pid=%-8s port=%-5s log=%s/%s.log\n' \
    "${label}" "${state}" "${pid}" "${port}" "${RUNTIME_DIR}" "${label}"
}

check_one backend  "${BACKEND_PORT}"  "${RUNTIME_DIR}/backend.pid"
check_one frontend "${FRONTEND_PORT}" "${RUNTIME_DIR}/frontend.pid"
