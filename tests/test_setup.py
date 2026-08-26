"""Project config: .env, skill links. No Feishu app credentials required."""

from pathlib import Path

from bot.initialize import apply_project_config, upsert_env_file


def test_setup_without_credentials_writes_env(tmp_path: Path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "hugo.toml").write_text("baseURL = '/'\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "FEISHU_APP_ID=\nFEISHU_APP_SECRET=\nSITE_BASE_URL=http://127.0.0.1:1314\n",
        encoding="utf-8",
    )
    (tmp_path / "skills").mkdir()

    code = apply_project_config(tmp_path, agents=[])

    assert code == 0
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "SITE_BASE_URL=http://127.0.0.1:1314" in text
    assert "FEISHU_APP_ID=" in text


def test_setup_copies_example_without_filling_secrets(tmp_path: Path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "hugo.toml").write_text("baseURL = '/'\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "FEISHU_APP_ID=\nFEISHU_APP_SECRET=\nSITE_BASE_URL=http://127.0.0.1:1314\n",
        encoding="utf-8",
    )
    (tmp_path / "skills").mkdir()

    code = apply_project_config(tmp_path, agents=[])

    assert code == 0
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FEISHU_APP_ID=cli_test" not in text
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
