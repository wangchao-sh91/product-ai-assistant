from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_id: str
    title: str
    snippet: str
    score: float | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    answer_type: str = "knowledge_qa"
    citations: list[Citation] = Field(default_factory=list)
    trace_id: str | None = None
    session_id: str | None = None


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
