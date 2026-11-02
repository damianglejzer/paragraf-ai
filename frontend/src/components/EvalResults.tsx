import { useRef, useState, type ReactNode } from "react";

type Num = number | null | undefined;
interface RetrievalRow { mode: string; n: number; overall: Record<string, Num>; latency_ms: { p50: number; p95: number } }
interface GenSummary {
  n: number;
  correctness: Num; faithfulness: Num; citation_accuracy: Num; citation_wrong_rate: Num; citation_recall: Num;
  refusal_accuracy: Num; oos_refusal_rate: Num; false_refusal_rate: Num;
  latency_ms_p50: Num; latency_ms_p95: Num; tokens_per_query: Num;
  by_category: Record<string, { n: number; correctness: Num; refusal_accuracy: Num }>;
}
interface GenRow { config: string; summary: GenSummary }
export interface EvalReport {
  meta: Record<string, string | number>;
  dataset?: { n: number; by_category: Record<string, number>; verified: number };
  retrieval?: RetrievalRow[];
  generation?: GenRow[];
}

const CONFIG: Record<string, { label: string; sub: string }> = {
  naive: { label: "Naive RAG", sub: "stałe fragmenty tekstu, tylko wektory" },
  full: { label: "Pełny pipeline", sub: "struktura ustawy, hybryda, reranker, przepisanie" },
  full_verified: { label: "+ weryfikacja cytatów", sub: "błędne cytaty usuwane z odpowiedzi" },
};
const MODE: Record<string, { label: string; sub: string }> = {
  naive: { label: "Naive RAG", sub: "stałe fragmenty, tylko wektory" },
  vector: { label: "Wektory", sub: "fragmenty według struktury ustawy" },
  fulltext: { label: "Pełnotekstowe", sub: "lematy + ts_rank_cd" },
  hybrid: { label: "Hybryda", sub: "wektory + pełnotekstowe, fuzja RRF" },
  hybrid_rerank: { label: "+ reranker", sub: "cross-encoder Jina" },
  full: { label: "+ przepisanie pytania", sub: "pytanie w języku ustawy" },
};
const CATEGORY: Record<string, string> = {
  regular: "Zwykłe pytania",
  multi: "Wymagające kilku przepisów",
  tricky: "Podchwytliwe (błędne założenie)",
  out_of_scope: "Poza zakresem",
};
const RETRIEVAL_METRICS = [
  { key: "recall@1", label: "Recall@1" },
  { key: "recall@3", label: "Recall@3" },
  { key: "recall@5", label: "Recall@5" },
  { key: "recall@10", label: "Recall@10" },
  { key: "mrr", label: "MRR" },
] as const;

const ok = (v: Num): v is number => typeof v === "number" && !Number.isNaN(v);
const pct = (v: Num, d = 0) => (ok(v) ? `${(v * 100).toFixed(d)}%` : "—");
const secs = (ms: Num) => (ok(ms) ? `${(ms / 1000).toFixed(1).replace(".", ",")} s` : "—");
const pp = (a: Num, b: Num) => {
  if (!ok(a) || !ok(b)) return null;
  const d = Math.round((a - b) * 100);
  return d === 0 ? "bez zmian" : `${d > 0 ? "+" : "−"}${Math.abs(d)} pp`;
};

/* ---------- tooltip: one per chart card, positioned inside it ---------- */

interface Tip { x: number; y: number; body: ReactNode }
function useTip() {
  const ref = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const show = (el: HTMLElement, body: ReactNode) => {
    const box = ref.current?.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    if (box) setTip({ x: r.left - box.left + r.width / 2, y: r.top - box.top, body });
  };
  const hide = () => setTip(null);
  const node = tip && (
    <div className="ev-tip" style={{ left: tip.x, top: tip.y }} role="tooltip">{tip.body}</div>
  );
  return { ref, show, hide, node };
}

/* ---------- one horizontal bar row ---------- */

