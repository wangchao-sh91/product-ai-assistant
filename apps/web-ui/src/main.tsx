import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type ChatResponse = {
  answer: string;
  citations: Array<{ document_id: string; title: string; snippet: string; score?: number }>;
  trace_id?: string;
  session_id?: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function App() {
  const [question, setQuestion] = useState("订单服务 502，网关报 upstream timeout");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitQuestion() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetch(`${apiBaseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });
      if (!result.ok) {
        throw new Error(`请求失败：${result.status}`);
      }
      const payload = await result.json();
      setResponse(payload);
      setSessionId(payload.session_id ?? sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">AI Ops Knowledge Copilot</p>
        <h1>RAG 知识问答</h1>
        <p className="lede">基于已入库文档检索证据，返回带引用的研发知识库答案。</p>
      </section>

      <section className="panel">
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button onClick={submitQuestion} disabled={loading}>
          {loading ? "分析中..." : "发送问题"}
        </button>
      </section>

      {error && <section className="error">{error}</section>}

      {response && (
        <section className="answer">
          <h2>回答</h2>
          <pre>{response.answer}</pre>
          <small>Trace: {response.trace_id}</small>
          {response.session_id && <small>Session: {response.session_id}</small>}
          <h3>引用</h3>
          {response.citations.map((citation) => (
            <article key={`${citation.document_id}-${citation.snippet}`}>
              <strong>{citation.title}</strong>
              {citation.score !== undefined && <span>Score {citation.score.toFixed(4)}</span>}
              <p>{citation.snippet}</p>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
