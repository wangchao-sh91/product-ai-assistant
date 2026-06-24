from __future__ import annotations

import os
from typing import Literal, TypedDict
from uuid import uuid4

import httpx
from langgraph.graph import END, StateGraph

from product_ai_shared import ChatRequest, ChatResponse, Citation
from product_ai_shared.embeddings import tokenize

from app.retrieval.rag import Evidence, RagPipeline, query_terms_from_rewrites, snippet

Route = Literal["knowledge_qa", "incident_analysis", "runbook_lookup", "impact_analysis"]


class AgentState(TypedDict, total=False):
    request: ChatRequest
    question: str
    route: Route
    plan: list[str]
    rewrites: list[str]
    evidences: list[Evidence]
    answer: str
    warnings: list[str]
    citations: list[Citation]
    response: ChatResponse


class RouterAgent:
    INCIDENT_TERMS = {
        "故障",
        "异常",
        "报错",
        "失败",
        "超时",
        "timeout",
        "502",
        "503",
        "500",
        "p1",
        "p2",
        "告警",
        "不可用",
        "排查",
        "回滚",
    }
    RUNBOOK_TERMS = {"runbook", "sop", "预案", "手册", "步骤", "怎么处理", "如何处理", "处置"}
    IMPACT_TERMS = {"影响", "范围", "blast", "用户数", "损失", "等级", "定级"}

    def run(self, state: AgentState) -> dict[str, object]:
        question = state["question"]
        lowered = question.lower()
        tokens = {token.lower() for token in tokenize(lowered)}
        route: Route = "knowledge_qa"
        if tokens.intersection(self.IMPACT_TERMS) or any(term in lowered for term in self.IMPACT_TERMS):
            route = "impact_analysis"
        if tokens.intersection(self.RUNBOOK_TERMS) or any(term in lowered for term in self.RUNBOOK_TERMS):
            route = "runbook_lookup"
        if tokens.intersection(self.INCIDENT_TERMS) or any(term in lowered for term in self.INCIDENT_TERMS):
            route = "incident_analysis"

        plan = ["router"]
        if route == "knowledge_qa":
            plan.append("rag")
        else:
            plan.extend(["retriever", "incident_analyst"])
            if route in {"incident_analysis", "runbook_lookup"}:
                plan.append("runbook")
            plan.append("critic")
        return {"route": route, "plan": plan}


class RetrieverAgent:
    def __init__(self, rag: RagPipeline) -> None:
        self.rag = rag

    def run(self, state: AgentState) -> dict[str, object]:
        rewrites, evidences = self.rag.retrieve(state["request"], top_k=6)
        return {"rewrites": rewrites, "evidences": evidences}


