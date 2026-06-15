from uuid import uuid4

from fastapi import FastAPI

from product_ai_shared import ChatRequest, ChatResponse, Citation

app = FastAPI(title="AI Ops Copilot AI Orchestrator", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-orchestrator"}


@app.post("/internal/chat/complete", response_model=ChatResponse)
async def complete_chat(request: ChatRequest) -> ChatResponse:
    return ChatResponse(
        answer=(
            "阶段 0 已接通 API Gateway 到 AI Orchestrator 的同步调用。"
            f" 后续阶段将在这里为问题“{request.question}”接入 RAG 和 Agent 工作流。"
        ),
        citations=[
            Citation(
                document_id="bootstrap",
                title="Project Bootstrap",
                snippet="This placeholder verifies the service boundary and response contract.",
                score=1.0,
            )
        ],
        trace_id=f"trace_{uuid4().hex}",
    )


@app.post("/internal/retrieve/debug")
async def retrieve_debug(request: ChatRequest) -> dict[str, object]:
    return {"query": request.question, "rewrites": [request.question], "documents": []}

