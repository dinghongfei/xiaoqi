"""Download a Feishu cloud doc (markdown + xml + media) without writing Hugo."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from config import Settings
from feishu.client import FeishuClient
from hugo.paths import find_existing_section
from last_job import dump_last_job, job_dir, relpath
from media.compress import MediaCompressor
from media.downloader import MediaProcessor
from media.index import MediaIndex, build_media_index_from_xml
from parser.doc_content import split_doc_content
from parser.feishu_text import prepare_feishu_markdown
from parser.message import DocRef
from parser.metadata import MetadataError
from state.store import StateStore

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    status: str  # ok | error
    message: str
    token: str = ""
    kind: str = ""
    document_id: str = ""
    doc_url: str = ""
    slug: str = ""
    lang: str = ""
    section: str = ""
    raw_markdown_path: str = ""
    processed_markdown_path: str = ""
    xml_path: str = ""
    featured_image: str = ""
    paths: list[str] = field(default_factory=list)


def _build_media_index(client: FeishuClient, doc_ref: DocRef) -> tuple[MediaIndex, str]:
    try:
        xml = client.fetch_doc_xml(doc_ref)
        index = build_media_index_from_xml(xml)
        logger.info(
            "Built media index for %s: %d urls, %d prefixes",
            doc_ref.label,
            len(index.by_url),
            len(index.by_prefix),
        )
        return index, xml
    except Exception as exc:
        logger.warning(
            "Failed to fetch XML media index for %s, will rely on stream URLs: %s",
            doc_ref.label,
            exc,
        )
        return MediaIndex(), ""


def download_feishu_doc(
    settings: Settings,
    client: FeishuClient,
    doc_ref: DocRef,
    *,
    section: str = "blog",
) -> DownloadResult:
    label = doc_ref.label
    doc_url = (doc_ref.url or "").strip()
    try:
        raw, document_id = client.fetch_doc_markdown(doc_ref)
        media_index, xml = _build_media_index(client, doc_ref)
    except Exception as exc:
        logger.exception("Download failed [%s]", label)
        return DownloadResult(
            status="error",
            message=f"❌ 下载文档失败：{exc}",
            token=doc_ref.token,
            kind=doc_ref.kind,
            doc_url=doc_url,
        )

    work = job_dir(settings, doc_ref.token)
    raw_path = work / "raw.md"
    xml_path = work / "raw.xml"
    processed_path = work / "processed.md"
    raw_path.write_text(raw, encoding="utf-8")
    if xml:
        xml_path.write_text(xml, encoding="utf-8")

    processor = MediaProcessor(
        client=client,
        image_dir=settings.image_dir,
        video_dir=settings.video_dir,
        media_index=media_index,
        compressor=MediaCompressor.from_settings(settings),
        token_store=StateStore(settings.state_db_path),
    )

    prepared = prepare_feishu_markdown(raw)
    processed = processor.process_body(prepared)
    processed_path.write_text(processed, encoding="utf-8")

    slug = ""
    lang = ""
    featured = ""
    meta_error = ""
    try:
        doc = split_doc_content(processed)
        slug = doc.metadata.get("slug", "")
        lang = doc.metadata.get("lang", "")
        featured = processor.resolve_featured_image(doc.metadata_region, doc.body) or ""
        existing = find_existing_section(settings.hugo_root, slug) if slug else None
        if existing and existing != section:
            meta_error = (
                f"slug「{slug}」已经在 {existing}，不能再写到 {section}。"
                "请改 slug 或改栏目。"
            )
    except MetadataError as exc:
        meta_error = str(exc)
    except Exception as exc:
        logger.warning("Metadata parse skipped [%s]: %s", label, exc)
        meta_error = str(exc)

    job = {
        "kind": doc_ref.kind,
        "token": doc_ref.token,
        "document_id": document_id,
        "doc_url": doc_url,
        "slug": slug,
        "lang": lang,
        "section": section,
        "raw_markdown_path": relpath(raw_path),
        "processed_markdown_path": relpath(processed_path),
        "xml_path": relpath(xml_path) if xml else "",
        "featured_image": featured,
        "content_path": "",
        "site_preview": "",
        "wechat_preview": "",
        "metadata_warning": meta_error,
    }
    dump_last_job(settings, job)

    note = "文档已下载，媒体已落到 static/。"
    if slug:
        note += f" 识别到 slug={slug} lang={lang}。"
    elif meta_error:
        note += f" 元数据尚未完整（{meta_error}），补全后再 convert-website。"

    return DownloadResult(
        status="ok",
        message=note,
        token=doc_ref.token,
        kind=doc_ref.kind,
        document_id=document_id,
        doc_url=doc_url,
        slug=slug,
        lang=lang,
        section=section,
        raw_markdown_path=relpath(raw_path),
        processed_markdown_path=relpath(processed_path),
        xml_path=relpath(xml_path) if xml else "",
        featured_image=featured,
        paths=[relpath(raw_path), relpath(processed_path)],
    )
