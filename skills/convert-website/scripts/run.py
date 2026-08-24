#!/usr/bin/env python3
"""Skill entry: write Hugo markdown from a downloaded Feishu doc."""

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
    from pipeline.convert_website import convert_website

    parser = argparse.ArgumentParser(description="写成官网 Hugo Markdown")
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--section", default=None)
    parser.add_argument("--markdown", default="", help="覆盖 last-job 中的 processed.md")
    args = parser.parse_args(argv)
    settings = get_settings(args.env_file or None)
    md = Path(args.markdown) if args.markdown else None
    result = convert_website(settings, section=args.section, markdown_path=md)
    print(result.message)
    if result.site_preview:
        print(f"SITE_PREVIEW={result.site_preview}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
