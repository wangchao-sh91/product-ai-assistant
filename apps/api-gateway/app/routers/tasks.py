from fastapi import APIRouter

from product_ai_shared import TaskStatus

router = APIRouter()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, str]:
    return {"task_id": task_id, "status": TaskStatus.QUEUED}

