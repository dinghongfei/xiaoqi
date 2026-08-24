"""bot CLI: Feishu IM process and preview HTTP."""

from __future__ import annotations

import argparse

from bot.config import get_settings


def _cmd_serve(args, _settings) -> int:
    from bot.main import run_serve

    run_serve(args.env_file)
    return 0


def _cmd_preview_http(args, settings) -> int:
    from bot.preview_server import serve_preview

    serve_preview(
        settings.preview_dir,
        host=args.host or settings.preview_host,
        port=args.port or settings.preview_port,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bot",
        description="飞书内容助手：IM 适配与本地预览（编排交给本机 Agent 与 skills/）",
    )
    parser.add_argument("--env-file", default=None, help="环境文件，默认项目根目录 .env")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="启动飞书长连接（不编排 Skill）")
    p.set_defaults(func=_cmd_serve)

    p = sub.add_parser("preview-http", help="在 127.0.0.1:1314 提供 preview/")
    p.add_argument("--host", default="")
    p.add_argument("--port", type=int, default=0)
    p.set_defaults(func=_cmd_preview_http)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings(args.env_file)
    code = args.func(args, settings)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
