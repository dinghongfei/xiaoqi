"""Tests for deploy-cloud Skill: sk required, empty bucket = 未开通."""

from pathlib import Path
from unittest.mock import patch

from config import Settings
from pipeline.deploy_cloud import deploy_cloud
from pipeline.step_result import StepResult


def test_deploy_cloud_rejects_missing_sk(tmp_path: Path):
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=tmp_path / "preview",
        publish_secret_key="demo-sk",
        oss_bucket="oss://bucket/www/",
    )
    result = deploy_cloud(settings, secret_key="")
    assert not result.ok
    assert "sk" in result.message.lower() or "拒绝" in result.message


def test_deploy_cloud_rejects_wrong_sk(tmp_path: Path):
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=tmp_path / "preview",
        publish_secret_key="demo-sk",
        oss_bucket="oss://bucket/www/",
    )
    result = deploy_cloud(settings, secret_key="nope")
    assert not result.ok
    assert "不正确" in result.message


def test_deploy_cloud_empty_bucket_is_not_open(tmp_path: Path):
    preview = tmp_path / "preview"
    preview.mkdir()
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        publish_secret_key="demo-sk",
        oss_bucket="",
    )
    result = deploy_cloud(settings, secret_key="demo-sk")
    assert not result.ok
    assert "未开通" in result.message


def test_deploy_cloud_uploads_preview(tmp_path: Path):
    preview = tmp_path / "preview"
    preview.mkdir()
    (preview / "index.html").write_text("ok", encoding="utf-8")
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        publish_secret_key="demo-sk",
        oss_bucket="oss://my-bucket/www/",
        ossutil_bin="aliyun ossutil",
        git_push_enabled=False,
    )
    with patch(
        "pipeline.deploy_cloud.run_command",
        return_value=StepResult(status="ok", message=""),
    ) as run_command:
        result = deploy_cloud(settings, secret_key="demo-sk")
    assert result.ok
    cmd = run_command.call_args[0][0]
    assert cmd[:2] == ["aliyun", "ossutil"]
    assert f"{preview.resolve()}/" in cmd
    assert "oss://my-bucket/www/" in cmd
