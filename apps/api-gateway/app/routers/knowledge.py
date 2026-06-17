from __future__ import annotations

import json
from uuid import uuid4

import redis
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select

from product_ai_shared import TaskStatus
from product_ai_shared.db import (
    document_chunks,
    document_sources,
    documents,
    get_engine,
    ingestion_tasks,
    row_to_dict,
    utcnow,
)

from app.config import settings

router = APIRouter()
QUEUE_NAME = "knowledge:jobs"


def enqueue(job: dict) -> None:
    queue = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    queue.lpush(QUEUE_NAME, json.dumps(job))


@router.post("/knowledge/import")
async def import_knowledge(
    request: Request,
    file: UploadFile | None = File(default=None),
    source_uri: str | None = Form(default=None),
    doc_type: str | None = Form(default=None),
    title: str | None = Form(default=None),
    system_name: str | None = Form(default=None),
    module_name: str | None = Form(default=None),
    environment: str | None = Form(default=None),
    owner: str | None = Form(default=None),
    version: str | None = Form(default=None),
) -> dict[str, str | None]:
    metadata = {
        "doc_type": doc_type,
        "title": title,
        "system_name": system_name,
        "module_name": module_name,
        "environment": environment,
        "owner": owner,
        "version": version,
    }
    metadata = {key: value for key, value in metadata.items() if value}

    if file is None and source_uri is None:
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Expected multipart file upload or JSON body") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        source_uri = body.get("source_uri")
        metadata_fields = {"doc_type", "title", "system_name", "module_name", "environment", "owner", "version"}
        metadata.update({key: value for key, value in body.items() if key in metadata_fields and value})

    if file is None and not source_uri:
        raise HTTPException(status_code=400, detail="source_uri or file is required")

    task_id = f"task_{uuid4().hex}"
    source_id: str | None = None
    now = utcnow()
    engine = get_engine(settings.database_url)

    with engine.begin() as conn:
        if file is not None:
            content = await file.read()
            source_id = f"src_{uuid4().hex}"
            conn.execute(
                document_sources.insert().values(
                    id=source_id,
                    source_uri=source_uri,
                    filename=file.filename or source_id,
                    content_type=file.content_type or "application/octet-stream",
                    content=content,
                    metadata_json=metadata,
                    created_at=now,
                )
            )

        conn.execute(
            ingestion_tasks.insert().values(
                id=task_id,
                kind="knowledge.import",
                status=TaskStatus.QUEUED.value,
                source_id=source_id,
                message="Import task queued",
                metadata_json=metadata,
                created_at=now,
                updated_at=now,
            )
        )

    enqueue(
        {
            "task_id": task_id,
            "kind": "knowledge.import",
            "source_id": source_id,
            "source_uri": source_uri,
            "metadata": metadata,
        }
    )
    return {
        "task_id": task_id,
        "status": TaskStatus.QUEUED.value,
        "source_id": source_id,
        "message": "Import task accepted",
    }


@router.post("/knowledge/reindex")
async def reindex_knowledge() -> dict[str, str]:
    task_id = f"task_{uuid4().hex}"
    now = utcnow()
    engine = get_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(
            ingestion_tasks.insert().values(
                id=task_id,
                kind="knowledge.reindex",
                status=TaskStatus.QUEUED.value,
                message="Reindex task queued",
                created_at=now,
                updated_at=now,
            )
        )
    enqueue({"task_id": task_id, "kind": "knowledge.reindex"})
    return {"task_id": task_id, "status": TaskStatus.QUEUED.value}


@router.get("/knowledge/documents")
async def list_documents(limit: int = 50, offset: int = 0) -> dict:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    engine = get_engine(settings.database_url)
    with engine.begin() as conn:
        total = conn.execute(select(func.count()).select_from(documents)).scalar_one()
        rows = conn.execute(
            select(documents).order_by(documents.c.created_at.desc()).limit(limit).offset(offset)
        ).all()
    return {"total": total, "items": [row_to_dict(row) for row in rows]}


@router.get("/knowledge/documents/{doc_id}/chunks")
async def list_document_chunks(doc_id: str, level: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    query = select(document_chunks).where(document_chunks.c.doc_id == doc_id)
    count_query = select(func.count()).select_from(document_chunks).where(document_chunks.c.doc_id == doc_id)
    if level:
        query = query.where(document_chunks.c.chunk_level == level)
        count_query = count_query.where(document_chunks.c.chunk_level == level)

    engine = get_engine(settings.database_url)
    with engine.begin() as conn:
        total = conn.execute(count_query).scalar_one()
        rows = conn.execute(
            query.order_by(document_chunks.c.chunk_index.asc()).limit(limit).offset(offset)
        ).all()
    return {"total": total, "items": [row_to_dict(row) for row in rows]}
