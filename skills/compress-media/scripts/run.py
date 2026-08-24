#!/usr/bin/env python3
"""Skill entry: compress images/videos with ffmpeg. Portable; no host-project imports."""

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
    from pipeline.media_compress import compress_static_media

    parser = argparse.ArgumentParser(
        description="压缩站点 static 下的图片与视频。脚本在本 Skill 的 scripts/ 内，拷走即可用。"
    )
    parser.add_argument("--root", default="", help="工作区根目录（含 site/）。默认 BOT_ROOT 或当前目录")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--image-dir", default="")
    parser.add_argument("--video-dir", default="")
    args = parser.parse_args(argv)

    settings = get_settings(args.env_file or None)
    result = compress_static_media(
        settings,
        force=True,
        image_dir=Path(args.image_dir) if args.image_dir else None,
        video_dir=Path(args.video_dir) if args.video_dir else None,
    )
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
