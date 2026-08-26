#!/usr/bin/env python3
"""Skill entry: inspect a local Feishu markdown draft, then write Agent-generated metadata."""

from __future__ import annotations

import argparse
import json
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


def _add_doc_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--kind", default="docx", choices=("docx", "wiki"))
    parser.add_argument("--markdown", default="", help="lark-cli fetch 的 markdown（或 JSON）文件")
    parser.add_argument("--document-id", default="")


def _resolve_ref(args: argparse.Namespace):
    from parser.message import DocRef, extract_doc_refs

    if args.url:
        refs = extract_doc_refs(args.url)
        ref = refs[0] if refs else None
        if ref is None:
            print("❌ 无法从 URL 解析飞书文档链接。")
            return None
        return ref
    if args.token:
        return DocRef(kind=args.kind, token=args.token, url="")
    from last_job import load_last_job
    from config import get_settings

    settings = get_settings(args.env_file or None)
    job = load_last_job(settings) or {}
    if job.get("token"):
        return DocRef(
            kind=str(job.get("kind") or "docx"),
            token=str(job["token"]),
            url=str(job.get("doc_url") or ""),
        )
    print("❌ 请提供 --url 或 --token。")
    return None


def _load_apply_payload(args: argparse.Namespace) -> dict:
    from parser.metadata import REQUIRED_METADATA_FIELDS
    from pipeline.enricher import parse_metadata_json

    data: dict = {}
    if args.json_file:
        path = Path(args.json_file)
        data.update(parse_metadata_json(path.read_text(encoding="utf-8")))
    elif args.metadata_json:
        data.update(parse_metadata_json(args.metadata_json))

    for field in REQUIRED_METADATA_FIELDS:
        value = getattr(args, field, "") or ""
        if str(value).strip():
            data[field] = value
    if args.cover_image.strip():
        data["cover_image"] = args.cover_image.strip()
    return data


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _preparse(argv)

    from config import get_settings
    from feishu.client import find_enrichment_block_ids
    from feishu.payload import document_from_fetch
    from parser.metadata import MetadataError
    from pipeline.enricher import Enricher

    parser = argparse.ArgumentParser(
        description="读取 Agent 用 lark-cli 拉好的正文，校验并生成本地元数据 / 写回 XML"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="读取正文线索，不写回")
    _add_doc_args(inspect_parser)

    apply_parser = sub.add_parser("apply", help="把已生成的元数据写入本地 processed.md 与 enrich.xml")
    _add_doc_args(apply_parser)
    apply_parser.add_argument("--slug", default="")
    apply_parser.add_argument("--lang", default="")
    apply_parser.add_argument("--title", default="")
    apply_parser.add_argument("--date", default="")
    apply_parser.add_argument("--author", default="")
    apply_parser.add_argument("--categories", default="")
    apply_parser.add_argument("--summary", default="")
    apply_parser.add_argument("--cover-image", default="")
    apply_parser.add_argument("--json", dest="metadata_json", default="")
    apply_parser.add_argument("--json-file", default="")

    ids_parser = sub.add_parser(
        "enrichment-ids",
        help="从 docs +fetch --detail with-ids 的 XML 中取出属性区块 id",
    )
    ids_parser.add_argument("--xml", required=True)
    ids_parser.add_argument("--root", default="")
    ids_parser.add_argument("--env-file", default="")

    args = parser.parse_args(argv)

    if args.command == "enrichment-ids":
        xml_path = Path(args.xml)
        if not xml_path.is_file():
            print(f"❌ 找不到 XML：{xml_path}")
            return 1
        xml, _document_id = document_from_fetch(xml_path.read_text(encoding="utf-8"))
        ids = find_enrichment_block_ids(xml)
        if not ids:
            print("❌ 未找到「属性」区块，请确认 XML 已包含刚 append 的内容。")
            return 1
        print(",".join(ids))
        return 0

    settings = get_settings(args.env_file or None)
    ref = _resolve_ref(args)
    if ref is None:
        return 1

    markdown_path = Path(args.markdown) if args.markdown else None
    enricher = Enricher(settings=settings)
    if args.command == "inspect":
        result = enricher.inspect_doc(
            ref,
            markdown_path=markdown_path,
            document_id=args.document_id,
        )
        if result.status != "ready":
            print(result.message or "inspect 失败。")
            return 1
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    try:
        payload = _load_apply_payload(args)
    except (MetadataError, OSError) as exc:
        print(f"❌ {exc}")
        return 1

    result = enricher.apply_metadata(
        ref,
        payload,
        markdown_path=markdown_path,
        document_id=args.document_id,
    )
    print(result.message or "补全完成。")
    if result.doc_url:
        print(result.doc_url)
    return 0 if result.status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
