"""Convert a downloaded Feishu doc into a Hugo markdown article."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from config import Settings
from hugo.paths import find_existing_section
from hugo.writer import write_content_file
from last_job import abs_from_job, load_last_job, relpath, update_last_job
from parser.body_format import prepare_hugo_body
from parser.doc_content import split_doc_content
from parser.feishu_grid import convert_feishu_grid_to_shortcode
from parser.feishu_text import strip_heading_inline_styles, unescape_feishu_text
from parser.metadata import MetadataError, validate_section
from parser.ordered_list import fix_ordered_list_numbering
from urls import site_page_url

logger = logging.getLogger(__name__)

_FEATURED_MD = re.compile(r"!\[[^\]]*\]\((/image/[^)]+)\)")
_FEATURED_SRC = re.compile(r'src="(/image/[^"]+)"')


@dataclass
class ConvertResult:
    status: str  # ok | error
    message: str
    slug: str = ""
    lang: str = ""
    section: str = ""
    content_path: str = ""
    site_preview: str = ""
    paths: list[str] = field(default_factory=list)


def _pick_featured_image(*texts: str) -> str:
    blob = "\n".join(t for t in texts if t)
    match = _FEATURED_MD.search(blob) or _FEATURED_SRC.search(blob)
    if not match:
        return ""
    return match.group(1)


def convert_website(
    settings: Settings,
    *,
    section: str | None = None,
    markdown_path: Path | None = None,
) -> ConvertResult:
    job = load_last_job(settings) or {}
    section_name = validate_section(section or job.get("section") or "blog")

    source = markdown_path or abs_from_job(
        settings,
        job.get("processed_markdown_path") or job.get("raw_markdown_path"),
    )
    if source is None or not source.is_file():
        return ConvertResult(
            status="error",
            message="没有可转换的文档。请先运行 download-feishu-doc，或指定 --markdown。",
        )

    try:
        raw = source.read_text(encoding="utf-8")
        doc = split_doc_content(raw)
    except MetadataError as exc:
        return ConvertResult(status="error", message=f"❌ {exc}")
    except Exception as exc:
        return ConvertResult(status="error", message=f"❌ 读取文档失败：{exc}")

    metadata = doc.metadata
    slug = metadata["slug"]
    lang = metadata["lang"]

    existing = find_existing_section(settings.hugo_root, slug)
    if existing and existing != section_name:
        return ConvertResult(
            status="error",
            message=(
                f"❌ slug「{slug}」已经在 {existing}，不能同时又挂到 {section_name}。"
            ),
            slug=slug,
            lang=lang,
            section=section_name,
        )

    hugo_toml = settings.hugo_root / "hugo.toml"
    if not hugo_toml.is_file():
        return ConvertResult(
            status="error",
            message=f"缺少 {hugo_toml}。演示站应随仓库提供，不要运行 hugo new site。",
        )

    body = unescape_feishu_text(doc.body)
    body = strip_heading_inline_styles(body)
    body = convert_feishu_grid_to_shortcode(body)
    body = fix_ordered_list_numbering(body)
    xml_path = abs_from_job(settings, job.get("xml_path"))
    xml_text = ""
    if xml_path is not None and xml_path.is_file():
        xml_text = xml_path.read_text(encoding="utf-8")
    body = prepare_hugo_body(body, xml_text)

    fm_metadata = {
        k: v
        for k, v in metadata.items()
        if k not in ("slug", "lang", "featured_image")
    }
    featured = (job.get("featured_image") or "").strip() or _pick_featured_image(
        doc.metadata_region, body
    )
    if featured:
        fm_metadata["featured_image"] = featured

    try:
        path = write_content_file(
            hugo_root=settings.hugo_root,
            section=section_name,
            lang=lang,
            slug=slug,
            metadata=fm_metadata,
            body=body,
        )
    except Exception as exc:
        return ConvertResult(
            status="error",
            message=f"❌ 写入 Hugo 文件失败：{exc}",
            slug=slug,
            lang=lang,
            section=section_name,
        )

    rel = relpath(path)
    preview = site_page_url(settings.site_base_url, section_name, slug, lang)
    update_last_job(
        settings,
        slug=slug,
        lang=lang,
        section=section_name,
        content_path=rel,
        featured_image=featured,
        site_preview=preview,
        metadata_warning="",
    )
    return ConvertResult(
        status="ok",
        message=f"已写入官网文章 {rel}",
        slug=slug,
        lang=lang,
        section=section_name,
        content_path=rel,
        site_preview=preview,
        paths=[rel],
    )
