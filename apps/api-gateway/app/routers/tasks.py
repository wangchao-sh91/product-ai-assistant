from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy import select

from product_ai_shared.db import get_engine, ingestion_tasks, row_to_dict

from app.config import settings

router = APIRouter()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    engine = get_engine(settings.database_url)
    with engine.begin() as conn:
        row = conn.execute(
            select(ingestion_tasks).where(ingestion_tasks.c.id == task_id)
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return row_to_dict(row)
