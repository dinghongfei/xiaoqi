#!/usr/bin/env python3
"""Feishu doc → standalone WeChat preview HTML."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))


def _safe_token(token: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (token or "").strip())
    return cleaned or "doc"


def _safe_filename(title: str, *, fallback: str = "preview") -> str:
    text = re.sub(r'[\\/:*?"<>|\s]+', "_", (title or "").strip())
    text = text.strip("._")[:80]
    return text or fallback


def main(argv: list[str] | None = None) -> int:
    from deps import ensure

    try:
        ensure()
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1

    from feishu_text import extract_title
    from lark_fetch import extract_token, fetch_markdown, fetch_xml, resolve_docx_token
    from payload import document_from_fetch
    from render import convert_wechat

    parser = argparse.ArgumentParser(
        description="飞书云文档 → 独立公众号预览 HTML"
    )
    parser.add_argument("--url", default="", help="飞书文档链接（只取路径上的 token）")
    parser.add_argument("--token", default="", help="docx 或 wiki token")
    parser.add_argument(
        "--kind",
        default="docx",
        choices=("docx", "wiki"),
        help="token 类型；若同时给了 --url 且未改本项，会优先用 URL 推断",
    )
    parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="复用已有 output/<token>/raw.md 与 raw.xml，不再调用 lark-cli",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="输出目录（默认 <本Skill>/output/<token>）",
    )
    parser.add_argument(
        "--summary",
        default="",
        help="公众号摘要（≤100字）；由 Agent 根据正文总结后传入",
    )
    parser.add_argument(
        "--summary-file",
        default="",
        help="摘要文本文件路径（优先于 --summary）",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    kind = args.kind
    token = (args.token or "").strip()
    if args.url:
        url_kind, url_token = extract_token(args.url)
        if not url_token:
            print("❌ 无法从 URL 解析飞书文档 token。")
            return 1
        token = url_token
        if "--kind" not in list(sys.argv[1:] if argv is None else argv):
            kind = url_kind
    if not token:
        print("❌ 请提供 --url 或 --token。")
        return 1

    work = Path(args.out_dir) if args.out_dir else (SKILL_ROOT / "output" / _safe_token(token))
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    raw_md_path = work / "raw.md"
    raw_xml_path = work / "raw.xml"

    try:
        if args.reuse_raw:
            if not raw_md_path.is_file():
                print(f"❌ 没有可复用的 {raw_md_path}，请先不带 --reuse-raw 拉取。")
                return 1
            raw_md = raw_md_path.read_text(encoding="utf-8")
            raw_xml = (
                raw_xml_path.read_text(encoding="utf-8")
                if raw_xml_path.is_file()
                else ""
            )
            docx_token = token
        else:
            docx_token = resolve_docx_token(token, kind=kind)
            print(f"正在拉取文档 token={docx_token} …", flush=True)
            raw_md = fetch_markdown(docx_token)
            raw_xml = fetch_xml(docx_token)
            raw_md_path.write_text(raw_md, encoding="utf-8")
            raw_xml_path.write_text(raw_xml, encoding="utf-8")
            if kind == "wiki" and docx_token != token:
                (work / "docx_token.txt").write_text(docx_token + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"❌ 拉取飞书文档失败：{exc}")
        return 1

    md_content, _doc_id = document_from_fetch(raw_md)
    xml_content, _ = document_from_fetch(raw_xml) if raw_xml.strip() else ("", "")
    if not md_content.strip():
        print("❌ 文档正文为空。")
        return 1

    (work / "body.md").write_text(md_content, encoding="utf-8")

    summary_arg = ""
    if args.summary_file:
        sp = Path(args.summary_file).expanduser()
        if not sp.is_file():
            print(f"❌ 摘要文件不存在：{sp}")
            return 1
        summary_arg = sp.read_text(encoding="utf-8")
    elif args.summary:
        summary_arg = args.summary
    else:
        # Prefer Agent-written summary.txt in work dir when present
        auto_summary = work / "summary.txt"
        if auto_summary.is_file():
            summary_arg = auto_summary.read_text(encoding="utf-8")

    title_hint = extract_title(md_content, fallback=token) or token
    preview_path = work / f"{_safe_filename(title_hint)}.html"

    result = convert_wechat(
        markdown_text=md_content,
        xml_text=xml_content,
        out_path=preview_path,
        token=_safe_token(docx_token),
        media_dir=work,
        summary=summary_arg or None,
    )
    print(result.message)
    title = result.title or extract_title(md_content, fallback=token)
    if title:
        print(f"title={title}")
    if result.summary:
        print(f"summary={result.summary}")
    if result.status != "ok":
        return 1
    print(f"预览文件={result.html_path}")
    print(f"正文稿={work / 'body.md'}")
    if result.cover_src:
        print(f"封面={result.cover_src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
