"""Tests for download skill with Agent-fetched local files."""

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


def _settings(tmp_path: Path) -> Settings:
    hugo_root = tmp_path / "site"
    (hugo_root / "static" / "image").mkdir(parents=True)
    (hugo_root / "static" / "video").mkdir(parents=True)
    return Settings(
        hugo_root=hugo_root,
        hugo_deploy_dir=tmp_path / "preview",
        last_job_path=tmp_path / "last-job.json",
        jobs_dir=tmp_path / "jobs",
        state_db_path=tmp_path / "state.db",
        media_compress_enabled=False,
    )


def _seed(settings: Settings, token: str, markdown: str, xml: str = "<doc></doc>") -> Path:
    work = Path(settings.jobs_dir) / token
    work.mkdir(parents=True, exist_ok=True)
    (work / "raw.md").write_text(markdown, encoding="utf-8")
    (work / "raw.xml").write_text(xml, encoding="utf-8")
    return work


def test_download_writes_last_job(tmp_path: Path):
    settings = _settings(tmp_path)
    _seed(settings, "AbCToken", RAW)
    result = download_feishu_doc(
        settings,
        DocRef(kind="docx", token="AbCToken", url="https://example.feishu.cn/docx/AbCToken"),
        section="blog",
    )
    assert result.status == "ok"
    assert result.slug == "demo-slug"
    job = load_last_job(settings)
    assert job["token"] == "AbCToken"
    assert (tmp_path / "jobs" / "AbCToken" / "raw.md").is_file()
    assert (tmp_path / "jobs" / "AbCToken" / "processed.md").is_file()


def test_download_same_token_overwrites_local_files(tmp_path: Path):
    settings = _settings(tmp_path)
    ref = DocRef(
        kind="docx",
        token="AbCToken",
        url="https://example.feishu.cn/docx/AbCToken",
    )
    first_md = RAW.replace("正文里没有媒体。", "第1次正文")
    second_md = RAW.replace("正文里没有媒体。", "第2次正文")
    _seed(settings, "AbCToken", first_md, "<doc>1</doc>")
    first = download_feishu_doc(settings, ref, section="blog")
    _seed(settings, "AbCToken", second_md, "<doc>2</doc>")
    second = download_feishu_doc(settings, ref, section="blog")
    assert first.status == "ok"
    assert second.status == "ok"
    raw = (tmp_path / "jobs" / "AbCToken" / "raw.md").read_text(encoding="utf-8")
    assert "第2次正文" in raw
    assert "第1次正文" not in raw
    assert "重新处理并覆盖本地稿" in second.message


def test_download_keeps_raw_title_tag_and_processed_h1(tmp_path: Path):
    settings = _settings(tmp_path)
    _seed(
        settings,
        "AbCToken",
        "<title>测试飞书云文档转换为公众号文章1</title>\n\n"
        "# 一、什么是具身智能\n\n正文里没有媒体。\n",
    )
    result = download_feishu_doc(
        settings,
        DocRef(kind="docx", token="AbCToken", url="https://example.feishu.cn/docx/AbCToken"),
        section="blog",
    )
    assert result.status == "ok"
    raw = (tmp_path / "jobs" / "AbCToken" / "raw.md").read_text(encoding="utf-8")
    processed = (tmp_path / "jobs" / "AbCToken" / "processed.md").read_text(
        encoding="utf-8"
    )
    assert raw.startswith("<title>测试飞书云文档转换为公众号文章1</title>")
    assert processed.startswith("# 测试飞书云文档转换为公众号文章1\n")
    assert "<title>" not in processed
    assert "# 一、什么是具身智能" in processed


def test_download_missing_markdown_prints_lark_cli(tmp_path: Path):
    settings = _settings(tmp_path)
    result = download_feishu_doc(
        settings,
        DocRef(kind="docx", token="AbCToken", url="https://example.feishu.cn/docx/AbCToken"),
        section="blog",
    )
    assert result.status == "error"
    assert "lark-cli docs +fetch" in result.message
    for line in result.message.splitlines():
        if line.startswith("lark-cli"):
            assert "--profile" not in line
            assert "--as" not in line
    assert "raw.md" in result.message


def test_download_http_image_url_saves_to_job_media(tmp_path: Path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    class Resp:
        content = png
        headers = {"content-type": "image/png"}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("media.downloader.httpx.get", lambda *a, **k: Resp())
    settings = _settings(tmp_path)
    url = (
        "https://internal-api-drive-stream.feishu.cn/space/api/box/"
        "stream/download/authcode/?code=abc"
    )
    md = RAW.replace("正文里没有媒体。", f"![图]({url})\n\n<img src=\"{url}\"/>\n")
    _seed(settings, "AbCToken", md, f'<img src="{url}"/>')
    result = download_feishu_doc(
        settings,
        DocRef(kind="docx", token="AbCToken", url="https://example.feishu.cn/docx/AbCToken"),
        section="blog",
    )
    assert result.status == "ok"
    media_files = list((tmp_path / "jobs" / "AbCToken" / "media").iterdir())
    assert media_files
    processed = (tmp_path / "jobs" / "AbCToken" / "processed.md").read_text(
        encoding="utf-8"
    )
    assert "/image/" in processed
    assert "authcode" not in processed
    static_images = list((tmp_path / "site" / "static" / "image").iterdir())
    assert static_images
