"""Inspect a Feishu doc and write Agent-generated metadata to cloud or local files."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from feishu.client import (
    FeishuClient,
    is_edit_permission_error,
    value_for_metadata_table,
)
from last_job import abs_from_job, load_last_job, relpath, update_last_job
from media.downloader import (
    IMAGE_TAG_PATTERN,
    IMG_TAG_PATTERN,
    MARKDOWN_IMAGE_PATTERN,
)
from parser.doc_content import split_doc_content
from parser.feishu_text import prepare_feishu_markdown, unescape_feishu_text
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


def prepend_enrichment_markdown(existing: str, prefix: str) -> str:
    """Insert enrichment after an optional leading <title>, before the original body."""
    text = existing or ""
    stripped = text.lstrip()
    lead = text[: len(text) - len(stripped)]
    enrichment = prefix.rstrip() + "\n\n"
    match = _DOC_TITLE_RE.match(stripped)
    if match:
        title_block = stripped[: match.end()].rstrip() + "\n\n"
        rest = stripped[match.end() :].lstrip("\n")
        return f"{lead}{title_block}{enrichment}{rest}"
    rest = text.lstrip("\n")
    return f"{enrichment}{rest}" if rest else enrichment


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
) -> list[Path]:
    """Locate already-downloaded raw.md / processed.md for this doc. Does not create dirs."""
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
        add(work / "raw.md")

    job = load_last_job(settings)
    if job and _job_matches(job, doc_ref, document_id):
        add(abs_from_job(settings, job.get("processed_markdown_path")))
        add(abs_from_job(settings, job.get("raw_markdown_path")))

    paths.sort(key=lambda p: (0 if p.name == "processed.md" else 1, str(p)))
    return paths


def local_doc_already_has_metadata(
    settings: Settings | None,
    doc_ref: DocRef,
    *,
    document_id: str = "",
) -> bool:
    for path in find_local_markdown_files(settings, doc_ref, document_id=document_id):
        try:
            if doc_already_has_metadata(path.read_text(encoding="utf-8")):
                return True
        except OSError:
            continue
    return False


class Enricher:
    def __init__(self, client: FeishuClient, settings: Settings | None = None):
        self.client = client
        self.settings = settings

    def _probe_can_edit(self, doc_ref: DocRef, document_id: str = "") -> bool | None:
        probe = getattr(self.client, "has_doc_edit_permission", None)
        if not callable(probe):
            return None
        try:
            result = probe(doc_ref, document_id=document_id)
        except TypeError:
            try:
                result = probe(doc_ref)
            except Exception:
                return None
        except Exception:
            return None
        return result if isinstance(result, bool) else None

    def _write_local_enrichment(
        self,
        doc_ref: DocRef,
        *,
        document_id: str,
        metadata: dict,
        cover_prompt: str,
        include_image_heading: bool,
    ) -> list[Path]:
        paths = find_local_markdown_files(
            self.settings, doc_ref, document_id=document_id
        )
        if not paths:
            return []
        prefix = build_enrichment_markdown(
            metadata,
            cover_prompt=cover_prompt or None,
            include_image_heading=include_image_heading,
        )
        written: list[Path] = []
        for path in paths:
            existing = path.read_text(encoding="utf-8")
            if doc_already_has_metadata(existing):
                continue
            updated = prepend_enrichment_markdown(existing, prefix)
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

    def inspect_doc(self, doc_ref: DocRef) -> InspectResult:
        label = doc_ref.label
        doc_url = (doc_ref.url or "").strip()

        try:
            raw, document_id = self.client.fetch_doc_markdown(doc_ref)
        except Exception as e:
            logger.exception("Enrich inspect fetch failed [%s]: %s", label, e)
            return InspectResult(
                status="error",
                message=f"❌ [{label}] 拉取文档失败：{e}",
                doc_url=doc_url,
            )

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
            can_edit=self._probe_can_edit(doc_ref, document_id),
        )

    def apply_metadata(
        self,
        doc_ref: DocRef,
        data: dict,
        *,
        cover_prompt: str = "",
    ) -> EnrichResult:
        label = doc_ref.label
        doc_url = (doc_ref.url or "").strip()

        try:
            raw, document_id = self.client.fetch_doc_markdown(doc_ref)
        except Exception as e:
            logger.exception("Enrich apply fetch failed [%s]: %s", label, e)
            return EnrichResult(
                slug="",
                lang="",
                status="error",
                message=f"❌ [{label}] 拉取文档失败：{e}",
                doc_url=doc_url,
            )

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
        can_edit = self._probe_can_edit(doc_ref, document_id)
        wrote_cloud = False
        if can_edit is not False:
            try:
                self.client.prepend_doc_enrichment(
                    doc_ref,
                    metadata=metadata,
                    cover_prompt=prompt or None,
                    document_id=document_id,
                    include_image_heading=include_image_heading,
                )
                wrote_cloud = True
            except Exception as e:
                if is_edit_permission_error(e):
                    logger.info("Enrich skip cloud write [%s]: %s", label, e)
                    can_edit = False
                else:
                    logger.exception("Enrich write-back failed [%s]: %s", label, e)
                    return EnrichResult(
                        slug=metadata.get("slug", ""),
                        lang=metadata.get("lang", ""),
                        status="error",
                        message=f"❌ [{label}] 写回飞书文档失败：{e}",
                        metadata=metadata,
                        cover_prompt=prompt,
                        doc_url=doc_url,
                    )

        written_local: list[Path] = []
        if not wrote_cloud or find_local_markdown_files(
            self.settings, doc_ref, document_id=document_id
        ):
            try:
                written_local = self._write_local_enrichment(
                    doc_ref,
                    document_id=document_id,
                    metadata=metadata,
                    cover_prompt=prompt,
                    include_image_heading=include_image_heading,
                )
            except Exception as e:
                logger.exception("Enrich local write failed [%s]: %s", label, e)
                if not wrote_cloud:
                    return EnrichResult(
                        slug=metadata.get("slug", ""),
                        lang=metadata.get("lang", ""),
                        status="error",
                        message=f"❌ [{label}] 写入本地已下载文档失败：{e}",
                        metadata=metadata,
                        cover_prompt=prompt,
                        doc_url=doc_url,
                    )

        local_labels = self._local_path_labels(written_local)
        if wrote_cloud:
            message = (
                f"补全完成（已写回飞书云文档，并更新本地已下载文档 {', '.join(local_labels)}）。"
                if local_labels
                else ""
            )
            return EnrichResult(
                slug=metadata.get("slug", ""),
                lang=metadata.get("lang", ""),
                status="enriched",
                message=message,
                metadata=metadata,
                cover_prompt=prompt,
                doc_url=doc_url,
                wrote_cloud=True,
                local_paths=local_labels,
            )

        if local_labels:
            return EnrichResult(
                slug=metadata.get("slug", ""),
                lang=metadata.get("lang", ""),
                status="enriched",
                message=(
                    f"补全完成（无云文档编辑权限，已写入本地已下载文档 "
                    f"{', '.join(local_labels)}）。"
                ),
                metadata=metadata,
                cover_prompt=prompt,
                doc_url=doc_url,
                wrote_cloud=False,
                local_paths=local_labels,
            )

        return EnrichResult(
            slug=metadata.get("slug", ""),
            lang=metadata.get("lang", ""),
            status="error",
            message=(
                f"❌ [{label}] 机器人没有该文档的编辑权限，本地也没有已下载文档可写入。"
                "请先运行 download-feishu-doc，再补全元数据。"
            ),
            metadata=metadata,
            cover_prompt=prompt,
            doc_url=doc_url,
        )
