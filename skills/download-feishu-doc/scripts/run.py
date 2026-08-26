#!/usr/bin/env python3
"""Skill entry: process a Feishu doc the Agent already fetched with lark-cli."""

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
    from last_job import job_dir
    from parser.message import DocRef, extract_doc_refs
    from pipeline.download import download_feishu_doc

    parser = argparse.ArgumentParser(
        description="把 Agent 用 lark-cli 拉好的飞书文档加工成本地 raw/processed 稿"
    )
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--kind", default="docx", choices=("docx", "wiki"))
    parser.add_argument("--section", default="blog")
    parser.add_argument("--markdown", default="", help="lark-cli fetch 的 markdown（或 JSON）文件")
    parser.add_argument("--xml", default="", help="lark-cli fetch 的 xml（或 JSON）文件")
    parser.add_argument("--media-dir", default="", help="lark-cli media-download 的输出目录")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args(argv)
    settings = get_settings(args.env_file or None)

    ref: DocRef | None = None
    if args.url:
        refs = extract_doc_refs(args.url)
        ref = refs[0] if refs else None
        if ref is None:
            print("❌ 无法从 URL 解析飞书文档链接。")
            return 1
    elif args.token:
        ref = DocRef(kind=args.kind, token=args.token, url="")
    else:
        from last_job import load_last_job

        job = load_last_job(settings) or {}
        if job.get("token"):
            ref = DocRef(
                kind=str(job.get("kind") or "docx"),
                token=str(job["token"]),
                url=str(job.get("doc_url") or ""),
            )
    if ref is None:
        print("❌ 请提供 --url 或 --token。")
        return 1

    work = job_dir(settings, ref.token)
    markdown_path = Path(args.markdown) if args.markdown else None
    xml_path = Path(args.xml) if args.xml else None
    media_dir = Path(args.media_dir) if args.media_dir else (work / "media")

    result = download_feishu_doc(
        settings,
        ref,
        section=args.section,
        markdown_path=markdown_path,
        xml_path=xml_path,
        media_dir=media_dir,
        document_id=args.document_id,
    )
    print(result.message)
    if result.slug:
        print(f"slug={result.slug}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
