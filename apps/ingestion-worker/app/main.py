from __future__ import annotations

import io
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
import redis
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from product_ai_shared import TaskStatus
from product_ai_shared.db import (
    document_chunks,
    document_sources,
    documents,
    get_engine,
    ingestion_tasks,
    utcnow,
)
from product_ai_shared.embeddings import DEFAULT_EMBEDDING_MODEL, EMBEDDING_DIMENSION, embed_text, tokenize

QUEUE_NAME = "knowledge:jobs"
COLLECTION_NAME = "knowledge_chunks"


@dataclass(frozen=True)
class ParsedBlock:
    content: str
    section_title: str | None = None
    page_no: int | None = None


@dataclass(frozen=True)
class Chunk:
    content: str
    token_count: int
    section_title: str | None
    page_no: int | None


def detect_doc_type(filename: str, content_type: str | None, explicit_type: str | None) -> str:
    if explicit_type:
        return explicit_type.lower()
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".pdf" or content_type == "application/pdf":
        return "pdf"
    return "txt"


def parse_markdown(text: str) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            if current_lines:
                blocks.append(ParsedBlock("\n".join(current_lines).strip(), current_title))
                current_lines = []
            current_title = heading.group(2).strip()
            current_lines.append(line)
            continue
        current_lines.append(line)

    if current_lines:
        blocks.append(ParsedBlock("\n".join(current_lines).strip(), current_title))
    return [block for block in blocks if block.content]


def parse_pdf(content: bytes) -> list[ParsedBlock]:
    reader = PdfReader(io.BytesIO(content))
    blocks: list[ParsedBlock] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append(ParsedBlock(content=text, section_title=f"Page {index}", page_no=index))
    return blocks


def parse_document(content: bytes, doc_type: str) -> list[ParsedBlock]:
    if doc_type == "pdf":
        return parse_pdf(content)

    text = content.decode("utf-8", errors="replace")
    if doc_type == "markdown":
        return parse_markdown(text)
    return [ParsedBlock(content=text.strip())] if text.strip() else []


def chunk_block(block: ParsedBlock, max_tokens: int, overlap_tokens: int) -> list[Chunk]:
    tokens = tokenize(block.content)
    if not tokens:
        return []

    chunks: list[Chunk] = []
    start = 0
    step = max(1, max_tokens - overlap_tokens)
    while start < len(tokens):
        selected = tokens[start : start + max_tokens]
        content = " ".join(selected).strip()
        if content:
            chunks.append(
                Chunk(
                    content=content,
                    token_count=len(selected),
                    section_title=block.section_title,
                    page_no=block.page_no,
                )
            )
        if start + max_tokens >= len(tokens):
            break
        start += step
    return chunks


def build_chunks(blocks: list[ParsedBlock]) -> tuple[list[Chunk], dict[int, list[Chunk]]]:
    parents: list[Chunk] = []
    children_by_parent: dict[int, list[Chunk]] = {}

    for block in blocks:
        for parent in chunk_block(block, max_tokens=1200, overlap_tokens=100):
            parent_index = len(parents)
            parents.append(parent)
            child_block = ParsedBlock(parent.content, section_title=parent.section_title, page_no=parent.page_no)
            children_by_parent[parent_index] = chunk_block(child_block, max_tokens=420, overlap_tokens=70)

    return parents, children_by_parent


