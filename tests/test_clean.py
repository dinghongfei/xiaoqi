"""clean-generated Skill: preview/_wechat, jobs, last-job.json only."""

from pathlib import Path

from config import Settings
from pipeline.clean import clean_generated


def test_clean_generated_removes_wechat_jobs_and_last_job(tmp_path: Path):
    preview = tmp_path / "preview"
    wechat = preview / "_wechat"
    wechat.mkdir(parents=True)
    (wechat / "index.html").write_text("x", encoding="utf-8")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "tok").mkdir()
    last_job = tmp_path / "last-job.json"
    last_job.write_text("{}", encoding="utf-8")

    settings = Settings(
        hugo_deploy_dir=preview,
        jobs_dir=jobs,
        last_job_path=last_job,
    )
    result = clean_generated(settings)
    assert result.ok
    assert not wechat.exists()
    assert not jobs.exists()
    assert not last_job.exists()


def test_clean_generated_noop(tmp_path: Path):
    settings = Settings(
        hugo_deploy_dir=tmp_path / "preview",
        jobs_dir=tmp_path / "jobs",
        last_job_path=tmp_path / "missing.json",
    )
    result = clean_generated(settings)
    assert result.ok
    assert "没有需要清理" in result.message
