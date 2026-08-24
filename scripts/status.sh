#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data/run"

_status() {
  local pidfile="$1" name="$2"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name 运行中 (pid=$(cat "$pidfile"))"
    return 0
  fi
  echo "$name 未运行"
  [[ -f "$pidfile" ]] && rm -f "$pidfile"
  return 1
}

code=0
_status "$DATA_DIR/bot.pid" "飞书进程" || code=1
_status "$DATA_DIR/preview.pid" "预览 HTTP" || code=1
echo "预览地址: http://127.0.0.1:1314/"
exit "$code"
