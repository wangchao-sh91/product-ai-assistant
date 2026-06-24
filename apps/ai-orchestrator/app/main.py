from fastapi import FastAPI, HTTPException

from product_ai_shared import ChatRequest, ChatResponse

from app.agents.incident import IncidentWorkflow, LLMAPIError
from app.retrieval.rag import RagPipeline

app = FastAPI(title="AI Ops Copilot AI Orchestrator", version="0.1.0")
rag = RagPipeline()
workflow = IncidentWorkflow(rag)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-orchestrator"}


@app.post("/internal/chat/complete", response_model=ChatResponse)
async def complete_chat(request: ChatRequest) -> ChatResponse:
    try:
        return workflow.complete(request)
    except LLMAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/internal/retrieve/debug")
async def retrieve_debug(request: ChatRequest) -> dict[str, object]:
    return rag.debug_retrieve(request)
