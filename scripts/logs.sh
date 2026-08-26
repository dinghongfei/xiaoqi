#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${1:-$PROJECT_ROOT/data/logs/preview-http.log}"
LINES="${2:-f}"
if [[ ! -f "$LOG" ]]; then
  echo "日志不存在: $LOG"
  echo "也可查看预览日志: $PROJECT_ROOT/data/logs/preview-http.log"
  exit 1
fi
if [[ "$LINES" == "f" || "$LINES" == "-f" ]]; then
  tail -f "$LOG"
else
  tail -n "$LINES" "$LOG"
fi
