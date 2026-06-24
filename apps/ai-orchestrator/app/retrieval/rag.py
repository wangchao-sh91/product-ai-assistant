from __future__ import annotations

import os
import re
from dataclasses import dataclass
from uuid import uuid4

from qdrant_client import QdrantClient
from sqlalchemy import or_, select

from product_ai_shared import ChatRequest, ChatResponse, Citation
from product_ai_shared.db import document_chunks, documents, get_engine
from product_ai_shared.embeddings import embed_text, rerank_texts, tokenize

COLLECTION_NAME = "knowledge_chunks"


@dataclass
class Evidence:
    chunk_id: str
    parent_chunk_id: str | None
    doc_id: str
    title: str
    doc_type: str
    content: str
    parent_content: str | None
    section_title: str | None
    page_no: int | None
    dense_score: float
    sparse_score: float
    score: float


def normalize_query(question: str) -> str:
    return " ".join(question.strip().split())


def rewrite_query(question: str) -> list[str]:
    normalized = normalize_query(question)
    lowered = normalized.lower()
    rewrites = [normalized]
    if lowered != normalized:
        rewrites.append(lowered)
    keywords = " ".join(token for token in tokenize(lowered) if len(token) > 1)
    if keywords and keywords not in rewrites:
        rewrites.append(keywords)
    return rewrites


def query_terms_from_rewrites(rewrites: list[str]) -> set[str]:
    terms = {token.lower() for rewrite in rewrites for token in tokenize(rewrite) if len(token) > 1}
    for rewrite in rewrites:
        for match in re.findall(r"[\u4e00-\u9fff]{2,}", rewrite):
            terms.add(match)
            for size in (2, 3, 4):
                terms.update(match[index : index + size] for index in range(0, max(len(match) - size + 1, 0)))
    return {term for term in terms if len(term) > 1}


def metadata_filters(metadata: dict | None) -> dict[str, str]:
    allowed = {"doc_type", "system_name", "module_name", "environment", "owner", "version"}
    return {key: str(value) for key, value in (metadata or {}).items() if key in allowed and value}


def lexical_score(query_terms: set[str], content: str, title: str = "") -> float:
    if not query_terms:
        return 0.0
    content_lower = content.lower()
    title_lower = title.lower()
    content_tokens = [token.lower() for token in tokenize(content)]
    title_tokens = [token.lower() for token in tokenize(title)]
    if not content_tokens and not title_tokens:
        return 0.0

    content_hits = sum(1 for token in content_tokens if token in query_terms)
    title_hits = sum(1 for token in title_tokens if token in query_terms)
    phrase_hits = sum(1 for term in query_terms if term in content_lower)
    title_phrase_hits = sum(1 for term in query_terms if term in title_lower)
    coverage = (phrase_hits + title_phrase_hits) / max(len(query_terms), 1)
    phrase_density = phrase_hits / max(len(content_tokens), 1)
    return (content_hits / max(len(content_tokens), 1)) + phrase_density + (title_hits * 0.15) + coverage


