"""Tests for local public/ deployment."""

from pathlib import Path

from config import Settings
from pipeline.deploy_local import deploy_public


def test_deploy_public_copies_tree(tmp_path: Path):
    hugo_root = tmp_path / "site"
    public_dir = hugo_root / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    nested = public_dir / "assets"
    nested.mkdir()
    (nested / "app.js").write_text("console.log(1)", encoding="utf-8")

    deploy_dir = tmp_path / "deploy"
    settings = Settings(hugo_root=hugo_root, hugo_deploy_dir=deploy_dir)

    result = deploy_public(settings)

    assert result.ok
    assert (deploy_dir / "index.html").read_text(encoding="utf-8") == "<html></html>"
    assert (deploy_dir / "assets" / "app.js").exists()


def test_deploy_public_replaces_existing_target(tmp_path: Path):
    hugo_root = tmp_path / "site"
    public_dir = hugo_root / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "index.html").write_text("new", encoding="utf-8")

    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    (deploy_dir / "old.txt").write_text("old", encoding="utf-8")

    settings = Settings(hugo_root=hugo_root, hugo_deploy_dir=deploy_dir)
    result = deploy_public(settings)

    assert result.ok
    assert (deploy_dir / "index.html").read_text(encoding="utf-8") == "new"
    assert not (deploy_dir / "old.txt").exists()


def test_deploy_public_missing_config(tmp_path: Path):
    hugo_root = tmp_path / "site"
    hugo_root.mkdir()
    settings = Settings(hugo_root=hugo_root, hugo_deploy_dir=None)

    result = deploy_public(settings)

    assert not result.ok
    assert "HUGO_DEPLOY_DIR" in result.message


def test_deploy_public_preserves_wechat_preview(tmp_path: Path):
    hugo_root = tmp_path / "site"
    public_dir = hugo_root / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "index.html").write_text("site", encoding="utf-8")

    deploy_dir = tmp_path / "preview"
    wechat = deploy_dir / "_wechat" / "zh-cn" / "hello"
    wechat.mkdir(parents=True)
    (wechat / "index.html").write_text("wx", encoding="utf-8")

    settings = Settings(hugo_root=hugo_root, hugo_deploy_dir=deploy_dir)
    result = deploy_public(settings)

    assert result.ok
    assert (deploy_dir / "index.html").read_text(encoding="utf-8") == "site"
    assert (deploy_dir / "_wechat" / "zh-cn" / "hello" / "index.html").read_text(
        encoding="utf-8"
    ) == "wx"


def test_deploy_public_missing_public_dir(tmp_path: Path):
    hugo_root = tmp_path / "site"
    hugo_root.mkdir()
    settings = Settings(hugo_root=hugo_root, hugo_deploy_dir=tmp_path / "deploy")

    result = deploy_public(settings)

    assert not result.ok
    assert "public/" in result.message
