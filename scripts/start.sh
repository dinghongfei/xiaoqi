#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
# shellcheck source=process.sh
source "$PROJECT_ROOT/scripts/process.sh"

DATA_DIR="$PROJECT_ROOT/data/run"
LOG_DIR="$PROJECT_ROOT/data/logs"
mkdir -p "$DATA_DIR" "$LOG_DIR" "$PROJECT_ROOT/preview"

BOT_PID="$DATA_DIR/bot.pid"
HTTP_PID="$DATA_DIR/preview.pid"
BOT_LOG="$LOG_DIR/bot.log"
HTTP_LOG="$LOG_DIR/preview-http.log"

# 从当前进程组拆出去，避免助手执行完命令后把预览/飞书进程一起杀掉。
_detach() {
  local pidfile="$1" logfile="$2"
  shift 2
  uv run python - "$pidfile" "$logfile" "$PROJECT_ROOT" "$@" <<'PY'
import os
import sys

pidfile, logfile, cwd, *cmd = sys.argv[1:]
pid = os.fork()
if pid > 0:
    os.waitpid(pid, 0)
    raise SystemExit(0)
os.setsid()
pid2 = os.fork()
if pid2 > 0:
    with open(pidfile, "w", encoding="utf-8") as fh:
        fh.write(str(pid2))
    os._exit(0)
os.chdir(cwd)
os.environ["PYTHONUNBUFFERED"] = "1"
logfd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(logfd, 1)
os.dup2(logfd, 2)
os.close(logfd)
devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(devnull, 0)
os.close(devnull)
try:
    os.execvp(cmd[0], cmd)
except OSError as exc:
    sys.stderr.write(f"启动失败: {exc}\n")
    os._exit(127)
PY
}

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  echo "缺少 .env。请对助手说「安装环境」，把飞书 App ID 和 Secret 发给它。"
  exit 1
fi

stop_project_services

_detach "$HTTP_PID" "$HTTP_LOG" uv run bot preview-http
_detach "$BOT_PID" "$BOT_LOG" uv run bot serve

ok=0
for _ in $(seq 1 40); do
  if curl -sf -o /dev/null --max-time 1 "http://127.0.0.1:${PREVIEW_PORT}/"; then
    ok=1
    break
  fi
  sleep 0.25
done
if [[ "$ok" -ne 1 ]]; then
  echo "预览服务没有在 http://127.0.0.1:${PREVIEW_PORT}/ 起来，请看日志 $HTTP_LOG" >&2
  exit 1
fi

echo "已启动"
echo "  飞书进程 pid=$(cat "$BOT_PID")  日志 $BOT_LOG"
echo "  预览 HTTP pid=$(cat "$HTTP_PID")  http://127.0.0.1:${PREVIEW_PORT}/  日志 $HTTP_LOG"
