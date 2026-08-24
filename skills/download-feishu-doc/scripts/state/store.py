"""SQLite-backed pending document state."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class PendingEntry:
    slug: str
    section: str
    lang: str
    doc_token: str
    metadata: dict
    body_md: str
    chat_id: str
    updated_at: str


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_docs (
                    slug TEXT NOT NULL,
                    section TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    doc_token TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    body_md TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (slug, lang)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_tokens (
                    token TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    web_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (token, media_type)
                )
                """
            )
            conn.commit()

    def upsert(
        self,
        slug: str,
        section: str,
        lang: str,
        doc_token: str,
        metadata: dict,
        body_md: str,
        chat_id: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_docs
                    (slug, section, lang, doc_token, metadata_json, body_md, chat_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug, lang) DO UPDATE SET
                    section=excluded.section,
                    doc_token=excluded.doc_token,
                    metadata_json=excluded.metadata_json,
                    body_md=excluded.body_md,
                    chat_id=excluded.chat_id,
                    updated_at=excluded.updated_at
                """,
                (
                    slug,
                    section,
                    lang,
                    doc_token,
                    json.dumps(metadata, ensure_ascii=False),
                    body_md,
                    chat_id,
                    now,
                ),
            )
            conn.commit()

    def get_by_slug(self, slug: str) -> list[PendingEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_docs WHERE slug = ?",
                (slug,),
            ).fetchall()

        return [
            PendingEntry(
                slug=row["slug"],
                section=row["section"],
                lang=row["lang"],
                doc_token=row["doc_token"],
                metadata=json.loads(row["metadata_json"]),
                body_md=row["body_md"],
                chat_id=row["chat_id"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def delete_slug(self, slug: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_docs WHERE slug = ?", (slug,))
            conn.commit()

    def is_ready(self, slug: str) -> bool:
        entries = self.get_by_slug(slug)
        langs = {e.lang for e in entries}
        return "zh-cn" in langs and "en" in langs

    def get_media_path(self, token: str, media_type: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT web_path FROM media_tokens
                WHERE token = ? AND media_type = ?
                """,
                (token, media_type),
            ).fetchone()
        if row is None:
            return None
        return row["web_path"]

    def set_media_path(self, token: str, media_type: str, web_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO media_tokens (token, media_type, web_path, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(token, media_type) DO UPDATE SET
                    web_path=excluded.web_path,
                    updated_at=excluded.updated_at
                """,
                (token, media_type, web_path, now),
            )
            conn.commit()
