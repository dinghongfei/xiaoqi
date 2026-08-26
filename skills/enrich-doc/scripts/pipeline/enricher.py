"""Inspect a Feishu doc and write Agent-generated metadata to cloud or local files."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from feishu import lark_cmds
from feishu.client import build_enrichment_xml, value_for_metadata_table
from feishu.payload import document_from_fetch
from last_job import abs_from_job, job_dir, load_last_job, relpath, update_last_job
from media.downloader import (
    IMAGE_TAG_PATTERN,
    IMG_TAG_PATTERN,
    MARKDOWN_IMAGE_PATTERN,
)
from parser.doc_content import split_doc_content
from parser.feishu_text import (
    feishu_title_tag_to_atx_h1,
    prepare_feishu_markdown,
    unescape_feishu_text,
)
from parser.message import DocRef
from parser.metadata import (
    DEFAULT_FIELD_HINTS,
    REQUIRED_METADATA_FIELDS,
    MetadataError,
    validate_metadata_fields,
)

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))
_CODE_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.IGNORECASE | re.DOTALL,
)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_HEADING_RE = re.compile(
    r"(?:^#{1,6}\s*图片\s*$)|(?:<h[1-6][^>]*>\s*图片\s*</h[1-6]>)",
    re.IGNORECASE | re.MULTILINE,
)
_DOC_TITLE_RE = re.compile(
    r"<title>\s*(.*?)\s*</title>",
    re.IGNORECASE | re.DOTALL,
)
_ATX_H1_LINE = re.compile(r"^#[^#\n](.*)$")
_ENRICHMENT_H1 = frozenset({"属性", "图片"})

ARTICLE_TEXT_MAX = 20000
DEFAULT_AUTHOR = "小七"
_COVER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class InspectResult:
    status: str  # ready | error
    message: str = ""
    doc_url: str = ""
    doc_title: str = ""
    article_text: str = ""
    need_cover: bool = False
    has_image_heading: bool = False
    default_date: str = ""
    default_author: str = DEFAULT_AUTHOR
    can_edit: bool | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "doc_url": self.doc_url,
            "doc_title": self.doc_title,
            "need_cover": self.need_cover,
            "has_image_heading": self.has_image_heading,
            "default_date": self.default_date,
            "default_author": self.default_author,
            "can_edit": self.can_edit,
            "required_fields": list(REQUIRED_METADATA_FIELDS),
            "field_hints": dict(DEFAULT_FIELD_HINTS),
            "article_text": self.article_text,
        }


@dataclass
class EnrichResult:
    slug: str
    lang: str
    status: str  # enriched | error
    message: str
    metadata: dict = field(default_factory=dict)
    cover_image: str = ""
    need_cover: bool = False
    doc_url: str = ""
    wrote_cloud: bool = False
    local_paths: list[str] = field(default_factory=list)
    enrichment_xml: str = ""
    enrich_xml_path: str = ""


def default_date_cst() -> str:
    return datetime.now(_CST).strftime("%Y-%m-%d")


def doc_has_images(raw_markdown: str) -> bool:
    text = prepare_feishu_markdown(raw_markdown)
    for pattern in (IMAGE_TAG_PATTERN, IMG_TAG_PATTERN, MARKDOWN_IMAGE_PATTERN):
        if pattern.search(text):
            return True
    return False


def doc_has_image_heading(raw_markdown: str) -> bool:
    """True when the doc already has a top-level「图片」heading."""
    text = prepare_feishu_markdown(raw_markdown)
    return bool(_IMAGE_HEADING_RE.search(text))


def image_section_has_media(raw_markdown: str) -> bool:
    """True when「图片」section already contains an embedded image."""
    text = prepare_feishu_markdown(raw_markdown)
    match = _IMAGE_HEADING_RE.search(text)
    if not match:
        return False
    rest = text[match.end() :]
    next_heading = re.search(r"^#{1,6}\s+\S+", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    for pattern in (IMAGE_TAG_PATTERN, IMG_TAG_PATTERN, MARKDOWN_IMAGE_PATTERN):
        if pattern.search(section):
            return True
    return False


def doc_already_has_metadata(raw_markdown: str) -> bool:
    """True when the doc already has --- plus a parseable metadata table."""
    try:
        split_doc_content(raw_markdown)
        return True
    except MetadataError:
        return False


def extract_feishu_doc_title(raw_markdown: str) -> str:
    """Extract Feishu document title from lark-cli markdown <title> tag."""
    match = _DOC_TITLE_RE.search(raw_markdown or "")
    if not match:
        return ""
    return unescape_feishu_text(match.group(1)).strip()


def extract_article_text(raw_markdown: str) -> str:
    """Reduce Feishu markdown export to plain text for the Agent."""
    text = prepare_feishu_markdown(raw_markdown)
    text = MARKDOWN_IMAGE_PATTERN.sub("", text)
    text = IMAGE_TAG_PATTERN.sub("", text)
    text = IMG_TAG_PATTERN.sub("", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def parse_metadata_json(content: str) -> dict:
    raw = _strip_json_fence(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MetadataError(f"元数据不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise MetadataError("元数据 JSON 根节点必须是对象")
    return data


def _md_cell(text: str) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def build_enrichment_markdown(
    metadata: dict,
    *,
    cover_image_md: str | None = None,
    include_image_heading: bool = True,
    include_image_section: bool = False,
) -> str:
    """Markdown equivalent of the Feishu 属性 table, parseable by split_doc_content."""
    rows: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        value = value_for_metadata_table(field, metadata.get(field, ""))
        hint = DEFAULT_FIELD_HINTS.get(field, field)
        rows.append(f"| {_md_cell(field)} | {_md_cell(hint)} | {_md_cell(value)} |")
    parts = ["# 属性", "", *rows, ""]
    if include_image_section:
        if include_image_heading:
            parts.extend(["# 图片", ""])
        image_md = (cover_image_md or "").strip()
        if image_md:
            parts.extend([image_md, ""])
    parts.append("---")
    return "\n".join(parts) + "\n"


def _split_leading_doc_title_h1(text: str) -> tuple[str, str]:
    """Keep original first-line H1 (Feishu doc title). Returns (title_block, rest)."""
    if not text:
        return "", ""
    lines = text.splitlines(keepends=True)
    first = lines[0]
    core = first.rstrip("\r\n")
    match = _ATX_H1_LINE.match(core)
    if not match:
        return "", text
    heading = match.group(1).strip()
    if heading in _ENRICHMENT_H1:
        return "", text
    rest = "".join(lines[1:]).lstrip("\n")
    return core + "\n\n", rest


def prepend_enrichment_markdown(
    existing: str, prefix: str, *, doc_title: str = ""
) -> str:
    """Insert 属性/图片 after the document title H1, then the article body.

    ``doc_title`` is the raw.md ``<title>`` text when writing processed.md.
    A leading ``<title>`` in ``existing`` is converted to ``# title`` and not kept.
    """
    text = feishu_title_tag_to_atx_h1(existing or "")
    stripped = text.lstrip()
    lead = text[: len(text) - len(stripped)]
    enrichment = prefix.rstrip() + "\n\n"
    title = (doc_title or "").strip() or extract_feishu_doc_title(existing or "")
    first_h1, rest = _split_leading_doc_title_h1(stripped)
    if title:
        heading_text = first_h1.lstrip("#").strip() if first_h1 else ""
        if heading_text != title:
            rest = stripped
        return f"{lead}# {title}\n\n{enrichment}{rest}"
    return f"{lead}{first_h1}{enrichment}{rest}"


def _safe_job_token(token: str) -> str:
    safe = "".join(ch for ch in token if ch.isalnum() or ch in ("-", "_"))
    return safe or "unknown"


def _job_matches(job: dict, doc_ref: DocRef, document_id: str = "") -> bool:
    if job.get("token") == doc_ref.token:
        return True
    if document_id and job.get("document_id") == document_id:
        return True
    return False


def find_local_markdown_files(
    settings: Settings | None,
    doc_ref: DocRef,
    *,
    document_id: str = "",
    include_raw: bool = True,
) -> list[Path]:
    """Locate already-downloaded processed.md (and optionally raw.md). Does not create dirs."""
    if settings is None:
        return []
    seen: set[Path] = set()
    paths: list[Path] = []

    def add(path: Path | None) -> None:
        if path is None or not path.is_file():
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        paths.append(path)

    tokens = [doc_ref.token]
    if document_id and document_id != doc_ref.token:
        tokens.append(document_id)

    jobs_dir = Path(settings.jobs_dir)
    for token in tokens:
        work = jobs_dir / _safe_job_token(token)
        add(work / "processed.md")
        if include_raw:
            add(work / "raw.md")

    job = load_last_job(settings)
    if job and _job_matches(job, doc_ref, document_id):
        add(abs_from_job(settings, job.get("processed_markdown_path")))
        if include_raw:
            add(abs_from_job(settings, job.get("raw_markdown_path")))

    paths.sort(key=lambda p: (0 if p.name == "processed.md" else 1, str(p)))
    return paths


def local_doc_already_has_metadata(
    settings: Settings | None,
    doc_ref: DocRef,
    *,
    document_id: str = "",
) -> bool:
    for path in find_local_markdown_files(
        settings, doc_ref, document_id=document_id, include_raw=False
    ):
        try:
            if doc_already_has_metadata(path.read_text(encoding="utf-8")):
                return True
        except OSError:
            continue
    return False


class Enricher:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def _missing_markdown_message(self, doc_ref: DocRef) -> str:
        doc = doc_ref.token
        wiki_line = ""
        if doc_ref.kind == "wiki":
            wiki_line = (
                f"知识库请先：{lark_cmds.inspect_wiki(doc_ref.token)}\n"
                "用返回的 data.token 作为 docx token，再 fetch。\n"
            )
        dest = ""
        if self.settings is not None:
            dest = relpath(
                Path(self.settings.jobs_dir) / _safe_job_token(doc_ref.token) / "raw.md"
            )
        dest_line = f"把 fetch 的 stdout 写入 {dest}（JSON 或 markdown 均可）\n" if dest else ""
        return (
            f"❌ 还没有正文稿。{lark_cmds.AUTH_HINT}\n"
            f"{wiki_line}"
            f"请先执行：{lark_cmds.fetch_markdown(doc)}\n"
            f"{dest_line}"
            "或给 inspect/apply 传入 --markdown。"
        )

    def _load_markdown(
        self,
        doc_ref: DocRef,
        *,
        markdown_path: Path | None = None,
        markdown_text: str | None = None,
        document_id: str = "",
    ) -> tuple[str, str] | None:
        if markdown_text is not None:
            content, fetched_id = document_from_fetch(markdown_text)
            return content, (document_id or fetched_id)
        if markdown_path is not None:
            if not markdown_path.is_file():
                return None
            content, fetched_id = document_from_fetch(
                markdown_path.read_text(encoding="utf-8")
            )
            return content, (document_id or fetched_id)
        located = find_local_markdown_files(
            self.settings, doc_ref, document_id=document_id, include_raw=True
        )
        raw_files = [p for p in located if p.name == "raw.md"]
        processed_files = [p for p in located if p.name == "processed.md"]
        chosen = raw_files + processed_files + located
        if not chosen:
            return None
        content, fetched_id = document_from_fetch(chosen[0].read_text(encoding="utf-8"))
        return content, (document_id or fetched_id)

    def _write_enrich_xml(self, doc_ref: DocRef, xml: str) -> Path | None:
        if self.settings is None:
            return None
        work = job_dir(self.settings, doc_ref.token)
        path = work / "enrich.xml"
        path.write_text(xml, encoding="utf-8")
        return path

    def _writeback_message(
        self,
        doc_ref: DocRef,
        *,
        xml_path: Path | None,
        document_id: str,
        local_labels: list[str],
        need_cover: bool = False,
        cover_image: str = "",
    ) -> str:
        doc = (document_id or doc_ref.token).strip()
        page_id = document_id or "<page_id>"
        xml_arg = relpath(xml_path) if xml_path is not None else "data/jobs/<token>/enrich.xml"
        after_xml = (
            relpath(xml_path.with_name("after.xml"))
            if xml_path is not None
            else "data/jobs/<token>/after.xml"
        )
        parts = [
            "补全完成（已写入本地"
            + (f" {', '.join(local_labels)}" if local_labels else "稿")
            + "）。写回飞书请由 Agent 执行 lark-cli，不要加 --profile 或 --as：",
            lark_cmds.docs_append_xml(doc, xml_arg),
            lark_cmds.fetch_xml_with_ids(doc),
            f"把 with-ids XML 写入 {after_xml} 后执行：",
            f"uv run python skills/enrich-doc/scripts/run.py enrichment-ids --xml '{after_xml}'",
            lark_cmds.docs_move_blocks(page_id, "<block_ids>"),
        ]
        if need_cover:
            cover = cover_image or (
                relpath(Path(self.settings.jobs_dir) / _safe_job_token(doc_ref.token) / "cover.png")
                if self.settings is not None
                else "data/jobs/<token>/cover.png"
            )
            if self.settings is not None:
                work = Path(self.settings.jobs_dir) / _safe_job_token(doc_ref.token)
                raw_md = relpath(work / "raw.md")
                raw_xml = relpath(work / "raw.xml")
            else:
                raw_md = "data/jobs/<token>/raw.md"
                raw_xml = "data/jobs/<token>/raw.xml"
            parts.extend(
                [
                    "封面图插入云文档（不要把生图提示词或封面图写进本地 processed.md）：",
                    lark_cmds.media_insert(doc, cover),
                    "把 media-insert 返回的 block_id 移到「图片」标题后面：",
                    lark_cmds.docs_move_blocks("<图片标题id>", "<image_block_id>"),
                    "插图完成后必须重新拉取云文档并跑 download-feishu-doc，用下载结果覆盖本地稿，保证与飞书一致：",
                    lark_cmds.fetch_markdown(doc),
                    f"把 markdown 写入 {raw_md}",
                    lark_cmds.fetch_xml(doc),
                    f"把 xml 写入 {raw_xml}",
                    lark_cmds.download_skill(doc_ref.token, kind=doc_ref.kind),
                ]
            )
        return "\n".join(parts)

    def _stage_cover_image(self, src: Path, doc_ref: DocRef) -> Path:
        suffix = src.suffix.lower()
        if suffix not in _COVER_SUFFIXES:
            suffix = ".png"
        dest = job_dir(self.settings, doc_ref.token) / f"cover{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest

    def _write_local_enrichment(
        self,
        doc_ref: DocRef,
        *,
        document_id: str,
        metadata: dict,
        include_image_section: bool,
        include_image_heading: bool,
        cover_image_md: str | None,
        source_markdown: str = "",
    ) -> list[Path]:
        located = find_local_markdown_files(
            self.settings, doc_ref, document_id=document_id
        )
        raw_title = extract_feishu_doc_title(source_markdown)
        for path in located:
            if path.name != "raw.md":
                continue
            try:
                raw_title = extract_feishu_doc_title(path.read_text(encoding="utf-8")) or raw_title
            except OSError:
                pass
            break
        prefix = build_enrichment_markdown(
            metadata,
            cover_image_md=cover_image_md,
            include_image_heading=include_image_heading,
            include_image_section=include_image_section,
        )
        paths = [path for path in located if path.name == "processed.md"]
        if not paths and self.settings is not None and source_markdown.strip():
            dest = job_dir(self.settings, doc_ref.token) / "processed.md"
            dest.write_text(
                prepend_enrichment_markdown(
                    source_markdown, prefix, doc_title=raw_title
                ),
                encoding="utf-8",
            )
            written = [dest]
        else:
            written = []
            for path in paths:
                existing = path.read_text(encoding="utf-8")
                if doc_already_has_metadata(existing):
                    continue
                updated = prepend_enrichment_markdown(
                    existing, prefix, doc_title=raw_title
                )
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(updated, encoding="utf-8")
                tmp.replace(path)
                written.append(path)
        if written and self.settings is not None:
            job = load_last_job(self.settings)
            if job and _job_matches(job, doc_ref, document_id):
                update_last_job(
                    self.settings,
                    slug=metadata.get("slug", ""),
                    lang=metadata.get("lang", ""),
                    metadata_warning="",
                )
        return written

    def _local_path_labels(self, paths: list[Path]) -> list[str]:
        labels: list[str] = []
        for path in paths:
            if self.settings is not None:
                labels.append(relpath(path))
            else:
                labels.append(str(path))
        return labels

    def inspect_doc(
        self,
        doc_ref: DocRef,
        *,
        markdown_path: Path | None = None,
        markdown_text: str | None = None,
        document_id: str = "",
    ) -> InspectResult:
        label = doc_ref.label
        doc_url = (doc_ref.url or "").strip()

        loaded = self._load_markdown(
            doc_ref,
            markdown_path=markdown_path,
            markdown_text=markdown_text,
            document_id=document_id,
        )
        if loaded is None:
            return InspectResult(
                status="error",
                message=self._missing_markdown_message(doc_ref),
                doc_url=doc_url,
            )
        raw, document_id = loaded

        if doc_already_has_metadata(raw):
            return InspectResult(
                status="error",
                message=f"❌ [{label}] 已有属性信息，无需补全",
                doc_url=doc_url,
            )

        if local_doc_already_has_metadata(
            self.settings, doc_ref, document_id=document_id
        ):
            return InspectResult(
                status="error",
                message=f"❌ [{label}] 本地已下载文档已有属性信息，无需补全",
                doc_url=doc_url,
            )

        article_text = extract_article_text(raw)
        if not article_text:
            return InspectResult(
                status="error",
                message=f"❌ [{label}] 文档几乎没有文字，没法补全元数据 📭",
                doc_url=doc_url,
            )

        return InspectResult(
            status="ready",
            doc_url=doc_url,
            doc_title=extract_feishu_doc_title(raw),
            article_text=article_text[:ARTICLE_TEXT_MAX],
            need_cover=not image_section_has_media(raw),
            has_image_heading=doc_has_image_heading(raw),
            default_date=default_date_cst(),
            default_author=DEFAULT_AUTHOR,
            can_edit=None,
        )

    def apply_metadata(
        self,
        doc_ref: DocRef,
        data: dict,
        *,
        cover_image: str = "",
        markdown_path: Path | None = None,
        markdown_text: str | None = None,
        document_id: str = "",
    ) -> EnrichResult:
        label = doc_ref.label
        doc_url = (doc_ref.url or "").strip()

        loaded = self._load_markdown(
            doc_ref,
            markdown_path=markdown_path,
            markdown_text=markdown_text,
            document_id=document_id,
        )
        if loaded is None:
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=self._missing_markdown_message(doc_ref),
                doc_url=doc_url,
            )
        raw, document_id = loaded

        if doc_already_has_metadata(raw):
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=f"❌ [{label}] 已有属性信息，无需补全",
                doc_url=doc_url,
            )

        if local_doc_already_has_metadata(
            self.settings, doc_ref, document_id=document_id
        ):
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=f"❌ [{label}] 本地已下载文档已有属性信息，无需补全",
                doc_url=doc_url,
            )

        article_text = extract_article_text(raw)
        if not article_text:
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=f"❌ [{label}] 文档几乎没有文字，没法补全元数据 📭",
                doc_url=doc_url,
            )

        has_image_heading = doc_has_image_heading(raw)
        need_cover = not image_section_has_media(raw)
        payload = dict(data)
        payload.pop("cover_prompt", None)
        if not str(payload.get("author") or "").strip():
            payload["author"] = DEFAULT_AUTHOR
        cover_arg = (cover_image or str(payload.pop("cover_image", "") or "")).strip()
        if not need_cover:
            cover_arg = ""

        staged_cover = ""
        if cover_arg:
            src = Path(cover_arg)
            if not src.is_file():
                return EnrichResult(
                    slug="",
                    lang="",
                    status="error",
                    message=f"❌ [{label}] 找不到封面图：{src}",
                    doc_url=doc_url,
                    need_cover=need_cover,
                )
            suffix = src.suffix.lower()
            if suffix not in _COVER_SUFFIXES:
                return EnrichResult(
                    slug="",
                    lang="",
                    status="error",
                    message=f"❌ [{label}] 封面图须为 png / jpg / webp / gif",
                    doc_url=doc_url,
                    need_cover=need_cover,
                )
            if self.settings is not None:
                dest = self._stage_cover_image(src, doc_ref)
                staged_cover = relpath(dest)
            else:
                staged_cover = src.name

        try:
            metadata = validate_metadata_fields(payload)
        except MetadataError as e:
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=f"❌ [{label}] {e}",
                doc_url=doc_url,
                need_cover=need_cover,
            )

        include_image_section = need_cover
        include_image_heading = include_image_section and not has_image_heading
        xml = build_enrichment_xml(
            metadata,
            include_image_section=include_image_section,
            include_image_heading=include_image_heading,
        )
        xml_path = self._write_enrich_xml(doc_ref, xml)

        try:
            written_local = self._write_local_enrichment(
                doc_ref,
                document_id=document_id,
                metadata=metadata,
                include_image_section=include_image_section,
                include_image_heading=include_image_heading,
                cover_image_md=None,  # cover lives on Feishu; re-download after insert
                source_markdown=raw,
            )
        except Exception as e:
            logger.exception("Enrich local write failed [%s]: %s", label, e)
            return EnrichResult(
                slug=metadata.get("slug", ""),
                lang=metadata.get("lang", ""),
                status="error",
                message=f"❌ [{label}] 写入本地已下载文档失败：{e}",
                metadata=metadata,
                cover_image=staged_cover,
                need_cover=need_cover,
                doc_url=doc_url,
                enrichment_xml=xml,
                enrich_xml_path=relpath(xml_path) if xml_path else "",
            )

        local_labels = self._local_path_labels(written_local)
        if xml_path is not None:
            local_labels = [*local_labels, relpath(xml_path)]
        if staged_cover:
            local_labels = [*local_labels, staged_cover]
        if not local_labels and not xml:
            return EnrichResult(
                slug=metadata.get("slug", ""),
                lang=metadata.get("lang", ""),
                status="error",
                message=(
                    f"❌ [{label}] 本地没有已下载文档可写入。"
                    "请先运行 download-feishu-doc，再补全元数据。"
                ),
                metadata=metadata,
                cover_image=staged_cover,
                need_cover=need_cover,
                doc_url=doc_url,
                enrichment_xml=xml,
            )

        return EnrichResult(
            slug=metadata.get("slug", ""),
            lang=metadata.get("lang", ""),
            status="enriched",
            message=self._writeback_message(
                doc_ref,
                xml_path=xml_path,
                document_id=document_id,
                local_labels=local_labels,
                need_cover=need_cover,
                cover_image=staged_cover,
            ),
            metadata=metadata,
            cover_image=staged_cover,
            need_cover=need_cover,
            doc_url=doc_url,
            wrote_cloud=False,
            local_paths=local_labels,
            enrichment_xml=xml,
            enrich_xml_path=relpath(xml_path) if xml_path else "",
        )
