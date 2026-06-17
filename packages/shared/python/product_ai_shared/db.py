from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("id", String(length=64), primary_key=True),
    Column("title", String(length=512), nullable=False),
    Column("source_type", String(length=64), nullable=False),
    Column("source_uri", Text),
    Column("doc_type", String(length=64), nullable=False),
    Column("system_name", String(length=128)),
    Column("module_name", String(length=128)),
    Column("environment", String(length=64)),
    Column("owner", String(length=128)),
    Column("version", String(length=64)),
    Column("status", String(length=32), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

document_chunks = Table(
    "document_chunks",
    metadata,
    Column("id", String(length=64), primary_key=True),
    Column("doc_id", String(length=64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("parent_chunk_id", String(length=64), ForeignKey("document_chunks.id", ondelete="CASCADE")),
    Column("chunk_level", String(length=16), nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("page_no", Integer),
    Column("section_title", Text),
    Column("metadata_json", JSON),
    Column("embedding_model", String(length=128), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

document_sources = Table(
    "document_sources",
    metadata,
    Column("id", String(length=64), primary_key=True),
    Column("source_uri", Text),
    Column("filename", String(length=512), nullable=False),
    Column("content_type", String(length=128), nullable=False),
    Column("content", LargeBinary),
    Column("metadata_json", JSON),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

ingestion_tasks = Table(
    "ingestion_tasks",
    metadata,
    Column("id", String(length=64), primary_key=True),
    Column("kind", String(length=64), nullable=False),
    Column("status", String(length=32), nullable=False),
    Column("source_id", String(length=64), ForeignKey("document_sources.id", ondelete="SET NULL")),
    Column("document_id", String(length=64), ForeignKey("documents.id", ondelete="SET NULL")),
    Column("message", Text),
    Column("error", Text),
    Column("metadata_json", JSON),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def utcnow() -> datetime:
    return datetime.utcnow()


def row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row._mapping)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data
