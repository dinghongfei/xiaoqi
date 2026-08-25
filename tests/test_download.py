"""Tests for download skill with a fake Feishu client."""

from pathlib import Path

from config import Settings
from last_job import load_last_job
from parser.message import DocRef
from pipeline.download import download_feishu_doc

RAW = """
| slug | 文件名 | demo-slug |
| lang | 语言 | zh |
| title | 标题 | 示例 |
| date | 时间 | 2026-03-01 |
| author | 作者 | 内容编辑 |
| categories | 分类 | 演示 |
| summary | 摘要 | 摘要 |
---

正文里没有媒体。
"""


class FakeClient:
    def fetch_doc_markdown(self, doc):
        return RAW, "docid"

    def fetch_doc_xml(self, doc):
        return "<doc></doc>"


def test_download_writes_last_job(tmp_path: Path):
    hugo_root = tmp_path / "site"
    (hugo_root / "static" / "image").mkdir(parents=True)
    (hugo_root / "static" / "video").mkdir(parents=True)
    settings = Settings(
        hugo_root=hugo_root,
        hugo_deploy_dir=tmp_path / "preview",
        last_job_path=tmp_path / "last-job.json",
        jobs_dir=tmp_path / "jobs",
        state_db_path=tmp_path / "state.db",
        media_compress_enabled=False,
    )
    result = download_feishu_doc(
        settings,
        FakeClient(),
        DocRef(kind="docx", token="AbCToken", url="https://example.feishu.cn/docx/AbCToken"),
        section="blog",
    )
    assert result.status == "ok"
    assert result.slug == "demo-slug"
    job = load_last_job(settings)
    assert job["token"] == "AbCToken"
    assert (tmp_path / "jobs" / "AbCToken" / "raw.md").is_file()
    assert (tmp_path / "jobs" / "AbCToken" / "processed.md").is_file()


class CountingClient:
    def __init__(self) -> None:
        self.markdown_calls = 0
        self.xml_calls = 0

    def fetch_doc_markdown(self, doc):
        self.markdown_calls += 1
        body = RAW.replace("正文里没有媒体。", f"第{self.markdown_calls}次正文")
        return body, "docid"

    def fetch_doc_xml(self, doc):
        self.xml_calls += 1
        return f"<doc>{self.xml_calls}</doc>"


def test_download_same_token_refetches_and_overwrites(tmp_path: Path):
    hugo_root = tmp_path / "site"
    (hugo_root / "static" / "image").mkdir(parents=True)
    (hugo_root / "static" / "video").mkdir(parents=True)
    settings = Settings(
        hugo_root=hugo_root,
        hugo_deploy_dir=tmp_path / "preview",
        last_job_path=tmp_path / "last-job.json",
        jobs_dir=tmp_path / "jobs",
        state_db_path=tmp_path / "state.db",
        media_compress_enabled=False,
    )
    ref = DocRef(
        kind="docx",
        token="AbCToken",
        url="https://example.feishu.cn/docx/AbCToken",
    )
    client = CountingClient()
    first = download_feishu_doc(settings, client, ref, section="blog")
    second = download_feishu_doc(settings, client, ref, section="blog")
    assert first.status == "ok"
    assert second.status == "ok"
    assert client.markdown_calls == 2
    assert client.xml_calls == 2
    raw = (tmp_path / "jobs" / "AbCToken" / "raw.md").read_text(encoding="utf-8")
    assert "第2次正文" in raw
    assert "第1次正文" not in raw
    assert "重新下载并覆盖本地稿" in second.message
