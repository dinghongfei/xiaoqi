"""Project config: credentials, .env, skill links."""

from pathlib import Path

from bot.initialize import EXIT_MISSING_CREDENTIALS, apply_project_config, upsert_env_file


def test_setup_without_credentials_returns_2(tmp_path: Path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "hugo.toml").write_text("baseURL = '/'\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("FEISHU_APP_ID=\nFEISHU_APP_SECRET=\n", encoding="utf-8")
    (tmp_path / "skills").mkdir()

    code = apply_project_config(tmp_path)

    assert code == EXIT_MISSING_CREDENTIALS
    assert not (tmp_path / ".env").exists()


def test_setup_writes_env_from_flags(tmp_path: Path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "hugo.toml").write_text("baseURL = '/'\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "FEISHU_APP_ID=\nFEISHU_APP_SECRET=\nSITE_BASE_URL=http://127.0.0.1:1314\n",
        encoding="utf-8",
    )
    (tmp_path / "skills").mkdir()

    code = apply_project_config(
        tmp_path,
        app_id="cli_test",
        app_secret="secret_test",
        agents=[],
    )

    assert code == 0
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FEISHU_APP_ID=cli_test" in text
    assert "FEISHU_APP_SECRET=secret_test" in text
    assert "SITE_BASE_URL=http://127.0.0.1:1314" in text


def test_upsert_env_updates_existing_keys(tmp_path: Path):
    (tmp_path / ".env.example").write_text("FEISHU_APP_ID=\nFEISHU_APP_SECRET=\n", encoding="utf-8")
    dest = upsert_env_file(tmp_path, {"FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "b"})
    upsert_env_file(tmp_path, {"FEISHU_APP_ID": "c"})
    text = dest.read_text(encoding="utf-8")
    assert "FEISHU_APP_ID=c" in text
    assert "FEISHU_APP_SECRET=b" in text


def test_setup_reuses_existing_env(tmp_path: Path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "hugo.toml").write_text("baseURL = '/'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("FEISHU_APP_ID=cli_old\nFEISHU_APP_SECRET=sec_old\n", encoding="utf-8")
    (tmp_path / "skills").mkdir()

    code = apply_project_config(tmp_path, agents=[])

    assert code == 0
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FEISHU_APP_ID=cli_old" in text
