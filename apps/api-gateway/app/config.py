from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "local"
    ai_orchestrator_url: str = Field(default="http://ai-orchestrator:8001")
    redis_url: str = "redis://redis:6379/0"
    database_url: str = "postgresql+psycopg://ai_ops:ai_ops_password@postgres:5432/ai_ops_copilot"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
