"""HTTP preview server bound to loopback (default port 1314)."""

from __future__ import annotations

import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def _bind(host: str, port: int, handler) -> ThreadingHTTPServer:
    if ":" in host and not host.startswith("["):
        return _V6Server((host, port), handler)
    return ThreadingHTTPServer((host, port), handler)


def serve_preview(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 1314,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "index.html"
    if not index.exists():
        index.write_text(
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>内容助手预览</title></head>"
            "<body><p>预览目录已就绪。请先运行 "
            "<code>uv run python skills/deploy-local/scripts/run.py</code>。</p></body></html>\n",
            encoding="utf-8",
        )
    handler = partial(_QuietHandler, directory=str(directory.resolve()))
    hosts = [host]
    if host == "127.0.0.1":
        hosts.append("::1")

    servers: list[ThreadingHTTPServer] = []
    bound: list[str] = []
    last_error: OSError | None = None
    for bind_host in hosts:
        try:
            servers.append(_bind(bind_host, port, handler))
            bound.append(bind_host)
        except OSError as exc:
            last_error = exc

    if not servers:
        raise last_error or OSError(f"无法监听 {host}:{port}")

    for extra in servers[1:]:
        threading.Thread(target=extra.serve_forever, daemon=True).start()

    print(f"预览服务 http://127.0.0.1:{port}/  →  {directory}  (bind {', '.join(bound)})")
    servers[0].serve_forever()