function BarRow({ label, sub, value, emphasis, stacked, tipBody, onTip, onHide }: {
  label: string; sub?: string; value: Num; emphasis?: boolean; stacked?: boolean;
  tipBody: ReactNode; onTip: (el: HTMLElement, body: ReactNode) => void; onHide: () => void;
}) {
  const w = ok(value) ? Math.max(0, Math.min(1, value)) : 0;
  return (
    <div
      className={`ev-row ${emphasis ? "em" : ""} ${stacked ? "stacked" : ""}`} tabIndex={0}
      onMouseEnter={(e) => onTip(e.currentTarget, tipBody)} onMouseLeave={onHide}
      onFocus={(e) => onTip(e.currentTarget, tipBody)} onBlur={onHide}
    >
      <div className="ev-label"><span>{label}</span>{sub && <small>{sub}</small>}</div>
      <div className="ev-track">
        <div className="ev-bar" style={{ width: `calc((100% - 48px) * ${w})` }} />
        <span className="ev-val" style={{ left: `calc((100% - 48px) * ${w} + 8px)` }}>{pct(value)}</span>
      </div>
    </div>
  );
}

/* ---------- sections ---------- */

function Kpi({ value, label, delta, hint }: { value: string; label: string; delta?: string | null; hint?: string }) {
  return (
    <div className="card ev-kpi">
      <div className="ev-kpi-label">{label}</div>
      <div className="ev-kpi-value">{value}</div>
      {delta && <div className={`ev-kpi-delta ${delta.startsWith("−") ? "down" : ""}`}>{delta} <span>vs naive RAG</span></div>}
      {hint && <div className="ev-kpi-hint">{hint}</div>}
    </div>
  );
}

function ConfigCompare({ gen }: { gen: GenRow[] }) {
  const tip = useTip();
  const metrics: { key: keyof GenSummary; title: string; note: string; lowerBetter?: boolean }[] = [
    { key: "correctness", title: "Poprawność odpowiedzi", note: "zgodność z odpowiedzią wzorcową" },
    { key: "citation_accuracy", title: "Cytaty zweryfikowane", note: "przepis istnieje, cytat się zgadza i popiera tezę" },
    { key: "citation_wrong_rate", title: "Błędne cytaty", note: "mniej = lepiej", lowerBetter: true },
  ];
  return (
    <div className="ev-multiples" ref={tip.ref}>
      {metrics.map((m) => (
        <div className="card ev-chart" key={m.key}>
          <h3>{m.title}</h3>
          <p className="ev-note">{m.note}</p>
          <div className="ev-rows">
            {gen.map((g) => (
              <BarRow
                key={g.config}
                label={CONFIG[g.config]?.label ?? g.config}
                value={g.summary[m.key] as Num}
                emphasis={g.config === gen[gen.length - 1].config}
                stacked
                onTip={tip.show} onHide={tip.hide}
                tipBody={<>
                  <strong>{CONFIG[g.config]?.label ?? g.config}</strong>
                  <span>{CONFIG[g.config]?.sub}</span>
                  <span>{m.title}: <b>{pct(g.summary[m.key] as Num, 1)}</b></span>
                </>}
              />
            ))}
          </div>
        </div>
      ))}
      {tip.node}
    </div>
  );
}

