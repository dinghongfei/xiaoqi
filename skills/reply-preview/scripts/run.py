#!/usr/bin/env python3
"""Skill entry: reply Feishu preview card. Portable; no host-project imports."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


def _preparse(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", default="")
    args, _ = parser.parse_known_args(argv)
    if args.root:
        os.environ["BOT_ROOT"] = str(Path(args.root).resolve())


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _preparse(argv)

    from config import get_settings
    from pipeline.reply_preview import reply_preview

    parser = argparse.ArgumentParser(description="向飞书消息回复官网/公众号预览卡片")
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--message-id", required=True, help="要回复的飞书 message_id")
    parser.add_argument("--site-preview", default="", help="覆盖 last-job 中的官网 URL")
    parser.add_argument("--wechat-preview", default="", help="覆盖 last-job 中的公众号 URL")
    parser.add_argument("--summary", default="", help="失败或补充说明")
    args = parser.parse_args(argv)

    settings = get_settings(args.env_file or None)
    result = reply_preview(
        settings,
        args.message_id,
        site_preview=args.site_preview,
        wechat_preview=args.wechat_preview,
        summary=args.summary,
    )
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
