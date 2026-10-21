import { useEffect, useState } from "react";
import { fetchEval } from "../api";
import { AgentGraph } from "./AgentGraph";
import { Database, Shield, Zap } from "./Icons";

interface RetrievalRow { mode: string; label?: string; overall: Record<string, number>; latency_ms: { p50: number; p95: number } }
interface GenSummary { [k: string]: number | null | undefined | object }
interface GenRow { config: string; label: string; summary: GenSummary }
interface Report {
  meta: Record<string, string | number>;
  dataset?: { n: number; by_category: Record<string, number>; verified: number };
  retrieval?: RetrievalRow[];
  generation?: GenRow[];
}

const pct = (v: unknown) => (typeof v === "number" && !Number.isNaN(v) ? `${(v * 100).toFixed(1)}%` : "—");
const num = (v: unknown, d = 3) => (typeof v === "number" && !Number.isNaN(v) ? v.toFixed(d) : "—");

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
      {box(195, 140, 175, "Retrieval hybrydowy", "BM25 + wektory + RRF", true)}
      {box(405, 140, 140, "Reranker", "cross-encoder Jina")}
      {box(580, 140, 170, "Odpowiedź (LLM)", "structured output + cytaty")}
      {box(785, 140, 185, "Weryfikacja cytatów", "istnieje · cytat · popiera?", true)}
      {arrow(160, 169, 193, 169)}{arrow(370, 169, 403, 169)}{arrow(545, 169, 578, 169)}{arrow(750, 169, 783, 169)}
      {arrow(895, 90, 895, 112)}<line x1="895" y1="112" x2="282" y2="112" stroke="var(--text-3)" strokeWidth="1.5" strokeDasharray="4 4" />{arrow(282, 112, 282, 138)}

      <text x="10" y="238" fontSize="11" fontWeight="600" fill="var(--gold)" letterSpacing="1.5">NARZĘDZIA AGENTA · UDOSTĘPNIONE TEŻ PRZEZ MCP</text>
      {["search_law", "get_article", "follow_reference", "calculate_deadline"].map((t, i) => (
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
  const [report, setReport] = useState<Report | null | undefined>(undefined);
  useEffect(() => { fetchEval().then((r) => setReport(r as Report | null)).catch(() => setReport(null)); }, []);

  const gen = report?.generation ?? [];
  const final = gen[gen.length - 1]?.summary;
  const retrievalByMode = Object.fromEntries((report?.retrieval ?? []).map((r) => [r.mode, r]));
  const modeFor: Record<string, string> = { naive: "naive", hybrid: "hybrid", hybrid_rerank: "hybrid_rerank", full: "full", full_verified: "full" };

  return (
    <div className="scroll">
      <div className="page">
        <div>
          <h1>Jak to działa</h1>
          <p className="lead">
            Paragraf AI to agent RAG nad polskimi ustawami. Najważniejsze nie jest samo czatowanie, tylko to,
            że <strong>każdy cytat jest automatycznie sprawdzany</strong>, a jakość systemu jest zmierzona
            na zbiorze testowym. Ablacja pokazuje, ile daje każdy element pipeline'u.
          </p>
        </div>

        <div className="card diagram"><Diagram /></div>

        <div className="grid-3">
          <div className="card info"><h3><Database size={16} /> Chunking strukturalny</h3><p>Jednostką jest artykuł / § / ustęp z pełną ścieżką (np. „KP, Dział VII, Rozdział I, art. 154 § 1”). Parser zgadza się w 100% z endpointem <code>/struct</code> API ELI.</p></div>
          <div className="card info"><h3><Zap size={16} /> Retrieval hybrydowy</h3><p>Pełnotekstowe wyszukiwanie po lematach (spaCy, Postgres <code>simple</code>) + wektory (pgvector), fuzja RRF, przepisanie pytania na język ustaw i reranker cross-encoder.</p></div>
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

        {report === undefined && <div className="note"><span className="spinner" /> Wczytuję wyniki ewaluacji…</div>}
        {report === null && <div className="card info"><p>Wyniki ewaluacji nie zostały jeszcze wygenerowane (<code>evals/results/latest.json</code>).</p></div>}

        {report && final && (
          <div>
            <h2>Wyniki (pełny system)</h2>
            <div className="kpis">
              <div className="card kpi"><div className="v">{pct(final.correctness)}</div><div className="k">poprawność odpowiedzi</div></div>
              <div className="card kpi"><div className="v">{pct(final.citation_accuracy)}</div><div className="k">zweryfikowanych cytatów</div></div>
              <div className="card kpi"><div className="v">{pct(final.faithfulness)}</div><div className="k">faithfulness</div></div>
              <div className="card kpi"><div className="v">{pct(final.refusal_accuracy)}</div><div className="k">trafność odmów</div></div>
              <div className="card kpi"><div className="v">{((final.latency_ms_p50 as number) / 1000).toFixed(1)} s</div><div className="k">latencja p50 (p95: {((final.latency_ms_p95 as number) / 1000).toFixed(1)} s)</div></div>
            </div>
          </div>
        )}

        {report && gen.length > 0 && (
          <div>
            <h2>Ablacja: co daje każdy element</h2>
            <div className="card table-wrap">
              <table className="results">
                <thead>
                  <tr><th>Konfiguracja</th><th>Recall@5</th><th>MRR</th><th>Poprawność</th><th>Faithfulness</th><th>Cytaty OK</th><th>Błędne cytaty</th><th>Odmowy</th><th>p50</th></tr>
                </thead>
                <tbody>
                  {gen.map((g, i) => {
                    const r = retrievalByMode[modeFor[g.config]];
                    const s = g.summary;
                    return (
                      <tr key={g.config} className={i === gen.length - 1 ? "best" : ""}>
                        <td>{g.label}</td>
                        <td>{pct(r?.overall["recall@5"])}</td>
                        <td>{num(r?.overall.mrr)}</td>
                        <td>{pct(s.correctness)}<span className="bar" style={{ width: `${Number(s.correctness ?? 0) * 40}px` }} /></td>
                        <td>{pct(s.faithfulness)}</td>
                        <td>{pct(s.citation_accuracy)}</td>
                        <td>{pct(s.citation_wrong_rate)}</td>
                        <td>{pct(s.refusal_accuracy)}</td>
                        <td>{((s.latency_ms_p50 as number) / 1000).toFixed(1)} s</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="note">
              Zbiór: {String(report.meta.n_questions ?? "?")} pytań (syntetyczne, generowane przez LLM z automatyczną kontrolą jakości; kategorie: zwykłe,
              wymagające kilku przepisów, poza zakresem, podchwytliwe). Recall i MRR liczone na poziomie artykułu.
              Modele: {String(report.meta.llm)} (odpowiedzi), {String(report.meta.judge)} (sędzia), {String(report.meta.embedding)}, {String(report.meta.reranker)}.
              Wygenerowano {String(report.meta.generated_at)}.
            </p>
          </div>
        )}

        {report?.retrieval && (
          <div>
            <h2>Retrieval</h2>
            <div className="card table-wrap">
              <table className="results">
                <thead><tr><th>Tryb</th><th>R@1</th><th>R@3</th><th>R@5</th><th>R@10</th><th>MRR</th><th>p50</th></tr></thead>
                <tbody>
                  {report.retrieval.map((r) => (
                    <tr key={r.mode}>
                      <td>{r.label ?? r.mode}</td>
                      <td>{pct(r.overall["recall@1"])}</td><td>{pct(r.overall["recall@3"])}</td><td>{pct(r.overall["recall@5"])}</td><td>{pct(r.overall["recall@10"])}</td>
                      <td>{num(r.overall.mrr)}</td><td>{Math.round(r.latency_ms.p50)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