function RetrievalChart({ rows }: { rows: RetrievalRow[] }) {
  const tip = useTip();
  const [metric, setMetric] = useState<(typeof RETRIEVAL_METRICS)[number]["key"]>("recall@5");
  const best = rows.find((r) => r.mode === "full") ?? rows[rows.length - 1];
  return (
    <div className="card ev-chart ev-wide" ref={tip.ref}>
      <div className="ev-chart-head">
        <div>
          <h3>Czy właściwy przepis trafia do kontekstu?</h3>
          <p className="ev-note">
            {metric === "mrr"
              ? "MRR: średnia odwrotność pozycji pierwszego trafnego przepisu (1 = zawsze na pierwszym miejscu)"
              : `Odsetek pytań, dla których oczekiwany artykuł jest w ${metric.split("@")[1]} pierwszych wynikach`}
          </p>
        </div>
        <div className="ev-seg" role="group" aria-label="Metryka">
          {RETRIEVAL_METRICS.map((m) => (
            <button key={m.key} className={metric === m.key ? "on" : ""} onClick={() => setMetric(m.key)} aria-pressed={metric === m.key}>{m.label}</button>
          ))}
        </div>
      </div>
      <div className="ev-rows">
        {rows.map((r) => (
          <BarRow
            key={r.mode}
            label={MODE[r.mode]?.label ?? r.mode}
            sub={MODE[r.mode]?.sub}
            value={r.overall[metric]}
            emphasis={r.mode === best.mode}
            onTip={tip.show} onHide={tip.hide}
            tipBody={<>
              <strong>{MODE[r.mode]?.label ?? r.mode}</strong>
              <span>R@1 {pct(r.overall["recall@1"])} · R@3 {pct(r.overall["recall@3"])} · R@5 {pct(r.overall["recall@5"])} · R@10 {pct(r.overall["recall@10"])}</span>
              <span>MRR {ok(r.overall.mrr) ? r.overall.mrr.toFixed(2) : "—"} · czas p50 {Math.round(r.latency_ms.p50)} ms</span>
            </>}
          />
        ))}
      </div>
      {rows.some((r) => r.mode === "naive") && (
        <p className="ev-foot">
          Naive RAG tnie tekst na fragmenty stałej długości, a jeden fragment obejmuje kilka przepisów naraz, więc
          łatwiej mu „trafić” w artykuł. Odpowiedzi z takiego kontekstu są jednak dużo gorsze: model nie wie, który
          przepis cytuje (patrz wykresy wyżej).
        </p>
      )}
      {tip.node}
    </div>
  );
}

function CategoryChart({ s }: { s: GenSummary }) {
  const tip = useTip();
  const order = Object.keys(CATEGORY);
  const cats = Object.entries(s.by_category)
    .filter(([c]) => c !== "out_of_scope")
    .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b));
  const oos = s.by_category.out_of_scope;
  return (
    <div className="card ev-chart" ref={tip.ref}>
      <h3>Poprawność według rodzaju pytania</h3>
      <p className="ev-note">pełny system z weryfikacją cytatów</p>
      <div className="ev-rows">
        {cats.map(([c, v]) => (
          <BarRow
            key={c} label={CATEGORY[c] ?? c} value={v.correctness} emphasis stacked
            onTip={tip.show} onHide={tip.hide}
            tipBody={<><strong>{CATEGORY[c] ?? c}</strong><span>{v.n} pytań · poprawność {pct(v.correctness, 1)}</span></>}
          />
        ))}
      </div>
      {oos && (
        <div className="ev-oos">
          <span className="ev-oos-v">{pct(oos.refusal_accuracy)}</span>
          <span>pytań spoza zakresu (gotowanie, prawo karne…) agent poprawnie odrzucił, zamiast zgadywać</span>
        </div>
      )}
      {tip.node}
    </div>
  );
}

