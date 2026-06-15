import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type ChatResponse = {
  answer: string;
  citations: Array<{ title: string; snippet: string; score?: number }>;
  trace_id?: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function App() {
  const [question, setQuestion] = useState("订单服务 502，网关报 upstream timeout");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function submitQuestion() {
    setLoading(true);
    const result = await fetch(`${apiBaseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    setResponse(await result.json());
    setLoading(false);
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">AI Ops Knowledge Copilot</p>
        <h1>研发知识库与故障助手</h1>
        <p className="lede">阶段 0 骨架已拆分为 Web UI、API Gateway、AI Orchestrator 和 Ingestion Worker。</p>
      </section>

      <section className="panel">
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button onClick={submitQuestion} disabled={loading}>
          {loading ? "分析中..." : "发送问题"}
        </button>
      </section>

      {response && (
        <section className="answer">
          <h2>回答</h2>
          <p>{response.answer}</p>
          <small>Trace: {response.trace_id}</small>
          <h3>引用</h3>
          {response.citations.map((citation) => (
            <article key={citation.title}>
              <strong>{citation.title}</strong>
              <p>{citation.snippet}</p>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

