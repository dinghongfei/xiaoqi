#!/usr/bin/env python3
"""Skill entry: restyle markdown into WeChat preview HTML with copy button."""

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
    from wechat.renderer import convert_wechat

    parser = argparse.ArgumentParser(description="把 processed.md 换成公众号预览（复制正文）")
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--markdown", default="")
    args = parser.parse_args(argv)
    settings = get_settings(args.env_file or None)
    md = Path(args.markdown) if args.markdown else None
    result = convert_wechat(settings, markdown_path=md)
    print(result.message)
    if result.wechat_preview:
        print(f"公众号预览={result.wechat_preview}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