class OpenAICompatibleLLM:
    def __init__(self) -> None:
        self.base_url = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4.1-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.base_url or not self.api_key:
            raise LLMAPIError(503, "LLM API is not configured")
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMAPIError(504, f"LLM API timed out after {self.timeout:g} seconds") from exc
        except httpx.RequestError as exc:
            raise LLMAPIError(502, f"LLM API request failed: {exc}") from exc

        if response.is_error:
            detail = response.text[:1000].strip() or response.reason_phrase
            raise LLMAPIError(502, f"LLM API returned HTTP {response.status_code}: {detail}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMAPIError(502, "LLM API returned an invalid chat completion response") from exc
        if not content:
            raise LLMAPIError(502, "LLM API returned an empty response")
        return content


class LLMAPIError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class IncidentAnalystAgent:
    def __init__(self) -> None:
        self.llm = OpenAICompatibleLLM()

    def run(self, state: AgentState) -> dict[str, str]:
        evidences = state.get("evidences") or []
        evidence_text = "\n\n".join(
            f"[{index}] {evidence.title} {evidence.section_title or ''}\n{evidence.parent_content or evidence.content}"
            for index, evidence in enumerate(evidences[:5], start=1)
        )
        system_prompt = (
            "你是企业研发故障 Copilot。必须优先基于给定证据回答；证据不足时要明确说明。"
            "输出中文结构化排查建议，包含：症状提取、可能根因、排查优先级、风险操作、引用依据。"
        )
        user_prompt = f"用户问题：{state['question']}\n\n检索证据：\n{evidence_text or '无'}"
        return {"answer": self.llm.complete(system_prompt, user_prompt)}


class RunbookAgent:
    RUNBOOK_TERMS = {"runbook", "sop", "预案", "手册", "步骤", "处置", "回滚", "降级", "限流", "扩容"}

    def run(self, state: AgentState) -> dict[str, str]:
        evidences = state.get("evidences") or []
        query_terms = query_terms_from_rewrites([state["question"]])
        runbook_evidences = [
            evidence
            for evidence in evidences
            if evidence.doc_type == "runbook"
            or any(term in (evidence.title + evidence.content).lower() for term in self.RUNBOOK_TERMS)
        ]

        lines = ["", "## Runbook 建议"]
        if runbook_evidences:
            for index, evidence in enumerate(runbook_evidences[:3], start=1):
                source = evidence.title
                if evidence.section_title:
                    source = f"{source} / {evidence.section_title}"
                lines.append(f"{index}. {snippet(evidence.parent_content or evidence.content, query_terms, 260)}（来源：{source}）")
        else:
            lines.append("当前检索结果中没有匹配到可引用的 Runbook。")
        return {"answer": f"{state.get('answer', '')}\n" + "\n".join(lines)}


class CriticAgent:
    def run(self, state: AgentState) -> dict[str, list[str]]:
        warnings: list[str] = []
        evidences = state.get("evidences") or []
        if not evidences or evidences[0].score < 0.12:
            warnings.append("当前知识库证据不足，故障建议需要结合实时监控、日志和变更记录复核。")
        if any(term in state["question"].lower() for term in ("回滚", "删除", "清理", "重启", "扩容", "降级")):
            warnings.append("涉及生产操作，执行前应确认影响范围、审批记录、观察指标和回滚方案。")
        return {"warnings": warnings}


class IncidentWorkflow:
    def __init__(self, rag: RagPipeline) -> None:
        self.rag = rag
        self.router = RouterAgent()
        self.retriever = RetrieverAgent(rag)
        self.analyst = IncidentAnalystAgent()
        self.runbook = RunbookAgent()
        self.critic = CriticAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("supervisor", self.router.run)
        graph.add_node("rag", self._run_rag)
        graph.add_node("retriever", self.retriever.run)
        graph.add_node("incident_analyst", self.analyst.run)
        graph.add_node("runbook", self.runbook.run)
        graph.add_node("critic", self.critic.run)
        graph.add_node("finalize", self._finalize)

        graph.set_entry_point("supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self._next_after_supervisor,
            {
                "rag": "rag",
                "retriever": "retriever",
            },
        )
        graph.add_edge("rag", END)
        graph.add_edge("retriever", "incident_analyst")
        graph.add_conditional_edges(
            "incident_analyst",
            self._next_after_analysis,
            {
                "runbook": "runbook",
                "critic": "critic",
            },
        )
        graph.add_edge("runbook", "critic")
        graph.add_edge("critic", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _next_after_supervisor(self, state: AgentState) -> str:
        if state.get("route") == "knowledge_qa":
            return "rag"
        return "retriever"

    def _next_after_analysis(self, state: AgentState) -> str:
        if state.get("route") in {"incident_analysis", "runbook_lookup"}:
            return "runbook"
        return "critic"

    def _run_rag(self, state: AgentState) -> dict[str, ChatResponse]:
        return {"response": self.rag.complete_chat(state["request"])}

    def _finalize(self, state: AgentState) -> dict[str, ChatResponse]:
        answer = state.get("answer", "")
        warnings = state.get("warnings") or []
        if warnings:
            answer = f"{answer}\n\n## 复核提示\n" + "\n".join(f"- {warning}" for warning in warnings)

        query_terms = query_terms_from_rewrites([state["question"]])
        citations = [
            Citation(
                document_id=evidence.doc_id,
                title=evidence.title,
                snippet=snippet(evidence.content, query_terms),
                score=round(evidence.score, 4),
            )
            for evidence in state.get("evidences", [])
            if evidence.score >= 0.12
        ]
        return {
            "response": ChatResponse(
                answer=answer,
                answer_type=state.get("route", "incident_analysis"),
                citations=citations,
                trace_id=f"trace_{uuid4().hex}",
            )
        }

    def complete(self, request: ChatRequest) -> ChatResponse:
        state: AgentState = {"request": request, "question": request.question}
        result = self.graph.invoke(state)
        return result["response"]
