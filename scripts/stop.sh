#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data/run"

_stop() {
  local pidfile="$1" name="$2"
  if [[ ! -f "$pidfile" ]]; then
    echo "$name 未在运行"
    return 0
  fi
  local pid
  pid="$(cat "$pidfile")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "停止 $name (pid=$pid)…"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pidfile"
}

_stop "$DATA_DIR/bot.pid" "飞书进程"
_stop "$DATA_DIR/preview.pid" "预览 HTTP"
echo "已停止"
