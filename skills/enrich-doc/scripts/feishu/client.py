"""Feishu API client backed by lark-cli."""

from __future__ import annotations

import html
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

import httpx

from lark_cli.runner import LarkCliError, LarkCliRunner
from parser.message import DocRef
from parser.metadata import DEFAULT_FIELD_HINTS, REQUIRED_METADATA_FIELDS

logger = logging.getLogger(__name__)

MediaType = Literal["media", "whiteboard"]

_VOID_XML_TAGS = frozenset({"hr", "img", "image", "br", "source"})
_ATTR_HEADING_RE = re.compile(
    r"<h1\b([^>]*)>\s*属性\s*</h1>",
    re.IGNORECASE,
)
_BLOCK_OPEN_RE = re.compile(r"<([a-zA-Z0-9_-]+)(\s[^>]*)?>", re.IGNORECASE)


class FeishuAPIError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def doc_ref_url(doc_ref: DocRef) -> str:
    return f"https://open.feishu.cn/{doc_ref.kind}/{doc_ref.token}"


def _xml_escape(text: str) -> str:
    return html.escape(text, quote=False)


def is_edit_permission_error(exc: BaseException | str) -> bool:
    """True when a Feishu write-back failed because the bot cannot edit the doc."""
    text = str(exc or "")
    lowered = text.lower()
    return (
        "4030004" in text
        or "no permission" in lowered
        or "lacks view or edit" in lowered
        or "没有权限" in text
        or ("编辑" in text and "权限" in text)
        or "edit access" in lowered
    )


def auth_result_from_payload(payload: dict[str, Any]) -> bool | None:
    """Extract drive permission.members auth result. None if the payload is inconclusive."""
    data = payload.get("data")
    candidates: list[dict[str, Any]] = []
    if isinstance(data, dict):
        candidates.append(data)
        nested = data.get("data")
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in ("auth_result", "is_permitted", "has_perm"):
            if key in candidate:
                return bool(candidate[key])
    return None


def format_docs_update_failure(payload: dict[str, Any]) -> str:
    """Turn docs +update failed/partial payload into a user-facing error."""
    data = payload.get("data") or {}
    result = data.get("result")
    warnings = data.get("warnings") or []
    joined = "；".join(str(item) for item in warnings if item)
    text = joined or f"result={result!r}"
    if is_edit_permission_error(text):
        return (
            "机器人没有该文档的编辑权限。"
            "请在飞书文档/知识库把应用机器人加为「可编辑」协作者，"
            "并确认开放平台已开通文档写权限（如 docs:document.content:write / docx:document）后重新发布应用"
        )
    return f"写回文档失败：{text[:500]}"


def ensure_docs_update_ok(payload: dict[str, Any]) -> None:
    """Raise when lark-cli reports ok=true but data.result indicates failure."""
    data = payload.get("data") or {}
    result = data.get("result")
    if result in (None, "success"):
        return
    if result == "partial_success":
        warnings = data.get("warnings") or []
        logger.warning("docs +update partial_success warnings=%s", warnings)
        return
    message = format_docs_update_failure(payload)
    logger.error("docs +update rejected result=%s: %s", result, message)
    raise FeishuAPIError(message)


def _block_id_from_attrs(attrs: str) -> str:
    match = re.search(r'\bid="([^"]+)"', attrs or "")
    return match.group(1) if match else ""


