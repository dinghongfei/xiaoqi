#!/usr/bin/env python3
"""Skill entry: upload preview/ to object storage. Requires user-provided sk."""

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
    from last_job import load_last_job
    from pipeline.deploy_cloud import deploy_cloud

    parser = argparse.ArgumentParser(description="把 preview/ 上传到对象存储")
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--sk", required=True, help="用户提供的发布口令")
    args = parser.parse_args(argv)
    settings = get_settings(args.env_file or None)
    result = deploy_cloud(settings, secret_key=args.sk)
    print(result.message)
    job = load_last_job(settings) or {}
    if job.get("site_preview"):
        print(f"SITE_PREVIEW={job['site_preview']}")
    if job.get("wechat_preview"):
        print(f"WECHAT_PREVIEW={job['wechat_preview']}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
