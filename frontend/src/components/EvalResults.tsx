type Num = number | null | undefined;
interface RetrievalRow { mode: string; n: number; overall: Record<string, Num> }
interface GenSummary {
  n: number;
  correctness: Num; citation_accuracy: Num; citation_wrong_rate: Num;
  oos_refusal_rate: Num; false_refusal_rate: Num;
  by_category: Record<string, { n: number }>;
}
interface GenRow { config: string; summary: GenSummary }
export interface EvalReport {
  meta: Record<string, string | number>;
  dataset?: { n: number; by_category: Record<string, number> };
  retrieval?: RetrievalRow[];
  generation?: GenRow[];
}

const CATEGORY: Record<string, string> = {
  regular: "zwykłych",
  multi: "wymagających kilku przepisów",
  tricky: "podchwytliwych",
  out_of_scope: "spoza zakresu",
};

const ok = (v: Num): v is number => typeof v === "number" && !Number.isNaN(v);
const pct = (v: Num) => (ok(v) ? `${Math.round(v * 100)}%` : "—");

interface Test {
  question: string;
  how: string;
  value: string;
  share: Num; // 0..1 for the meter; null hides it
  baseline?: string; // the same test for a plain RAG
}

function TestRow({ n, t }: { n: number; t: Test }) {
  return (
    <li className="ev-test">
      <span className="ev-test-n">{n}</span>
      <div className="ev-test-body">
        <h3>{t.question}</h3>
        <p>{t.how}</p>
      </div>
      <div className="ev-test-result">
        <span className="ev-test-v">{t.value}</span>
        {ok(t.share) && (
          <span className="ev-meter" aria-hidden><span style={{ width: `${Math.round(t.share * 100)}%` }} /></span>
        )}
        {t.baseline && <span className="ev-test-base">{t.baseline}</span>}
      </div>
    </li>
  );
}

export function EvalResults({ report }: { report: EvalReport | null | undefined }) {
  if (report === undefined) return <div className="note"><span className="spinner" /> Wczytuję wyniki testów…</div>;
  if (report === null || !report.generation?.length) {
    return (
      <div className="card info">
        <h3>Brak wyników testów</h3>
        <p>Uruchom <code>uv run python -m paragraf.evaluation.run_all</code>, aby je wygenerować.</p>
      </div>
    );
  }

  const gen = report.generation;
  const final = gen[gen.length - 1].summary;
  const naive = gen.find((g) => g.config === "naive")?.summary;
  const found = report.retrieval?.find((r) => r.mode === "full")?.overall["recall@5"];
  const ds = report.dataset;
  const oosN = final.by_category.out_of_scope?.n ?? 0;
  const inScopeN = final.n - oosN;
  const count = (rate: Num, of: number) => (ok(rate) ? `${Math.round(rate * of)} z ${of}` : "—");
  const vsNaive = (v: Num) => (ok(v) ? `zwykły RAG: ${pct(v)}` : undefined);

  const tests: Test[] = [
    {
      question: "Czy odpowiedź jest poprawna?",
      how: "Osobny model-sędzia porównuje każdą odpowiedź z odpowiedzią wzorcową.",
      value: pct(final.correctness),
      share: final.correctness,
      baseline: vsNaive(naive?.correctness),
    },
    {
      question: "Czy cytowane przepisy są prawdziwe i popierają odpowiedź?",
      how: "Sprawdzamy, czy przepis istnieje, czy cytat naprawdę w nim jest i czy potwierdza tezę.",
      value: pct(final.citation_accuracy),
      share: final.citation_accuracy,
      baseline: vsNaive(naive?.citation_accuracy),
    },
    {
      question: "Czy do użytkownika trafia błędny cytat?",
      how: "Cytaty, które nie przejdą weryfikacji, są usuwane z odpowiedzi.",
      value: pct(final.citation_wrong_rate),
      share: null,
      baseline: vsNaive(naive?.citation_wrong_rate),
    },
    {
      question: "Czy agent znajduje właściwy przepis?",
      how: "Oczekiwany artykuł jest wśród 5 pierwszych przepisów, które trafiają do modelu.",
      value: pct(found),
      share: found,
    },
    {
      question: "Czy odmawia, gdy pytanie wykracza poza zakres?",
      how: "Pytania z innych dziedzin (prawo karne, gotowanie…) mają dostać odmowę, a nie zgadywanie.",
      value: count(final.oos_refusal_rate, oosN),
      share: final.oos_refusal_rate,
    },
    {
      question: "Czy nie odmawia bez powodu?",
      how: "Pytania z zakresu, na które agent niepotrzebnie odmówił odpowiedzi.",
      value: count(final.false_refusal_rate, inScopeN),
      share: null,
    },
  ];

  return (
    <section className="ev">
      <div>
        <h2>Wyniki testów</h2>
        <p className="lead" style={{ marginTop: 0 }}>
          System odpowiedział na {ds?.n ?? final.n} pytań testowych
          {ds && <> ({Object.entries(ds.by_category).map(([c, n]) => `${n} ${CATEGORY[c] ?? c}`).join(", ")})</>}.
          Dla porównania te same pytania dostał zwykły RAG: tekst pocięty na fragmenty, bez struktury ustawy i bez
          weryfikacji cytatów.
        </p>
      </div>

      <ol className="card ev-tests">
        {tests.map((t, i) => <TestRow key={t.question} n={i + 1} t={t} />)}
      </ol>

      <p className="note">Modele: {String(report.meta.llm)} (odpowiedzi), {String(report.meta.judge)} (sędzia).</p>
    </section>
  );
}