def list_top_level_block_ids(xml: str) -> list[str]:
    """Collect true top-level block ids (does not include nested table cells)."""
    text = re.sub(r"<title\b[^>]*>.*?</title>", "", xml, flags=re.IGNORECASE | re.DOTALL)
    ids: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        while pos < n and text[pos].isspace():
            pos += 1
        if pos >= n:
            break
        if text[pos] != "<":
            pos += 1
            continue
        open_match = _BLOCK_OPEN_RE.match(text, pos)
        if not open_match:
            pos += 1
            continue
        tag = open_match.group(1).lower()
        attrs = open_match.group(2) or ""
        open_end = open_match.end()
        open_raw = text[pos:open_end]
        block_id = _block_id_from_attrs(attrs)
        self_closing = (
            open_raw.rstrip().endswith("/>")
            or tag in _VOID_XML_TAGS
        )
        if self_closing:
            if block_id:
                ids.append(block_id)
            pos = open_end
            continue

        depth = 1
        cursor = open_end
        while cursor < n and depth > 0:
            next_open = re.search(rf"<{tag}\b[^>]*>", text[cursor:], re.IGNORECASE)
            next_close = re.search(rf"</{tag}\s*>", text[cursor:], re.IGNORECASE)
            if next_close is None:
                break
            open_rel = next_open.start() if next_open else None
            close_rel = next_close.start()
            if open_rel is not None and open_rel < close_rel:
                open_tag = next_open.group(0)
                if open_tag.rstrip().endswith("/>"):
                    cursor += next_open.end()
                    continue
                depth += 1
                cursor += next_open.end()
            else:
                depth -= 1
                cursor += next_close.end()
        if block_id:
            ids.append(block_id)
        pos = cursor if cursor > open_end else open_end
    return ids


def find_enrichment_block_ids(xml: str) -> list[str]:
    """Locate top-level blocks starting at h1「属性」through document end."""
    match = _ATTR_HEADING_RE.search(xml)
    if not match:
        return []
    heading_id = _block_id_from_attrs(match.group(1))
    rest_ids = list_top_level_block_ids(xml[match.end() :])
    ids = ([heading_id] if heading_id else []) + rest_ids
    # Keep order, drop empties/dupes
    seen: set[str] = set()
    ordered: list[str] = []
    for block_id in ids:
        if block_id and block_id not in seen:
            seen.add(block_id)
            ordered.append(block_id)
    return ordered


def lang_for_metadata_table(lang: str) -> str:
    """Convert normalized Hugo lang back to user-facing zh/en for the table."""
    raw = (lang or "").strip().lower()
    if raw in ("zh-cn", "zh"):
        return "zh"
    return "en"


def value_for_metadata_table(field: str, value) -> str:
    """Format normalized metadata values for the Feishu three-column table."""
    if field == "lang":
        return lang_for_metadata_table(str(value or ""))
    if field == "date":
        text = str(value or "").strip()
        return text[:10] if len(text) >= 10 else text
    if field == "categories":
        if isinstance(value, list):
            return "，".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()
    return str(value) if value is not None else ""


def build_enrichment_xml(
    metadata: dict,
    *,
    cover_prompt: str | None = None,
    include_image_heading: bool = True,
) -> str:
    """Build write-back XML: 属性(h1) → table → [图片(h1)? → prompt → hr].

    横线只跟在封面提示词后面；已有封面图、不写提示词时，表格下方不写 hr。
    """
    rows: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        value = value_for_metadata_table(field, metadata.get(field, ""))
        hint = DEFAULT_FIELD_HINTS.get(field, field)
        # Wrap cell text in <p> so Feishu keeps third-column values reliably
        rows.append(
            "<tr>"
            f"<td><p>{_xml_escape(field)}</p></td>"
            f"<td><p>{_xml_escape(hint)}</p></td>"
            f"<td><p>{_xml_escape(value)}</p></td>"
            "</tr>"
        )

    parts = [
        "<h1>属性</h1>",
        "<table>",
        '<colgroup><col width="120"/><col width="280"/><col width="360"/></colgroup>',
        "<tbody>",
        *rows,
        "</tbody>",
        "</table>",
    ]
    prompt = (cover_prompt or "").strip()
    if prompt:
        if include_image_heading:
            parts.append("<h1>图片</h1>")
        parts.append(f"<p>{_xml_escape(prompt)}</p>")
        parts.append("<hr/>")
    return "".join(parts)


class FeishuClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        cli_bin: str,
        cli_identity: str,
        cli_profile: str,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.cli = LarkCliRunner(
            bin_path=cli_bin,
            identity=cli_identity,
            profile=cli_profile,
            app_id=app_id,
            app_secret=app_secret,
        )

    def fetch_doc_markdown(self, doc: str | DocRef) -> tuple[str, str]:
        """Fetch document markdown. Returns (content, document_id)."""
        doc_arg = doc_ref_url(doc) if isinstance(doc, DocRef) else doc
        try:
            payload = self.cli.run(
                [
                    "docs",
                    "+fetch",
                    "--api-version",
                    "v2",
                    "--doc",
                    doc_arg,
                    "--doc-format",
                    "markdown",
                ],
                timeout=180,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc

        document = payload.get("data", {}).get("document", {})
        content = document.get("content", "")
        document_id = document.get("document_id", "")
        if not content:
            raise FeishuAPIError(f"文档 {doc_arg} 内容为空")
        return content, document_id

    def fetch_doc_xml(self, doc: str | DocRef) -> str:
        doc_arg = doc if isinstance(doc, str) else doc_ref_url(doc)
        try:
            payload = self.cli.run(
                [
                    "docs",
                    "+fetch",
                    "--api-version",
                    "v2",
                    "--doc",
                    doc_arg,
                    "--doc-format",
                    "xml",
                    "--detail",
                    "full",
                ],
                timeout=180,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc

        content = payload.get("data", {}).get("document", {}).get("content", "")
        if not content:
            raise FeishuAPIError(f"文档 {doc_arg} XML 内容为空")
        return content

    def resolve_doc_token(self, kind: str, token: str) -> str:
        if kind == "docx":
            return token

        if kind == "wiki":
            return self.resolve_wiki_to_docx(token)

        raise FeishuAPIError(f"未知文档类型: {kind}")

    def resolve_wiki_to_docx(self, wiki_token: str) -> str:
        url = f"https://open.feishu.cn/wiki/{wiki_token}"
        try:
            payload = self.cli.run(
                ["drive", "+inspect", "--url", url],
                timeout=60,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc

        data = payload.get("data", {})
        obj_type = data.get("type")
        obj_token = data.get("token")
        if not obj_token:
            raise FeishuAPIError(f"无法解析知识库节点 {wiki_token}")
        if obj_type != "docx":
            raise FeishuAPIError(
                f"暂不支持的知识库文档类型: {obj_type}，当前仅支持新版文档 docx"
            )
        return obj_token

    def download_media(
        self,
        file_token: str,
        *,
        media_type: MediaType = "media",
    ) -> tuple[bytes, str | None]:
        with tempfile.TemporaryDirectory(prefix="bot-media-") as tmp:
            cwd = Path(tmp)
            args = [
                "docs",
                "+media-download",
                "--token",
                file_token,
                "--output",
                "./media",
            ]
            if media_type == "whiteboard":
                args.extend(["--type", "whiteboard"])

            try:
                payload = self.cli.run(args, cwd=cwd, timeout=180)
            except LarkCliError as exc:
                raise FeishuAPIError(str(exc)) from exc

            data = payload.get("data", {})
            saved_path = data.get("saved_path")
            if not saved_path:
                raise FeishuAPIError(f"媒体下载失败: {file_token}")

            path = Path(saved_path)
            if not path.is_absolute():
                path = cwd / path
            content_type = data.get("content_type")
            return path.read_bytes(), content_type

    def download_media_url(self, url: str) -> tuple[bytes, str | None]:
        try:
            resp = httpx.get(url, timeout=120, follow_redirects=True)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type")
        except httpx.HTTPError as exc:
            raise FeishuAPIError(f"下载媒体 URL 失败: {exc}") from exc

    def reply_text(self, message_id: str, text: str) -> None:
        try:
            self.cli.run(
                [
                    "im",
                    "+messages-reply",
                    "--message-id",
                    message_id,
                    "--text",
                    text,
                ],
                timeout=30,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc

    def send_text_to_chat(self, chat_id: str, text: str) -> None:
        try:
            self.cli.run(
                [
                    "im",
                    "+messages-send",
                    "--chat-id",
                    chat_id,
                    "--text",
                    text,
                ],
                timeout=30,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc

    def has_doc_edit_permission(
        self,
        doc: str | DocRef,
        *,
        document_id: str = "",
    ) -> bool | None:
        """Probe whether the bot can edit this doc. None if the probe is inconclusive."""
        token = (document_id or "").strip()
        doc_type = "docx"
        if not token and isinstance(doc, DocRef):
            if doc.kind == "wiki":
                try:
                    token = self.resolve_wiki_to_docx(doc.token)
                except Exception as exc:
                    logger.info("edit permission probe wiki resolve failed: %s", exc)
                    token = doc.token
                    doc_type = "wiki"
            else:
                token = doc.token
        elif not token and isinstance(doc, str):
            token = doc.strip()
        if not token:
            return None
        try:
            payload = self.cli.run(
                [
                    "drive",
                    "permission.members",
                    "auth",
                    "--params",
                    json.dumps({"token": token, "type": doc_type, "action": "edit"}),
                ],
                timeout=30,
            )
        except LarkCliError as exc:
            logger.info("edit permission probe failed token=%s: %s", token, exc)
            return None
        return auth_result_from_payload(payload)

    def fetch_doc_xml_with_ids(self, document_id: str) -> str:
        try:
            payload = self.cli.run(
                [
                    "docs",
                    "+fetch",
                    "--api-version",
                    "v2",
                    "--doc",
                    document_id,
                    "--doc-format",
                    "xml",
                    "--detail",
                    "with-ids",
                ],
                timeout=180,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc
        content = payload.get("data", {}).get("document", {}).get("content", "")
        if not content:
            raise FeishuAPIError(f"文档 {document_id} XML 内容为空")
        return content

    def prepend_doc_enrichment(
        self,
        doc: str | DocRef,
        *,
        metadata: dict,
        cover_prompt: str | None = None,
        document_id: str = "",
        include_image_heading: bool = True,
    ) -> None:
        """Insert 属性/table/[图片/prompt/hr] at document start."""
        doc_arg = doc_ref_url(doc) if isinstance(doc, DocRef) else doc
        page_id = document_id.strip()
        if not page_id:
            _, page_id = self.fetch_doc_markdown(doc)
        if not page_id:
            raise FeishuAPIError(f"无法获取文档 ID：{doc_arg}")

        content = build_enrichment_xml(
            metadata,
            cover_prompt=cover_prompt,
            include_image_heading=include_image_heading,
        )

        # 1) append at end, 2) move only the enrichment top-level blocks to page start.
        # Never move nested table-cell ids — that empties the third column.
        try:
            append_payload = self.cli.run(
                [
                    "docs",
                    "+update",
                    "--doc",
                    page_id,
                    "--command",
                    "append",
                    "--doc-format",
                    "xml",
                    "--content",
                    content,
                ],
                timeout=180,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(str(exc)) from exc
        ensure_docs_update_ok(append_payload)

        try:
            after_xml = self.fetch_doc_xml_with_ids(page_id)
        except Exception as exc:
            raise FeishuAPIError(f"写回后校验拉取失败：{exc}") from exc

        move_ids = find_enrichment_block_ids(after_xml)
        if not move_ids:
            raise FeishuAPIError("写回后未找到「属性」区块，无法移到文档顶部")

        try:
            move_payload = self.cli.run(
                [
                    "docs",
                    "+update",
                    "--doc",
                    page_id,
                    "--command",
                    "block_move_after",
                    "--block-id",
                    page_id,
                    "--src-block-ids",
                    ",".join(move_ids),
                ],
                timeout=180,
            )
        except LarkCliError as exc:
            raise FeishuAPIError(
                f"内容已写入但移到文档顶部失败：{exc}"
            ) from exc
        ensure_docs_update_ok(move_payload)

        slug = value_for_metadata_table("slug", metadata.get("slug", ""))
        try:
            verify_md, _ = self.fetch_doc_markdown(page_id)
        except Exception as exc:
            raise FeishuAPIError(f"写回后校验失败：{exc}") from exc
        head = "\n".join(verify_md.splitlines()[:120])
        missing: list[str] = []
        if "属性" not in head:
            missing.append("标题「属性」")
        if slug and slug not in verify_md:
            missing.append(f"表格值 slug={slug}")
        if cover_prompt and cover_prompt.strip() and cover_prompt.strip() not in verify_md:
            missing.append("封面图提示词")
        if cover_prompt and "---" not in verify_md.splitlines()[:120]:
            missing.append("分隔线 ---")
        if missing:
            logger.error(
                "prepend_doc_enrichment verify failed page_id=%s missing=%s",
                page_id,
                missing,
            )
            raise FeishuAPIError(
                "写回未完整生效，缺少：" + "、".join(missing)
            )