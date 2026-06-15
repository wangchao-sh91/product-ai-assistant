from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from product_ai_shared import TaskStatus

router = APIRouter()


class ImportRequest(BaseModel):
    source_uri: str
    doc_type: str = "markdown"


@router.post("/knowledge/import")
async def import_knowledge(request: ImportRequest) -> dict[str, str]:
    task_id = f"task_{uuid4().hex}"
    return {
        "task_id": task_id,
        "status": TaskStatus.QUEUED,
        "message": f"Import task accepted for {request.source_uri}",
    }


@router.post("/knowledge/reindex")
async def reindex_knowledge() -> dict[str, str]:
    task_id = f"task_{uuid4().hex}"
    return {"task_id": task_id, "status": TaskStatus.QUEUED}