function DataTable({ gen, retrieval }: { gen: GenRow[]; retrieval: RetrievalRow[] }) {
  return (
    <details className="card ev-table">
      <summary>Wszystkie liczby w tabeli</summary>
      <div className="table-wrap">
        <table className="results">
          <thead><tr><th>Konfiguracja</th><th>Poprawność</th><th>Wierność</th><th>Cytaty OK</th><th>Błędne cytaty</th><th>Trafne odmowy</th><th>p50</th><th>p95</th></tr></thead>
          <tbody>
            {gen.map((g) => (
              <tr key={g.config}>
                <td>{CONFIG[g.config]?.label ?? g.config}</td>
                <td>{pct(g.summary.correctness, 1)}</td><td>{pct(g.summary.faithfulness, 1)}</td>
                <td>{pct(g.summary.citation_accuracy, 1)}</td><td>{pct(g.summary.citation_wrong_rate, 1)}</td>
                <td>{pct(g.summary.refusal_accuracy, 1)}</td>
                <td>{secs(g.summary.latency_ms_p50)}</td><td>{secs(g.summary.latency_ms_p95)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="results">
          <thead><tr><th>Wyszukiwanie</th><th>R@1</th><th>R@3</th><th>R@5</th><th>R@10</th><th>MRR</th><th>p50</th></tr></thead>
          <tbody>
            {retrieval.map((r) => (
              <tr key={r.mode}>
                <td>{MODE[r.mode]?.label ?? r.mode}</td>
                <td>{pct(r.overall["recall@1"], 1)}</td><td>{pct(r.overall["recall@3"], 1)}</td>
                <td>{pct(r.overall["recall@5"], 1)}</td><td>{pct(r.overall["recall@10"], 1)}</td>
                <td>{ok(r.overall.mrr) ? r.overall.mrr.toFixed(3) : "—"}</td><td>{Math.round(r.latency_ms.p50)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/* ---------- page section ---------- */

export function EvalResults({ report }: { report: EvalReport | null | undefined }) {
  if (report === undefined) return <div className="note"><span className="spinner" /> Wczytuję wyniki ewaluacji…</div>;
  if (report === null || !report.generation?.length) {
    return (
      <div className="card info">
        <h3>Brak wyników ewaluacji</h3>
        <p>Uruchom <code>uv run python -m paragraf.evaluation.run_all</code>, aby je wygenerować.</p>
      </div>
    );
  }
  const gen = report.generation;
  const final = gen[gen.length - 1].summary;
  const naive = gen.find((g) => g.config === "naive")?.summary;
  const ds = report.dataset;
  const meta = report.meta;
  const date = typeof meta.generated_at === "string" ? new Date(meta.generated_at).toLocaleDateString("pl-PL", { day: "numeric", month: "long", year: "numeric" }) : null;

  return (
    <section className="ev">
      <div>
        <h2>Wyniki ewaluacji</h2>
        <p className="lead" style={{ marginTop: 0 }}>
          Każda wersja systemu odpowiada na te same {ds?.n ?? meta.n_questions} pytania testowe. Osobny model-sędzia
          porównuje odpowiedzi z wzorcowymi i sprawdza cytaty. Poniżej: pełny system i to, ile wnosi każdy element.
        </p>
      </div>

      <div className="ev-kpis">
        <Kpi label="Poprawne odpowiedzi" value={pct(final.correctness)} delta={pp(final.correctness, naive?.correctness)} />
        <Kpi label="Zweryfikowane cytaty" value={pct(final.citation_accuracy)} delta={pp(final.citation_accuracy, naive?.citation_accuracy)} />
        <Kpi label="Wierność przepisom" value={pct(final.faithfulness)} hint="twierdzenia poparte cytowanym przepisem" />
        <Kpi label="Trafne odmowy" value={pct(final.refusal_accuracy)} hint="odmawia tylko pytań spoza zakresu" />
        <Kpi label="Czas odpowiedzi" value={secs(final.latency_ms_p50)} hint="mediana: wyszukiwanie, odpowiedź i weryfikacja" />
      </div>

      <div>
        <h3 className="ev-h3">Co wnosi każdy element</h3>
        <ConfigCompare gen={gen} />
      </div>

      <div className="ev-split">
        {report.retrieval && report.retrieval.length > 0 && <RetrievalChart rows={report.retrieval} />}
        <CategoryChart s={final} />
      </div>

      <DataTable gen={gen} retrieval={report.retrieval ?? []} />

      <div className="ev-method">
        {ds && (
          <div className="ev-chips">
            <span className="ev-chip strong">{ds.n} pytań</span>
            {Object.entries(ds.by_category).map(([c, n]) => <span key={c} className="ev-chip">{CATEGORY[c] ?? c}: {n}</span>)}
          </div>
        )}
        <p className="note">
          Pytania są syntetyczne: generuje je LLM na podstawie konkretnych przepisów, a drugi model automatycznie
          odrzuca te, na które nie da się odpowiedzieć z przepisu. Trafienie w wyszukiwaniu liczymy na poziomie artykułu.
          Zbiór jest celowo mały, żeby cała ewaluacja trwała kilka minut i kosztowała grosze
          {ok(meta.duration_s as Num) ? ` (ostatni przebieg: ${Math.round(Number(meta.duration_s) / 60)} min)` : ""}.
          Modele: {String(meta.llm)} (odpowiedzi), {String(meta.judge)} (sędzia), {String(meta.embedding)}, {String(meta.reranker)}.
          {date && ` Wygenerowano ${date}.`} Czasy mierzone przy kilku pytaniach naraz, więc percentyl 95 w tabeli jest zawyżony.
        </p>
      </div>
    </section>
  );
}
