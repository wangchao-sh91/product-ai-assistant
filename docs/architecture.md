# Architecture Notes

## Service Boundaries

- `web-ui` owns user-facing interaction and calls only `/api/*`.
- `api-gateway` owns public API contracts, auth/session placeholders, and service routing.
- `ai-orchestrator` owns RAG, agents, model calls, retrieval orchestration, and tracing.
- `ingestion-worker` owns document parsing, chunking, embedding, index writes, reindexing, and batch evaluations.

## Communication

- Online chat path: Web UI -> API Gateway -> AI Orchestrator.
- Offline ingestion path: API Gateway -> Redis queue -> Ingestion Worker.
- Shared stores: PostgreSQL for metadata, Qdrant for vectors, MinIO for source objects.

