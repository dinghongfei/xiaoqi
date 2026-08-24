"""Tests for last-job.json session artifacts (Skill copy; adapter only reads)."""

from pathlib import Path

from config import Settings
from last_job import dump_last_job, load_last_job, update_last_job


def test_dump_and_load_last_job(tmp_path: Path):
    settings = Settings(
        last_job_path=tmp_path / "last-job.json",
        jobs_dir=tmp_path / "jobs",
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=tmp_path / "preview",
    )
    dump_last_job(settings, {"token": "TOK", "slug": "hello-preview"})
    data = load_last_job(settings)
    assert data is not None
    assert data["token"] == "TOK"
    assert data["slug"] == "hello-preview"
    assert "updated_at" in data


def test_update_last_job_merges(tmp_path: Path):
    settings = Settings(last_job_path=tmp_path / "last-job.json")
    dump_last_job(settings, {"token": "TOK", "slug": "a"})
    update_last_job(settings, wechat_preview="http://127.0.0.1:1314/_wechat/zh-cn/a/")
    data = load_last_job(settings)
    assert data["token"] == "TOK"
    assert data["wechat_preview"].endswith("/_wechat/zh-cn/a/")
