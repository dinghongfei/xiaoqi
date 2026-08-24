#!/usr/bin/env python3
"""Skill entry: remove generated preview/jobs. Never git reset. Portable."""

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
    from pipeline.clean import clean_generated

    parser = argparse.ArgumentParser(
        description="清理生成稿（preview/_wechat、data/jobs、last-job.json），不执行 git reset。"
    )
    parser.add_argument("--root", default="", help="工作区根目录。默认 BOT_ROOT 或当前目录")
    parser.add_argument("--env-file", default="")
    args = parser.parse_args(argv)

    settings = get_settings(args.env_file or None)
    result = clean_generated(settings)
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
