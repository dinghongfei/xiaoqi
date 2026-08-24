#!/usr/bin/env python3
"""Skill entry: hugo build + copy public/ to preview/. Not hugo new site."""

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
    from pipeline.local_preview import deploy_local_preview

    parser = argparse.ArgumentParser(description="对已有 Hugo 工程构建并拷到 preview/")
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    args = parser.parse_args(argv)
    settings = get_settings(args.env_file or None)
    result = deploy_local_preview(settings)
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