def load_source(engine: Engine, job: dict) -> tuple[dict, bytes]:
    source_id = job.get("source_id")
    source_uri = job.get("source_uri")

    if source_id:
        with engine.begin() as conn:
            row = conn.execute(
                select(document_sources).where(document_sources.c.id == source_id)
            ).mappings().first()
        if row is None:
            raise ValueError(f"document source not found: {source_id}")
        content = row["content"]
        if content is None:
            raise ValueError(f"document source has no uploaded content: {source_id}")
        return dict(row), bytes(content)

    if not source_uri:
        raise ValueError("job must include source_id or source_uri")

    if re.match(r"^https?://", source_uri):
        response = httpx.get(source_uri, timeout=30)
        response.raise_for_status()
        filename = Path(source_uri).name or "remote-document"
        return {
            "source_uri": source_uri,
            "filename": filename,
            "content_type": response.headers.get("content-type", "application/octet-stream"),
            "metadata_json": job.get("metadata", {}),
        }, response.content

    path = Path(source_uri)
    if not path.exists():
        raise FileNotFoundError(f"source_uri does not exist in worker container: {source_uri}")
    return {
        "source_uri": source_uri,
        "filename": path.name,
        "content_type": "application/octet-stream",
        "metadata_json": job.get("metadata", {}),
    }, path.read_bytes()


def ensure_qdrant_collection(client: QdrantClient) -> None:
    collections = client.get_collections().collections
    if any(collection.name == COLLECTION_NAME for collection in collections):
        info = client.get_collection(collection_name=COLLECTION_NAME)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        if size == EMBEDDING_DIMENSION:
            return
        client.delete_collection(collection_name=COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=qdrant_models.VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=qdrant_models.Distance.COSINE,
        ),
    )


def recreate_qdrant_collection(client: QdrantClient) -> None:
    collections = client.get_collections().collections
    if any(collection.name == COLLECTION_NAME for collection in collections):
        client.delete_collection(collection_name=COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=qdrant_models.VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=qdrant_models.Distance.COSINE,
        ),
    )


def update_task(engine: Engine, task_id: str, status: TaskStatus, message: str | None = None, error: str | None = None, document_id: str | None = None) -> None:
    values = {"status": status.value, "updated_at": utcnow()}
    if message is not None:
        values["message"] = message
    if error is not None:
        values["error"] = error
    if document_id is not None:
        values["document_id"] = document_id
    with engine.begin() as conn:
        conn.execute(update(ingestion_tasks).where(ingestion_tasks.c.id == task_id).values(**values))


def import_document(engine: Engine, qdrant: QdrantClient, job: dict) -> None:
    task_id = job["task_id"]
    update_task(engine, task_id, TaskStatus.RUNNING, message="Parsing document")

    source, content = load_source(engine, job)
    metadata = dict(source.get("metadata_json") or {})
    metadata.update(job.get("metadata") or {})
    doc_type = detect_doc_type(source["filename"], source.get("content_type"), metadata.get("doc_type"))
    blocks = parse_document(content, doc_type)
    if not blocks:
        raise ValueError("document contains no extractable text")

    parents, children_by_parent = build_chunks(blocks)
    if not parents:
        raise ValueError("document produced no chunks")

    doc_id = f"doc_{uuid4().hex}"
    title = metadata.get("title") or Path(source["filename"]).stem or doc_id
    now = utcnow()

    update_task(engine, task_id, TaskStatus.RUNNING, message="Writing metadata and vector index")
    ensure_qdrant_collection(qdrant)

    points: list[qdrant_models.PointStruct] = []
    with engine.begin() as conn:
        conn.execute(
            documents.insert().values(
                id=doc_id,
                title=title,
                source_type="upload" if job.get("source_id") else "uri",
                source_uri=source.get("source_uri"),
                doc_type=doc_type,
                system_name=metadata.get("system_name"),
                module_name=metadata.get("module_name"),
                environment=metadata.get("environment"),
                owner=metadata.get("owner"),
                version=metadata.get("version"),
                status="indexed",
                created_at=now,
                updated_at=now,
            )
        )

        chunk_index = 0
        for parent_index, parent in enumerate(parents):
            parent_id = str(uuid4())
            conn.execute(
                document_chunks.insert().values(
                    id=parent_id,
                    doc_id=doc_id,
                    parent_chunk_id=None,
                    chunk_level="parent",
                    chunk_index=chunk_index,
                    content=parent.content,
                    token_count=parent.token_count,
                    page_no=parent.page_no,
                    section_title=parent.section_title,
                    metadata_json=metadata,
                    embedding_model=DEFAULT_EMBEDDING_MODEL,
                    created_at=now,
                )
            )
            chunk_index += 1

            for child in children_by_parent[parent_index]:
                child_id = str(uuid4())
                payload = {
                    "chunk_id": child_id,
                    "doc_id": doc_id,
                    "title": title,
                    "section_title": child.section_title,
                    "page_no": child.page_no,
                    "doc_type": doc_type,
                    "source_uri": source.get("source_uri"),
                    **metadata,
                }
                conn.execute(
                    document_chunks.insert().values(
                        id=child_id,
                        doc_id=doc_id,
                        parent_chunk_id=parent_id,
                        chunk_level="child",
                        chunk_index=chunk_index,
                        content=child.content,
                        token_count=child.token_count,
                        page_no=child.page_no,
                        section_title=child.section_title,
                        metadata_json=payload,
                        embedding_model=DEFAULT_EMBEDDING_MODEL,
                        created_at=now,
                    )
                )
                points.append(
                    qdrant_models.PointStruct(
                        id=child_id,
                        vector=embed_text(child.content),
                        payload={**payload, "content": child.content},
                    )
                )
                chunk_index += 1

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    update_task(
        engine,
        task_id,
        TaskStatus.SUCCEEDED,
        message=f"Imported {len(parents)} parent chunks and {len(points)} child chunks",
        document_id=doc_id,
    )


