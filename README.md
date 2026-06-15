# AI Ops Knowledge Copilot

面向研发团队的知识库与故障助手 Copilot。当前仓库采用前后端分离的 monorepo 结构，后端按职责拆分为 API Gateway、AI Orchestrator、Ingestion Worker。

## Architecture

```text
apps/web-ui            Web UI，负责聊天、引用、会话和任务状态展示
apps/api-gateway       对外 API，负责会话、鉴权预留、任务状态和内部服务转发
apps/ai-orchestrator   AI 编排服务，负责 RAG、多 Agent、检索和生成
apps/ingestion-worker  异步 Worker，负责文档入库、索引重建和批量评测
packages/shared        跨服务共享契约与 OpenAPI 产物
infra/compose.yaml     本地开发 Docker Compose
datasets               示例文档与评测数据
docs                   项目补充文档
scripts                本地辅助脚本
```

## Local Start

1. 复制配置：

```bash
cp .env.example .env
```

2. 启动服务：

```bash
docker compose --env-file .env -f infra/compose.yaml up --build
```

3. 访问入口：

```text
Web UI:              http://localhost:3000
API Gateway docs:    http://localhost:8000/docs
AI Orchestrator docs:http://localhost:8001/docs
Qdrant:              http://localhost:6333/dashboard
MinIO Console:       http://localhost:9001
```

## Service Contract

- 前端只调用 API Gateway 的 `/api/*`。
- API Gateway 同步调用 AI Orchestrator 的 `/internal/*`。
- 入库、重建索引、评测等耗时任务通过 Redis 队列交给 Ingestion Worker。
- PostgreSQL 存储业务元数据，Qdrant 存储向量索引，MinIO 存储原始文档对象。

