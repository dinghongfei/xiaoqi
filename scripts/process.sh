#!/usr/bin/env bash
# 由 start.sh / stop.sh source，不要单独执行。
# 关掉本项目同名进程（bot serve / bot preview-http）以及占用预览端口的监听进程。

: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${PREVIEW_PORT:=1314}"

DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/data/run}"
BOT_PID="${BOT_PID:-$DATA_DIR/bot.pid}"
HTTP_PID="${HTTP_PID:-$DATA_DIR/preview.pid}"

_is_safe_pid() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  [[ "$pid" -gt 1 ]] || return 1
  [[ "$pid" != "$$" && "$pid" != "$PPID" ]] || return 1
  return 0
}

_pid_alive() {
  local pid="$1" st
  _is_safe_pid "$pid" || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  st="$(ps -o state= -p "$pid" 2>/dev/null || true)"
  # 已被结束、等父进程收尸时不必再等。
  [[ "$st" == *Z* ]] && return 1
  return 0
}

_child_pids() {
  local pid="$1"
  pgrep -P "$pid" 2>/dev/null || true
}

_kill_tree() {
  local pid="$1" sig="${2:-TERM}" child
  _is_safe_pid "$pid" || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  for child in $(_child_pids "$pid"); do
    _kill_tree "$child" "$sig"
  done
  kill -s "$sig" "$pid" 2>/dev/null || true
}

_pids_from_pidfile() {
  local pidfile="$1" pid
  [[ -f "$pidfile" ]] || return 0
  pid="$(tr -d '[:space:]' < "$pidfile" || true)"
  if _pid_alive "$pid"; then
    printf '%s\n' "$pid"
  fi
}

_pids_on_port() {
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -nP -iTCP:"$PREVIEW_PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "${PREVIEW_PORT}/tcp" 2>/dev/null || true)"
  fi
  # shellcheck disable=SC2086
  for pid in $pids; do
    if _is_safe_pid "$pid"; then
      printf '%s\n' "$pid"
    fi
  done
}

_pids_by_name() {
  local pat pid comm
  if [[ -n "${XIAOQI_SKIP_NAME_MATCH:-}" ]]; then
    return 0
  fi
  for pat in "uv run bot preview-http" "uv run bot serve" "/bot preview-http" "/bot serve"; do
    while read -r pid; do
      [[ -n "$pid" ]] || continue
      _is_safe_pid "$pid" || continue
      comm="$(ps -o comm= -p "$pid" 2>/dev/null || true)"
      case "$comm" in
        *pgrep*) continue ;;
      esac
      printf '%s\n' "$pid"
    done < <(pgrep -f "$pat" 2>/dev/null || true)
  done
}

_unique_pids() {
  awk 'NF && !seen[$0]++' 
}

_collect_service_pids() {
  {
    _pids_from_pidfile "$BOT_PID"
    _pids_from_pidfile "$HTTP_PID"
    _pids_by_name
    _pids_on_port
  } | _unique_pids
}

_wait_gone() {
  local pid="$1" i
  for i in $(seq 1 20); do
    if ! _pid_alive "$pid"; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

_wait_port_free() {
  local i
  for i in $(seq 1 20); do
    if [[ -z "$(_pids_on_port | _unique_pids)" ]]; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

stop_project_services() {
  local pid pids
  mkdir -p "$DATA_DIR"
  pids="$(_collect_service_pids)"
  if [[ -z "$pids" ]]; then
    echo "没有同名服务，端口 ${PREVIEW_PORT} 也空闲"
  else
    echo "停止已有服务（同名进程或端口 ${PREVIEW_PORT}）…"
    for pid in $pids; do
      echo "  结束 pid=$pid"
      _kill_tree "$pid" TERM
    done
    for pid in $pids; do
      if ! _wait_gone "$pid"; then
        echo "  强制结束 pid=$pid"
        _kill_tree "$pid" KILL
      fi
    done
  fi
  rm -f "$BOT_PID" "$HTTP_PID"
  if ! _wait_port_free; then
    echo "端口 ${PREVIEW_PORT} 仍被占用：$(echo "$(_pids_on_port)" | tr '\n' ' ')" >&2
    return 1
  fi
  echo "已停止"
}
