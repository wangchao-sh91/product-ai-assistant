import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings
from product_ai_shared import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    url = f"{settings.ai_orchestrator_url}/internal/chat/complete"
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=request.model_dump())
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="AI orchestrator unavailable") from exc
    return ChatResponse.model_validate(response.json())