def snippet(text: str, query_terms: set[str], max_chars: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact

    lowered = compact.lower()
    positions = [lowered.find(term) for term in query_terms if term and lowered.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - max_chars // 3)
    end = min(len(compact), start + max_chars)
    start = max(0, end - max_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def split_sentences(text: str) -> list[str]:
    compact = " ".join(text.split())
    parts = re.split(r"(?<=[。！？.!?])\s+|(?<=[。！？])|(?<=[.!?])\s+", compact)
    return [part.strip() for part in parts if part.strip()]


def normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    low = min(scores)
    high = max(scores)
    if high == low:
        return [0.5 for _ in scores]
    return [(score - low) / (high - low) for score in scores]


class RagPipeline:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://ai_ops:ai_ops_password@postgres:5432/ai_ops_copilot",
        )
        self.qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        self.engine = get_engine(self.database_url)
        self.qdrant = QdrantClient(url=self.qdrant_url)

    def dense_retrieve(self, query: str, limit: int = 12) -> dict[str, float]:
        try:
            result = self.qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=embed_text(query),
                limit=limit,
                with_payload=True,
            )
        except Exception:
            return {}
        points = getattr(result, "points", result)
        return {str(point.id): float(point.score or 0.0) for point in points}

    def sparse_candidates(self, query_terms: set[str], filters: dict[str, str], limit: int = 80) -> list[dict]:
        conditions = [document_chunks.c.chunk_level == "child"]
        for key, value in filters.items():
            column = getattr(documents.c, key, None)
            if column is not None:
                conditions.append(column == value)

        keyword_conditions = []
        for term in sorted(query_terms):
            if len(term) > 1:
                pattern = f"%{term}%"
                keyword_conditions.append(document_chunks.c.content.ilike(pattern))
                keyword_conditions.append(documents.c.title.ilike(pattern))
        if keyword_conditions:
            conditions.append(or_(*keyword_conditions))

        query = (
            select(
                document_chunks.c.id,
                document_chunks.c.parent_chunk_id,
                document_chunks.c.doc_id,
                document_chunks.c.content,
                document_chunks.c.section_title,
                document_chunks.c.page_no,
                documents.c.title,
                documents.c.doc_type,
            )
            .join(documents, document_chunks.c.doc_id == documents.c.id)
            .where(*conditions)
            .limit(limit)
        )
        with self.engine.begin() as conn:
            return [dict(row) for row in conn.execute(query).mappings()]

    def load_chunk_rows(self, chunk_ids: set[str], filters: dict[str, str]) -> dict[str, dict]:
        if not chunk_ids:
            return {}
        conditions = [document_chunks.c.id.in_(chunk_ids)]
        for key, value in filters.items():
            column = getattr(documents.c, key, None)
            if column is not None:
                conditions.append(column == value)
        query = (
            select(
                document_chunks.c.id,
                document_chunks.c.parent_chunk_id,
                document_chunks.c.doc_id,
                document_chunks.c.content,
                document_chunks.c.section_title,
                document_chunks.c.page_no,
                documents.c.title,
                documents.c.doc_type,
            )
            .join(documents, document_chunks.c.doc_id == documents.c.id)
            .where(*conditions)
        )
        with self.engine.begin() as conn:
            return {row["id"]: dict(row) for row in conn.execute(query).mappings()}

    def load_parent_content(self, parent_ids: set[str]) -> dict[str, str]:
        if not parent_ids:
            return {}
        query = select(document_chunks.c.id, document_chunks.c.content).where(document_chunks.c.id.in_(parent_ids))
        with self.engine.begin() as conn:
            return {row["id"]: row["content"] for row in conn.execute(query).mappings()}

    def retrieve(self, request: ChatRequest, top_k: int = 5) -> tuple[list[str], list[Evidence]]:
        rewrites = rewrite_query(request.question)
        filters = metadata_filters(request.metadata)
        query_terms = query_terms_from_rewrites(rewrites)

        dense_scores: dict[str, float] = {}
        for rewrite in rewrites:
            for chunk_id, score in self.dense_retrieve(rewrite).items():
                dense_scores[chunk_id] = max(dense_scores.get(chunk_id, 0.0), score)

        candidates = self.load_chunk_rows(set(dense_scores), filters)
        for row in self.sparse_candidates(query_terms, filters):
            candidates.setdefault(row["id"], row)

        parent_ids = {row["parent_chunk_id"] for row in candidates.values() if row.get("parent_chunk_id")}
        parents = self.load_parent_content(parent_ids)

        evidences: list[Evidence] = []
        for row in candidates.values():
            sparse = lexical_score(query_terms, row["content"], row["title"])
            dense = dense_scores.get(row["id"], 0.0)
            score = (0.45 * max(dense, 0.0)) + (0.55 * min(sparse, 1.0))
            evidences.append(
                Evidence(
                    chunk_id=row["id"],
                    parent_chunk_id=row.get("parent_chunk_id"),
                    doc_id=row["doc_id"],
                    title=row["title"],
                    doc_type=row["doc_type"],
                    content=row["content"],
                    parent_content=parents.get(row.get("parent_chunk_id")),
                    section_title=row.get("section_title"),
                    page_no=row.get("page_no"),
                    dense_score=dense,
                    sparse_score=sparse,
                    score=score,
                )
            )

        evidences = [
            evidence
            for evidence in evidences
            if evidence.score >= 0.08 or evidence.sparse_score > 0.0 or evidence.dense_score >= 0.18
        ]
        evidences.sort(key=lambda item: item.score, reverse=True)
        shortlist = evidences[: min(len(evidences), 20)]
        try:
            rerank_scores = normalize_scores(
                rerank_texts(request.question, [evidence.parent_content or evidence.content for evidence in shortlist])
            )
            for evidence, rerank_score in zip(shortlist, rerank_scores, strict=False):
                evidence.score = (0.35 * evidence.score) + (0.65 * rerank_score)
        except Exception:
            pass
        shortlist.sort(key=lambda item: item.score, reverse=True)
        return rewrites, shortlist[:top_k]

    def generate_answer(self, question: str, evidences: list[Evidence]) -> str:
        if not evidences or evidences[0].score < 0.12:
            return (
                "未在当前知识库中检索到足够相关的证据。请补充更具体的系统、模块、错误信息，"
                "或先导入相关设计文档、Runbook、事故复盘后再提问。"
            )

        query_terms = query_terms_from_rewrites([question])
        lines = ["基于当前知识库证据，结论如下："]
        used: set[str] = set()
        for index, evidence in enumerate(evidences[:4], start=1):
            context = evidence.parent_content or evidence.content
            ranked_sentences = sorted(
                split_sentences(context),
                key=lambda sentence: lexical_score(query_terms, sentence, evidence.title),
                reverse=True,
            )
            selected = next((sentence for sentence in ranked_sentences if sentence not in used), "")
            if not selected:
                selected = snippet(evidence.content, query_terms, max_chars=220)
            used.add(selected)
            source = evidence.title
            if evidence.page_no:
                source = f"{source} 第 {evidence.page_no} 页"
            elif evidence.section_title:
                source = f"{source} / {evidence.section_title}"
            lines.append(f"{index}. {selected}（来源：{source}）")
        lines.append("以上回答仅基于已检索到的文档片段；若问题涉及生产变更，请结合实时监控和日志复核。")
        return "\n".join(lines)

    def complete_chat(self, request: ChatRequest) -> ChatResponse:
        _, evidences = self.retrieve(request)
        if not evidences or evidences[0].score < 0.12:
            return ChatResponse(
                answer=self.generate_answer(request.question, evidences),
                citations=[],
                trace_id=f"trace_{uuid4().hex}",
            )
        query_terms = query_terms_from_rewrites([request.question])
        citations = [
            Citation(
                document_id=evidence.doc_id,
                title=evidence.title,
                snippet=snippet(evidence.content, query_terms),
                score=round(evidence.score, 4),
            )
            for evidence in evidences
        ]
        return ChatResponse(
            answer=self.generate_answer(request.question, evidences),
            citations=citations,
            trace_id=f"trace_{uuid4().hex}",
        )

    def debug_retrieve(self, request: ChatRequest) -> dict[str, object]:
        rewrites, evidences = self.retrieve(request, top_k=10)
        return {
            "query": request.question,
            "rewrites": rewrites,
            "documents": [
                {
                    "chunk_id": evidence.chunk_id,
                    "parent_chunk_id": evidence.parent_chunk_id,
                    "document_id": evidence.doc_id,
                    "title": evidence.title,
                    "doc_type": evidence.doc_type,
                    "section_title": evidence.section_title,
                    "page_no": evidence.page_no,
                    "score": round(evidence.score, 4),
                    "dense_score": round(evidence.dense_score, 4),
                    "sparse_score": round(evidence.sparse_score, 4),
                    "snippet": snippet(evidence.content, query_terms_from_rewrites([request.question])),
                }
                for evidence in evidences
            ],
        }
