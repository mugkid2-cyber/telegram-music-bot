"""Схема БД модуля «Цитатник» и dataclass-обёртки над строками aiosqlite."""
from __future__ import annotations

import dataclasses
import datetime as dt

import aiosqlite

QUOTES_SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes_message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    user_full_name TEXT NOT NULL,
    user_username TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    text TEXT,
    has_media INTEGER NOT NULL DEFAULT 0,
    media_kind TEXT,
    media_file_id TEXT,
    reply_to_message_id INTEGER,
    date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_quotes_msglog_chat_message
    ON quotes_message_log(chat_id, message_id);

CREATE TABLE IF NOT EXISTS quotes_sticker_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    part_number INTEGER NOT NULL DEFAULT 1,
    pack_name TEXT NOT NULL UNIQUE,
    pack_title TEXT NOT NULL,
    sticker_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, part_number)
);
CREATE INDEX IF NOT EXISTS idx_quotes_packs_chat
    ON quotes_sticker_packs(chat_id);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    pack_id INTEGER NOT NULL REFERENCES quotes_sticker_packs(id),
    sticker_file_id TEXT NOT NULL,
    sticker_file_unique_id TEXT NOT NULL,
    source_message_ids TEXT NOT NULL,
    anchor_message_id INTEGER NOT NULL,
    created_by_user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quotes_chat ON quotes(chat_id);
CREATE INDEX IF NOT EXISTS idx_quotes_file_unique ON quotes(sticker_file_unique_id);
"""


def _parse_dt(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value else None


@dataclasses.dataclass
class MessageLog:
    id: int
    chat_id: int
    message_id: int
    user_id: int
    user_full_name: str
    user_username: str | None
    is_bot: bool
    text: str | None
    has_media: bool
    media_kind: str | None
    media_file_id: str | None
    reply_to_message_id: int | None
    date: dt.datetime | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "MessageLog":
        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            message_id=row["message_id"],
            user_id=row["user_id"],
            user_full_name=row["user_full_name"],
            user_username=row["user_username"],
            is_bot=bool(row["is_bot"]),
            text=row["text"],
            has_media=bool(row["has_media"]),
            media_kind=row["media_kind"],
            media_file_id=row["media_file_id"],
            reply_to_message_id=row["reply_to_message_id"],
            date=_parse_dt(row["date"]),
        )


@dataclasses.dataclass
class QuoteStickerPack:
    id: int
    chat_id: int
    part_number: int
    pack_name: str
    pack_title: str
    sticker_count: int
    status: str  # "open" | "full"

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "QuoteStickerPack":
        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            part_number=row["part_number"],
            pack_name=row["pack_name"],
            pack_title=row["pack_title"],
            sticker_count=row["sticker_count"],
            status=row["status"],
        )


@dataclasses.dataclass
class Quote:
    id: int
    chat_id: int
    pack_id: int
    sticker_file_id: str
    sticker_file_unique_id: str
    source_message_ids: str
    anchor_message_id: int
    created_by_user_id: int

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Quote":
        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            pack_id=row["pack_id"],
            sticker_file_id=row["sticker_file_id"],
            sticker_file_unique_id=row["sticker_file_unique_id"],
            source_message_ids=row["source_message_ids"],
            anchor_message_id=row["anchor_message_id"],
            created_by_user_id=row["created_by_user_id"],
        )

    def source_ids(self) -> list[int]:
        return [int(x) for x in self.source_message_ids.split(",") if x]