def reindex(engine: Engine, qdrant: QdrantClient, task_id: str) -> None:
    update_task(engine, task_id, TaskStatus.RUNNING, message="Rebuilding Qdrant collection")
    recreate_qdrant_collection(qdrant)

    points: list[qdrant_models.PointStruct] = []
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                document_chunks.c.id,
                document_chunks.c.doc_id,
                document_chunks.c.content,
                document_chunks.c.metadata_json,
                documents.c.title,
                documents.c.doc_type,
                documents.c.source_uri,
            )
            .join(documents, document_chunks.c.doc_id == documents.c.id)
            .where(document_chunks.c.chunk_level == "child")
        ).mappings()
        for row in rows:
            payload = dict(row["metadata_json"] or {})
            payload.update(
                {
                    "chunk_id": row["id"],
                    "doc_id": row["doc_id"],
                    "title": row["title"],
                    "doc_type": row["doc_type"],
                    "source_uri": row["source_uri"],
                    "content": row["content"],
                }
            )
            points.append(
                qdrant_models.PointStruct(
                    id=row["id"],
                    vector=embed_text(row["content"]),
                    payload=payload,
                )
            )
    if points:
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    update_task(engine, task_id, TaskStatus.SUCCEEDED, message=f"Reindexed {len(points)} child chunks")


def process_job(engine: Engine, qdrant: QdrantClient, raw_job: str) -> None:
    job = json.loads(raw_job)
    task_id = job["task_id"]
    try:
        if job["kind"] == "knowledge.import":
            import_document(engine, qdrant, job)
        elif job["kind"] == "knowledge.reindex":
            reindex(engine, qdrant, task_id)
        else:
            raise ValueError(f"unsupported job kind: {job['kind']}")
    except Exception as exc:
        update_task(engine, task_id, TaskStatus.FAILED, error=str(exc), message="Task failed")
        raise


def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://ai_ops:ai_ops_password@postgres:5432/ai_ops_copilot",
    )
    qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")

    engine = get_engine(database_url)
    queue = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=10)
    qdrant = QdrantClient(url=qdrant_url)

    print(f"ingestion-worker started, waiting for jobs from {redis_url}", flush=True)
    while True:
        try:
            item = queue.brpop(QUEUE_NAME, timeout=5)
            if item is None:
                continue
            _, raw_job = item
            process_job(engine, qdrant, raw_job)
        except redis.exceptions.TimeoutError:
            continue
        except Exception as exc:
            print(f"ingestion-worker error: {exc}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
