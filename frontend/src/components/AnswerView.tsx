import type { ReactNode } from "react";
import type { AssistantMessage, Citation, CitationStatus } from "../types";
import { AgentTrace } from "./AgentTrace";
import { Alert, Check, Clock, Coins, Refresh, X, Zap } from "./Icons";

export const STATUS_LABEL: Record<CitationStatus, string> = {
  verified: "zweryfikowany",
  uncertain: "niepewny",
  wrong: "błędny",
};

export function StatusBadge({ status }: { status: CitationStatus }) {
  const icon = status === "verified" ? <Check size={12} /> : status === "uncertain" ? <Alert size={12} /> : <X size={12} />;
  return <span className={`badge s-${status}`}>{icon}{STATUS_LABEL[status]}</span>;
}

/** Render answer text, turning [n] markers into clickable, status-colored citation chips. */
function renderWithMarkers(text: string, citations: Citation[], onOpen: (c: Citation) => void): ReactNode[] {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (!m) return part;
    const c = citations.find((x) => x.index === Number(m[1]));
    if (!c) return null;
    return (
      <button key={i} className={`cite-marker s-${c.status}`} title={`${c.citation ?? c.provision_id} — ${STATUS_LABEL[c.status]}`} onClick={() => onOpen(c)}>
        {c.index}
      </button>
    );
  });
}

const plural = (n: number, one: string, few: string, many: string) =>
  n === 1 ? one : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? few : many;

export function AnswerView({ msg, onOpen, onRetry }: { msg: AssistantMessage; onOpen: (c: Citation) => void; onRetry: () => void }) {
  const p = msg.payload;
  const citations = p?.citations ?? [];
  const text = p ? p.answer : msg.text;
  const kind = p?.status === "clarify" ? "Pytanie doprecyzowujące" : p?.status === "refuse" ? "Brak podstawy w przepisach" : null;

  return (
    <div className="msg-bot">
      <div className="avatar">§</div>
      <div className="bot-body">
        {(msg.steps.length > 0 || msg.pending) && <AgentTrace steps={msg.steps} pending={msg.pending} />}

        {msg.error && (
          <div className="card error">
            <strong>{msg.error.code === "busy" ? "Chwilowo zajęte" : msg.error.code === "budget" ? "Limit dzienny" : "Ups"}</strong>
            <div>{msg.error.message}</div>
            {msg.error.code !== "too_long" && <button className="ref-chip" style={{ marginTop: 8 }} onClick={onRetry}><Refresh size={12} /> Spróbuj ponownie</button>}
          </div>
        )}

        {text && (
          <div className={`card answer ${p?.status ?? ""}`}>
            {kind && <div className="kind">{kind}</div>}
            <div className="text">
              {renderWithMarkers(text, citations, onOpen)}
              {msg.pending && !p && <span className="caret" />}
            </div>
          </div>
        )}

        {citations.length > 0 && (
          <div className="citations">
            {citations.map((c) => (
              <button key={c.index} className="cite-card" onClick={() => onOpen(c)}>
                <span className={`cite-marker s-${c.status} num`}>{c.index}</span>
                <div className="head"><span className="ref">{c.citation ?? c.provision_id}</span><StatusBadge status={c.status} /></div>
                <div className="quote">„{c.quote}”</div>
                {c.explanation && <div className="why">Weryfikator: {c.explanation}</div>}
              </button>
            ))}
          </div>
        )}

        {p && (
          <div className="meta">
            <span><Clock size={13} /> {(p.metrics.total_ms / 1000).toFixed(1)} s</span>
            <span><Zap size={13} /> {p.metrics.tokens.toLocaleString("pl-PL")} tokenów · {p.metrics.llm_calls} {plural(p.metrics.llm_calls, "wywołanie", "wywołania", "wywołań")} API</span>
            <span title="Demo działa na darmowych limitach API — faktyczny koszt to $0. To szacunek w cenach płatnego planu.">
              <Coins size={13} /> ≈ ${p.metrics.cost_usd.toFixed(4)} w płatnym planie (demo: $0)
            </span>
            {p.cached && <span>⚡ z cache</span>}
          </div>
        )}
      </div>
    </div>
  );
}
