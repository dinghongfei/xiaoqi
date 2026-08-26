"""Inspect a Feishu doc and write Agent-generated metadata to cloud or local files."""

from __future__ import annotations

import json
import logging
import re
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
DEFAULT_AUTHOR = "内容编辑"


@dataclass
class InspectResult:
    status: str  # ready | error
    message: str = ""
    doc_url: str = ""
    doc_title: str = ""
    article_text: str = ""
    need_cover_prompt: bool = False
    has_image_heading: bool = False
    default_date: str = ""
    default_author: str = DEFAULT_AUTHOR
    can_edit: bool | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "doc_url": self.doc_url,
            "doc_title": self.doc_title,
            "need_cover_prompt": self.need_cover_prompt,
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
    cover_prompt: str = ""
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
    cover_prompt: str | None = None,
    include_image_heading: bool = True,
) -> str:
    """Markdown equivalent of the Feishu 属性 table, parseable by split_doc_content."""
    rows: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        value = value_for_metadata_table(field, metadata.get(field, ""))
        hint = DEFAULT_FIELD_HINTS.get(field, field)
        rows.append(f"| {_md_cell(field)} | {_md_cell(hint)} | {_md_cell(value)} |")
    parts = ["# 属性", "", *rows, ""]
    prompt = (cover_prompt or "").strip()
    if prompt:
        if include_image_heading:
            parts.extend(["# 图片", ""])
        parts.extend([prompt, ""])
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
        doc = (doc_ref.url or "").strip() or doc_ref.token
        wiki_line = ""
        if doc_ref.kind == "wiki":
            wiki_url = doc or f"https://open.feishu.cn/wiki/{doc_ref.token}"
            wiki_line = (
                f"知识库请先：{lark_cmds.inspect_wiki(wiki_url)}\n"
                "用返回的 data.token 作为 docx token，再 fetch。\n"
            )
        dest = ""
        if self.settings is not None:
            dest = relpath(
                Path(self.settings.jobs_dir) / _safe_job_token(doc_ref.token) / "raw.md"
            )
        dest_line = f"把 data.document.content 写入 {dest}\n" if dest else ""
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
    ) -> str:
        doc = (doc_ref.url or "").strip() or document_id or doc_ref.token
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
        return "\n".join(parts)

    def _write_local_enrichment(
        self,
        doc_ref: DocRef,
        *,
        document_id: str,
        metadata: dict,
        cover_prompt: str,
        include_image_heading: bool,
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
            cover_prompt=cover_prompt or None,
            include_image_heading=include_image_heading,
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
            need_cover_prompt=not image_section_has_media(raw),
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
        cover_prompt: str = "",
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
        prompt = (cover_prompt or str(payload.pop("cover_prompt", "") or "")).strip()
        if need_cover:
            if not prompt:
                return EnrichResult(
                    slug="",
                    lang="",
                    status="error",
                    message=f"❌ [{label}] 缺少封面图提示词 cover_prompt",
                    doc_url=doc_url,
                )
        else:
            prompt = ""

        try:
            metadata = validate_metadata_fields(payload)
        except MetadataError as e:
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=f"❌ [{label}] {e}",
                doc_url=doc_url,
            )

        include_image_heading = bool(prompt) and not has_image_heading
        xml = build_enrichment_xml(
            metadata,
            cover_prompt=prompt or None,
            include_image_heading=include_image_heading,
        )
        xml_path = self._write_enrich_xml(doc_ref, xml)

        try:
            written_local = self._write_local_enrichment(
                doc_ref,
                document_id=document_id,
                metadata=metadata,
                cover_prompt=prompt,
                include_image_heading=include_image_heading,
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
                cover_prompt=prompt,
                doc_url=doc_url,
                enrichment_xml=xml,
                enrich_xml_path=relpath(xml_path) if xml_path else "",
            )

        local_labels = self._local_path_labels(written_local)
        if xml_path is not None:
            local_labels = [*local_labels, relpath(xml_path)]
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
                cover_prompt=prompt,
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
            ),
            metadata=metadata,
            cover_prompt=prompt,
            doc_url=doc_url,
            wrote_cloud=False,
            local_paths=local_labels,
            enrichment_xml=xml,
            enrich_xml_path=relpath(xml_path) if xml_path else "",
        )
