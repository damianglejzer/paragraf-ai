import { useEffect, useState } from "react";
import { fetchEval } from "../api";
import { AgentGraph } from "./AgentGraph";
import { EvalResults, type EvalReport } from "./EvalResults";
import { Database, Shield, Zap } from "./Icons";

function Diagram() {
  const box = (x: number, y: number, w: number, title: string, sub: string, accent = false) => (
    <g>
      <rect x={x} y={y} width={w} height={58} rx={12} fill={accent ? "var(--primary-soft)" : "var(--surface-2)"} stroke={accent ? "var(--primary-2)" : "var(--border)"} />
      <text x={x + w / 2} y={y + 25} textAnchor="middle" fontSize="13.5" fontWeight="600" fill="var(--text)">{title}</text>
      <text x={x + w / 2} y={y + 43} textAnchor="middle" fontSize="11" fill="var(--text-3)">{sub}</text>
    </g>
  );
  const arrow = (x1: number, y1: number, x2: number, y2: number) => (
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--text-3)" strokeWidth="1.5" markerEnd="url(#arr)" />
  );
  return (
    <svg viewBox="0 0 980 330" role="img" aria-label="Diagram architektury">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 10 5 0 10z" fill="var(--text-3)" />
        </marker>
      </defs>
      <text x="10" y="18" fontSize="11" fontWeight="600" fill="var(--gold)" letterSpacing="1.5">INDEKSOWANIE (OFFLINE)</text>
      {box(10, 30, 160, "API ELI Sejmu", "teksty jednolite HTML")}
      {box(210, 30, 170, "Parser strukturalny", "art. / § / ust. + ścieżka")}
      {box(420, 30, 170, "Odesłania", "„art. 22 § 1” → relacje")}
      {box(630, 30, 160, "Lematyzacja + embed.", "spaCy pl · Jina v3")}
      {box(820, 30, 150, "PostgreSQL", "pgvector + FTS", true)}
      {arrow(170, 59, 208, 59)}{arrow(380, 59, 418, 59)}{arrow(590, 59, 628, 59)}{arrow(790, 59, 818, 59)}

      <text x="970" y="133" textAnchor="end" fontSize="11" fontWeight="600" fill="var(--gold)" letterSpacing="1.5">ZAPYTANIE (ONLINE) · AGENT LANGGRAPH</text>
      {box(10, 140, 150, "Planer (LLM)", "dopytaj / odmów / szukaj")}
      {box(195, 140, 175, "Retrieval hybrydowy", "ts_rank_cd + wektory + RRF", true)}
      {box(405, 140, 140, "Reranker", "cross-encoder Jina")}
      {box(580, 140, 170, "Odpowiedź (LLM)", "structured output + cytaty")}
      {box(785, 140, 185, "Weryfikacja cytatów", "istnieje · cytat · popiera?", true)}
      {arrow(160, 169, 193, 169)}{arrow(370, 169, 403, 169)}{arrow(545, 169, 578, 169)}{arrow(750, 169, 783, 169)}
      {arrow(895, 90, 895, 112)}<line x1="895" y1="112" x2="282" y2="112" stroke="var(--text-3)" strokeWidth="1.5" strokeDasharray="4 4" />{arrow(282, 112, 282, 138)}

      <text x="10" y="238" fontSize="11" fontWeight="600" fill="var(--gold)" letterSpacing="1.5">NARZĘDZIA AGENTA · UDOSTĘPNIONE TEŻ PRZEZ MCP</text>
      {["search_law", "get_article", "follow_reference"].map((t, i) => (
        <g key={t}>
          <rect x={10 + i * 175} y={250} width={160} height={34} rx={9} fill="var(--surface)" stroke="var(--border)" />
          <text x={90 + i * 175} y={272} textAnchor="middle" fontSize="12.5" fontFamily="ui-monospace, monospace" fill="var(--text-2)">{t}()</text>
        </g>
      ))}
      {box(720, 238, 250, "FastAPI (SSE) → React UI", "kroki na żywo · statusy cytatów")}
      <text x="10" y="315" fontSize="11" fill="var(--text-3)">Obserwowalność: Langfuse (opcjonalnie) · Ochrona kosztów: rate limit per IP, dzienny budżet, cache odpowiedzi</text>
    </svg>
  );
}

export function HowItWorks() {
  const [report, setReport] = useState<EvalReport | null | undefined>(undefined);
  useEffect(() => { fetchEval().then((r) => setReport(r as EvalReport | null)).catch(() => setReport(null)); }, []);

  return (
    <div className="scroll">
      <div className="page">
        <div>
          <h1>Jak to działa</h1>
          <p className="lead">
            Paragraf AI to agent RAG nad polskimi ustawami. Odpowiada na podstawie oficjalnych tekstów
            jednolitych <strong>Kodeksu pracy</strong>, <strong>Kodeksu cywilnego</strong> i <strong>ustawy o prawach konsumenta</strong>,
            a każdy cytat jest automatycznie weryfikowany: czy przepis istnieje, czy cytowany
            fragment naprawdę w nim jest i czy popiera on odpowiedź przygotowaną przez agenta.
          </p>
        </div>

        <div className="card diagram"><Diagram /></div>

        <div className="grid-3">
          <div className="card info"><h3><Database size={16} /> Chunking strukturalny</h3><p>Jednostką jest artykuł / § / ustęp z pełną ścieżką (np. „KP, Dział VII, Rozdział I, art. 154 § 1”).</p></div>
          <div className="card info"><h3><Zap size={16} /> Retrieval hybrydowy</h3><p>Wyszukiwanie po lematach z rankingiem <code>ts_rank_cd</code> (spaCy, Postgres <code>simple</code>) + wektory (pgvector), fuzja RRF, przepisanie pytania na język ustaw i reranker cross-encoder.</p></div>
          <div className="card info"><h3><Shield size={16} /> Weryfikacja cytatów</h3><p>Dla każdego cytatu: czy przepis istnieje w bazie, czy cytowany fragment naprawdę w nim jest (fuzzy match) i czy popiera twierdzenie — ocenia osobny sędzia LLM, który widzi tylko treść przepisu i twierdzenie.</p></div>
        </div>

        <div>
          <h2>Agent w LangGraph</h2>
          <p className="lead" style={{ marginTop: 0 }}>
            Agent to graf stanów: węzły wykonują kolejne kroki, a krawędzie warunkowe decydują, dokąd iść dalej.
            Wybierz scenariusz i odtwórz go, żeby zobaczyć, którędy przechodzi pytanie i co powstaje na każdym etapie.
          </p>
        </div>
        <AgentGraph />

        <EvalResults report={report} />
      </div>
    </div>
  );
}
