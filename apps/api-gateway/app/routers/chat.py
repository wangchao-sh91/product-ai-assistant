import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings
from product_ai_shared import ChatRequest, ChatResponse
from product_ai_shared.db import chat_messages, chat_sessions, get_engine, row_to_dict, utcnow
from uuid import uuid4

router = APIRouter()


def title_from_question(question: str) -> str:
    normalized = " ".join(question.split())
    return normalized[:80] or "New chat"


def save_chat_turn(request: ChatRequest, response: ChatResponse) -> str:
    session_id = request.session_id or f"sess_{uuid4().hex}"
    now = utcnow()
    engine = get_engine(settings.database_url)
    with engine.begin() as conn:
        if request.session_id is None:
            conn.execute(
                chat_sessions.insert().values(
                    id=session_id,
                    user_id=(request.metadata or {}).get("user_id"),
                    title=title_from_question(request.question),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing = conn.execute(chat_sessions.select().where(chat_sessions.c.id == session_id)).first()
            if existing is None:
                conn.execute(
                    chat_sessions.insert().values(
                        id=session_id,
                        user_id=(request.metadata or {}).get("user_id"),
                        title=title_from_question(request.question),
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                conn.execute(
                    chat_sessions.update().where(chat_sessions.c.id == session_id).values(updated_at=now)
                )

        conn.execute(
            chat_messages.insert().values(
                id=f"msg_{uuid4().hex}",
                session_id=session_id,
                role="user",
                content=request.question,
                created_at=now,
            )
        )
        conn.execute(
            chat_messages.insert().values(
                id=f"msg_{uuid4().hex}",
                session_id=session_id,
                role="assistant",
                content=response.answer,
                answer_type=response.answer_type,
                citations_json=[citation.model_dump() for citation in response.citations],
                trace_id=response.trace_id,
                created_at=now,
            )
        )
    return session_id


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    url = f"{settings.ai_orchestrator_url}/internal/chat/complete"
    async with httpx.AsyncClient(timeout=75) as client:
        try:
            response = await client.post(url, json=request.model_dump())
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="AI orchestrator request timed out") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"AI orchestrator request failed: {exc}") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text or response.reason_phrase
        raise HTTPException(status_code=response.status_code, detail=detail)
    chat_response = ChatResponse.model_validate(response.json())
    chat_response.session_id = save_chat_turn(request, chat_response)
    return chat_response


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    engine = get_engine(settings.database_url)
    with engine.begin() as conn:
        session = conn.execute(chat_sessions.select().where(chat_sessions.c.id == session_id)).first()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = conn.execute(
            chat_messages.select()
            .where(chat_messages.c.session_id == session_id)
            .order_by(chat_messages.c.created_at.asc())
        ).all()
    return {
        "session": row_to_dict(session),
        "messages": [row_to_dict(message) for message in messages],
    }
