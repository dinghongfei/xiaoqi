"""Process a Feishu cloud doc already fetched by the Agent via lark-cli."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import Settings
from feishu import lark_cmds
from feishu.payload import document_from_fetch
from hugo.paths import find_existing_section
from last_job import dump_last_job, job_dir, relpath
from media.compress import MediaCompressor
from media.downloader import MediaMissingError, MediaProcessor
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


def _read_fetch_file(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    content, document_id = document_from_fetch(text)
    return content, document_id


def download_feishu_doc(
    settings: Settings,
    doc_ref: DocRef,
    *,
    section: str = "blog",
    markdown_path: Path | None = None,
    xml_path: Path | None = None,
    media_dir: Path | None = None,
    document_id: str = "",
) -> DownloadResult:
    label = doc_ref.label
    doc_url = (doc_ref.url or "").strip()
    work = job_dir(settings, doc_ref.token)
    raw_path = work / "raw.md"
    default_xml = work / "raw.xml"
    processed_path = work / "processed.md"
    source_md = markdown_path or raw_path
    source_xml = xml_path or default_xml
    media_root = media_dir or (work / "media")

    if not source_md.is_file():
        doc = doc_ref.token
        wiki_line = ""
        if doc_ref.kind == "wiki":
            wiki_line = (
                f"知识库请先：{lark_cmds.inspect_wiki(doc_ref.token)}\n"
                "用返回的 data.token 作为 docx token，再 fetch。\n"
            )
        return DownloadResult(
            status="error",
            message=(
                f"❌ 还没有正文文件 {relpath(raw_path)}。{lark_cmds.AUTH_HINT}\n"
                f"{wiki_line}"
                f"请先执行：{lark_cmds.fetch_markdown(doc)}\n"
                f"把 stdout 写入 {relpath(raw_path)}（JSON 或 markdown 均可）\n"
                f"以及：{lark_cmds.fetch_xml(doc)}\n"
                f"把 stdout 写入 {relpath(default_xml)}（JSON 或 xml 均可）"
            ),
            token=doc_ref.token,
            kind=doc_ref.kind,
            doc_url=doc_url,
        )

    try:
        raw, fetched_id = _read_fetch_file(source_md)
        xml = ""
        if source_xml.is_file():
            xml, xml_id = _read_fetch_file(source_xml)
            fetched_id = fetched_id or xml_id
        page_id = (document_id or fetched_id or "").strip()
        media_index = build_media_index_from_xml(xml) if xml else MediaIndex()
    except Exception as exc:
        logger.exception("Read fetched doc failed [%s]", label)
        return DownloadResult(
            status="error",
            message=f"❌ 读取已拉取文档失败：{exc}",
            token=doc_ref.token,
            kind=doc_ref.kind,
            doc_url=doc_url,
        )

    if not raw.strip():
        return DownloadResult(
            status="error",
            message=f"❌ 文档 {label} 内容为空",
            token=doc_ref.token,
            kind=doc_ref.kind,
            doc_url=doc_url,
        )

    refreshed = raw_path.is_file()
    work.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw, encoding="utf-8")

    if xml:
        default_xml.write_text(xml, encoding="utf-8")

    media_root.mkdir(parents=True, exist_ok=True)
    processor = MediaProcessor(
        image_dir=settings.image_dir,
        video_dir=settings.video_dir,
        media_index=media_index,
        media_dir=media_root,
        compressor=MediaCompressor.from_settings(settings),
        token_store=StateStore(settings.state_db_path),
    )

    prepared = prepare_feishu_markdown(raw)
    try:
        processed = processor.process_body(prepared)
    except MediaMissingError as exc:
        if exc.media_type == "url" or str(exc.token).startswith("http"):
            return DownloadResult(
                status="error",
                message=(
                    f"❌ 无法通过 URL 下载媒体：{exc.token}\n"
                    "链接可能已过期。若 XML 里仍有 file token，"
                    f"再用：{lark_cmds.media_download('<token>', str(media_root / '<token>'))}"
                ),
                token=doc_ref.token,
                kind=doc_ref.kind,
                document_id=page_id,
                doc_url=doc_url,
            )
        out = media_root / exc.token
        cmd = lark_cmds.media_download(
            exc.token,
            str(out),
            whiteboard=exc.media_type == "whiteboard",
        )
        return DownloadResult(
            status="error",
            message=(
                f"❌ 缺少媒体 {exc.token}。{lark_cmds.AUTH_HINT}\n"
                f"请先执行：{cmd}\n"
                f"再重新运行 download-feishu-doc。"
            ),
            token=doc_ref.token,
            kind=doc_ref.kind,
            document_id=page_id,
            doc_url=doc_url,
        )

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
        "document_id": page_id,
        "doc_url": doc_url,
        "slug": slug,
        "lang": lang,
        "section": section,
        "raw_markdown_path": relpath(raw_path),
        "processed_markdown_path": relpath(processed_path),
        "xml_path": relpath(default_xml) if default_xml.is_file() else "",
        "featured_image": featured,
        "content_path": "",
        "site_preview": "",
        "wechat_preview": "",
        "metadata_warning": meta_error,
    }
    dump_last_job(settings, job)

    note = (
        "文档已重新处理并覆盖本地稿，媒体已落到 static/。"
        if refreshed
        else "文档已处理，媒体已落到 static/。"
    )
    if slug:
        note += f" 识别到 slug={slug} lang={lang}。"
    elif meta_error:
        note += f" 元数据尚未完整（{meta_error}），补全后再 convert-website。"

    return DownloadResult(
        status="ok",
        message=note,
        token=doc_ref.token,
        kind=doc_ref.kind,
        document_id=page_id,
        doc_url=doc_url,
        slug=slug,
        lang=lang,
        section=section,
        raw_markdown_path=relpath(raw_path),
        processed_markdown_path=relpath(processed_path),
        xml_path=relpath(default_xml) if default_xml.is_file() else "",
        featured_image=featured,
        paths=[relpath(raw_path), relpath(processed_path)],
    )
