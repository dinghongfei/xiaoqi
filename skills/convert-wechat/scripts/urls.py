"""Preview URL helpers."""

from __future__ import annotations


def site_page_url(site_base_url: str, section: str, slug: str, lang: str) -> str:
    base = (site_base_url or "").strip().rstrip("/")
    if not base or not section or not slug:
        return ""
    if lang == "en":
        return f"{base}/en/{section}/{slug}/"
    return f"{base}/{section}/{slug}/"


def wechat_page_url(site_base_url: str, lang: str, slug: str) -> str:
    base = (site_base_url or "").strip().rstrip("/")
    if not base or not lang or not slug:
        return ""
    return f"{base}/_wechat/{lang}/{slug}/"
