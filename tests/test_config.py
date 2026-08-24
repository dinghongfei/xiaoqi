"""Settings defaults for the IM adapter."""

from pathlib import Path

from bot.config import BOT_ROOT, Settings, get_settings


def test_defaults_point_at_project_preview():
    settings = Settings()
    assert settings.hugo_deploy_dir == BOT_ROOT / "preview"
    assert settings.preview_dir == BOT_ROOT / "preview"
    assert settings.preview_port == 1314
    assert settings.last_job_path == BOT_ROOT / "data" / "last-job.json"


def test_get_settings_without_env_file(tmp_path: Path):
    missing = tmp_path / "no-such.env"
    settings = get_settings(missing)
    assert settings.feishu_app_id == ""
