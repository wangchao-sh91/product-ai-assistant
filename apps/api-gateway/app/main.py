from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, health, knowledge, tasks

app = FastAPI(title="AI Ops Copilot API Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(knowledge.router, prefix="/api", tags=["knowledge"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
