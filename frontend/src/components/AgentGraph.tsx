import { useEffect, useState } from "react";

type NodeId =
  | "start" | "plan" | "respond" | "endTop" | "gather" | "expand" | "answer" | "verify" | "endBottom";
type Kind = "llm" | "tool" | "plain" | "terminal";

interface GNode { id: NodeId; x: number; y: number; w: number; h: number; kind: Kind; name: string; sub: string }
interface GEdge {
  id: string; from: NodeId; to: NodeId; d: string; conditional?: boolean;
  label?: string; lx?: number; ly?: number; anchor?: "start" | "middle" | "end";
}
interface Chip { label: string; ok?: boolean }
interface Step {
  node: NodeId;
  edge?: string;
  title: string;
  text?: string;
  quote?: { label: string; value: string };
  chips?: Chip[];
}
interface Scenario { id: string; label: string; question: string; note?: string; steps: Step[] }

const NODES: GNode[] = [
  { id: "start", x: 18, y: 178, w: 40, h: 40, kind: "terminal", name: "START", sub: "" },
  { id: "plan", x: 70, y: 170, w: 130, h: 56, kind: "llm", name: "plan", sub: "decyzja + przepisanie" },
  { id: "respond", x: 340, y: 40, w: 200, h: 56, kind: "plain", name: "respond_directly", sub: "dopytanie albo odmowa" },
  { id: "endTop", x: 590, y: 48, w: 40, h: 40, kind: "terminal", name: "END", sub: "" },
  { id: "gather", x: 340, y: 170, w: 130, h: 56, kind: "tool", name: "gather", sub: "szukanie + narzędzia" },
  { id: "expand", x: 510, y: 170, w: 120, h: 56, kind: "tool", name: "expand", sub: "odesłania" },
  { id: "answer", x: 670, y: 170, w: 120, h: 56, kind: "llm", name: "answer", sub: "odpowiedź + cytaty" },
  { id: "verify", x: 865, y: 170, w: 110, h: 56, kind: "llm", name: "verify", sub: "sędzia cytatów" },
  { id: "endBottom", x: 900, y: 298, w: 40, h: 40, kind: "terminal", name: "END", sub: "" },
];
const N = Object.fromEntries(NODES.map((n) => [n.id, n])) as Record<NodeId, GNode>;

const EDGES: GEdge[] = [
  { id: "start-plan", from: "start", to: "plan", d: "M58 198 H68" },
  { id: "plan-respond", from: "plan", to: "respond", d: "M135 170 V68 H338", conditional: true,
    label: "clarify · refuse", lx: 143, ly: 120, anchor: "start" },
  { id: "respond-end", from: "respond", to: "endTop", d: "M540 68 H588" },
  { id: "plan-gather", from: "plan", to: "gather", d: "M200 198 H338", conditional: true,
    label: "search · lookup", lx: 269, ly: 216 },
  { id: "gather-expand", from: "gather", to: "expand", d: "M470 198 H508" },
  { id: "expand-answer", from: "expand", to: "answer", d: "M630 198 H668" },
  { id: "answer-verify", from: "answer", to: "verify", d: "M790 198 H863", conditional: true,
    label: "odpowiedź", lx: 826, ly: 216 },
  { id: "verify-end", from: "verify", to: "endBottom", d: "M920 226 V296" },
];

const SCENARIOS: Scenario[] = [
  {
    id: "regular",
    label: "Zwykłe pytanie",
    question: "Ile dni urlopu wypoczynkowego przysługuje mi po 12 latach pracy?",
    steps: [
      { node: "start", title: "Pytanie trafia do grafu", text: "Stan startowy: pytanie, pusta historia rozmowy." },
      {
        node: "plan", edge: "start-plan", title: "Decyzja: szukaj w przepisach",
        quote: { label: "Pytanie w języku ustawy", value: "Wymiar urlopu wypoczynkowego pracownika zatrudnionego przez okres 12 lat" },
      },
      {
        node: "gather", edge: "plan-gather", title: "Znaleziono 9 przepisów",
        chips: [{ label: "art. 154 § 1 KP" }, { label: "art. 154 § 2 KP" }, { label: "art. 167³ KP" }, { label: "art. 153 § 1 KP" }, { label: "+5" }],
      },
      { node: "expand", edge: "gather-expand", title: "Brak dodatkowych odesłań", text: "Znalezione przepisy nie odsyłają do innych, lista bez zmian." },
      {
        node: "answer", edge: "expand-answer", title: "Odpowiedź z 1 cytatem",
        quote: { label: "Odpowiedź", value: "Po 12 latach pracy przysługuje Ci 26 dni urlopu [1]." },
      },
      {
        node: "verify", edge: "answer-verify", title: "Cytat zweryfikowany",
        chips: [{ label: "art. 154 § 1 KP", ok: true }, { label: "przepis istnieje", ok: true }, { label: "cytat zgodny w 100%", ok: true }, { label: "sędzia: popiera", ok: true }],
      },
      { node: "endBottom", edge: "verify-end", title: "Wynik trafia do czatu", text: "Odpowiedź, karty cytatów, kroki agenta i metryki." },
    ],
  },
  {
    id: "clarify",
    label: "Dopytanie",
    question: "Mam problem w pracy, co robić?",
    steps: [
      { node: "start", title: "Pytanie trafia do grafu", text: "Stan startowy: pytanie, pusta historia rozmowy." },
      {
        node: "plan", edge: "start-plan", title: "Decyzja: dopytaj",
        quote: { label: "Wiadomość planera", value: "Czy problem dotyczy umowy o pracę, czasu pracy, nadgodzin czy urlopu?" },
      },
      { node: "respond", edge: "plan-respond", title: "Pytanie doprecyzowujące trafia do użytkownika", text: "Bez wyszukiwania i bez kolejnego wywołania LLM." },
      {
        node: "endTop", edge: "respond-end", title: "Koniec",
        text: "Odpowiedź użytkownika wróci w następnym pytaniu jako historia rozmowy.",
        chips: [{ label: "1 wywołanie LLM" }, { label: "~1 s" }],
      },
    ],
  },
];

interface NodeInfo { reads: string; calls: string; writes: string }
const INFO: Record<NodeId, NodeInfo> = {
  start: { reads: "—", calls: "—", writes: "stan początkowy: question, history, steps = []" },
  plan: { reads: "question, history, today", calls: "LLM (Gemini) ze schematem Plan", writes: "plan (action, search_query, references, message), today, steps" },
  respond: { reads: "plan.action, plan.message", calls: "nic — ani LLM, ani bazy", writes: "answer (status clarify / refuse), checks = []" },
  endTop: { reads: "cały stan", calls: "—", writes: "stan końcowy → API → frontend" },
  gather: { reads: "plan, question", calls: "get_article (wskazane artykuły), search_law → Jina: embeddingi + reranker", writes: "hits (przepisy do kontekstu), steps" },
  expand: { reads: "hits", calls: "follow_reference — tabela provision_refs, bez AI", writes: "hits (+ maks. 3 przepisy z odesłań), steps" },
  answer: { reads: "question, hits, history", calls: "LLM (Gemini) ze schematem Answer — przepisy podane jako tekst <przepis id=…>", writes: "answer (status, tekst z [1] [2], citations), steps" },
  verify: { reads: "answer", calls: "baza (czy przepis istnieje) · rapidfuzz (czy cytat jest w tekście) · LLM-sędzia (czy popiera)", writes: "answer (bez błędnych cytatów), checks (status każdego cytatu), steps" },
  endBottom: { reads: "cały stan", calls: "—", writes: "stan końcowy → API → frontend" },
};

const KIND_LABEL: Record<Kind, string> = { llm: "LLM", tool: "narzędzia", plain: "bez LLM", terminal: "" };

export function AgentGraph() {
  const [scenarioId, setScenarioId] = useState("regular");
  const scenario = SCENARIOS.find((s) => s.id === scenarioId)!;
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<NodeId>("plan");

  useEffect(() => {
    if (!playing) return;
    if (step >= scenario.steps.length - 1) { setPlaying(false); return; }
    const t = window.setTimeout(() => setStep((s) => s + 1), 1100);
    return () => window.clearTimeout(t);
  }, [playing, step, scenario.steps.length]);

  useEffect(() => { setSelected(scenario.steps[step].node); }, [step, scenario]);

  const last = scenario.steps.length - 1;
  const pick = (id: string) => { setScenarioId(id); setPlaying(false); setStep(0); };
  const play = () => { setStep(0); setPlaying(true); };
  const go = (i: number) => { setPlaying(false); setStep(Math.max(0, Math.min(last, i))); };

  const visible = scenario.steps.slice(0, step + 1);
  const activeNodes = new Set(visible.map((s) => s.node));
  const activeEdges = new Set(visible.map((s) => s.edge).filter(Boolean) as string[]);
  const current = scenario.steps[step].node;
  const order = (id: NodeId) => visible.map((s, i) => (s.node === id ? i : -1)).filter((i) => i > 0);

  const info = INFO[selected];
  const node = N[selected];

  return (
    <div className="agent-graph">
      <div className="scenario-bar">
        {SCENARIOS.map((s) => (
          <button key={s.id} className={`scenario ${s.id === scenarioId ? "active" : ""}`} onClick={() => pick(s.id)}>{s.label}</button>
        ))}
        <button className="play" onClick={play} disabled={playing}>{playing ? "Odtwarzam…" : "▶ Odtwórz krok po kroku"}</button>
      </div>
      <div className="scenario-q">Pytanie: <em>„{scenario.question}”</em>{scenario.note && <span className="note"> · {scenario.note}</span>}</div>

      <div className="card graph-card">
        <svg viewBox="0 0 990 360" role="img" aria-label="Graf agenta LangGraph">
          <defs>
            <marker id="ga" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 10 5 0 10z" fill="var(--text-3)" />
            </marker>
            <marker id="ga-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 10 5 0 10z" fill="var(--primary-2)" />
            </marker>
          </defs>

          {EDGES.map((e) => {
            const on = activeEdges.has(e.id);
            return (
              <g key={e.id} className={`g-edge ${on ? "on" : ""}`}>
                <path d={e.d} fill="none" strokeDasharray={e.conditional ? "5 4" : undefined} markerEnd={on ? "url(#ga-on)" : "url(#ga)"} />
                {e.label && <text x={e.lx} y={e.ly} textAnchor={e.anchor ?? "middle"} className="g-edge-label">{e.label}</text>}
              </g>
            );
          })}

          {NODES.map((n) => {
            const on = activeNodes.has(n.id);
            const isCurrent = n.id === current;
            const nums = order(n.id);
            if (n.kind === "terminal") {
              return (
                <g key={n.id} className={`g-node terminal ${on ? "on" : ""}`} onClick={() => setSelected(n.id)}>
                  <circle cx={n.x + 20} cy={n.y + 20} r={20} />
                  <text x={n.x + 20} y={n.y + 24} textAnchor="middle">{n.name}</text>
                </g>
              );
            }
            return (
              <g key={n.id} className={`g-node ${n.kind} ${on ? "on" : ""} ${isCurrent ? "current" : ""} ${selected === n.id ? "selected" : ""}`}
                 onClick={() => setSelected(n.id)} role="button" tabIndex={0}
                 onKeyDown={(ev) => ev.key === "Enter" && setSelected(n.id)}>
                <rect x={n.x} y={n.y} width={n.w} height={n.h} rx={12} />
                <text x={n.x + n.w / 2} y={n.y + 24} textAnchor="middle" className="g-name">{n.name}</text>
                <text x={n.x + n.w / 2} y={n.y + 42} textAnchor="middle" className="g-sub">{n.sub}</text>
                {KIND_LABEL[n.kind] && (
                  <text x={n.x + n.w - 8} y={n.y - 6} textAnchor="end" className={`g-kind ${n.kind}`}>{KIND_LABEL[n.kind]}</text>
                )}
                {nums.length > 0 && (
                  <g>
                    <rect x={n.x - 8} y={n.y - 10} width={nums.length > 1 ? 34 : 20} height={20} rx={10} className="g-badge" />
                    <text x={n.x - 8 + (nums.length > 1 ? 17 : 10)} y={n.y + 4} textAnchor="middle" className="g-badge-t">{nums.join("·")}</text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>

        <div className="graph-legend">
          <span><i className="lg llm" /> węzeł z wywołaniem LLM</span>
          <span><i className="lg tool" /> narzędzia / baza</span>
          <span><i className="lg plain" /> bez LLM</span>
          <span><i className="lg dashed" /> krawędź warunkowa</span>
          <span className="note">Kliknij węzeł, aby zobaczyć jego wejście i wyjście.</span>
        </div>
      </div>

      <div className="graph-detail">
        <div className="card info">
          <h3><code>{node.name}</code>{KIND_LABEL[node.kind] && <span className={`g-pill ${node.kind}`}>{KIND_LABEL[node.kind]}</span>}</h3>
          <dl className="io">
            <dt>Czyta ze stanu</dt><dd>{info.reads}</dd>
            <dt>Wywołuje</dt><dd>{info.calls}</dd>
            <dt>Zapisuje do stanu</dt><dd>{info.writes}</dd>
          </dl>
        </div>
        <div className="card info step-card">
          <h3>Przebieg: {scenario.label.toLowerCase()}</h3>
          {/* Every step of every scenario shares one grid cell, so the card keeps the height of the tallest. */}
          <div className="step-stack">
            {SCENARIOS.flatMap((sc) =>
              sc.steps.map((s, i) => {
                const active = sc.id === scenarioId && i === step;
                return (
                  <div key={`${sc.id}-${i}`} className={`step-view ${active ? "active" : ""}`} aria-hidden={!active}>
                    <div className="step-head">
                      <span className="step-num">{i + 1}</span>
                      <code>{N[s.node].name}</code>
                      {KIND_LABEL[N[s.node].kind] && <span className={`g-pill ${N[s.node].kind}`}>{KIND_LABEL[N[s.node].kind]}</span>}
                    </div>
                    <strong className="step-title">{s.title}</strong>
                    {s.text && <p>{s.text}</p>}
                    {s.quote && <blockquote><span>{s.quote.label}</span>„{s.quote.value}”</blockquote>}
                    {s.chips && (
                      <div className="t-chips">
                        {s.chips.map((c) => <span key={c.label} className={`chip ${c.ok ? "ok" : ""}`}>{c.ok && "✓ "}{c.label}</span>)}
                      </div>
                    )}
                  </div>
                );
              }),
            )}
          </div>
          <div className="step-nav">
            <button className="step-btn" onClick={() => go(step - 1)} disabled={step === 0} aria-label="Poprzedni krok">← Wstecz</button>
            <div className="step-dots">
              {scenario.steps.map((s, i) => (
                <button key={i} className={`step-dot ${i === step ? "now" : i < step ? "done" : ""}`} onClick={() => go(i)}
                  aria-label={`Krok ${i + 1}: ${N[s.node].name}`} title={N[s.node].name} />
              ))}
            </div>
            <button className="step-btn primary" onClick={() => go(step + 1)} disabled={step === last} aria-label="Następny krok">Dalej →</button>
          </div>
          <div className="step-count">Krok {step + 1} z {scenario.steps.length}</div>
        </div>
      </div>

      <div className="grid-3 lg-concepts">
        <div className="card info"><h3>Stan (<code>AgentState</code>)</h3><p>Słownik, który „płynie” przez graf: pytanie, plan, znalezione przepisy, odpowiedź, wyniki weryfikacji. Węzeł zwraca tylko pola, które zmienia — LangGraph scala je ze stanem.</p></div>
        <div className="card info"><h3>Węzły</h3><p>Zwykłe funkcje Pythona: dostają stan, zwracają zmiany. Trzy z nich wywołują LLM (plan, answer, verify), reszta to kod deterministyczny i baza.</p></div>
        <div className="card info"><h3>Krawędzie warunkowe</h3><p>Funkcje routujące (<code>_route</code>, <code>_route_after_answer</code>) patrzą na stan i wybierają następny węzeł: odmowa kończy graf od razu, odpowiedź idzie do weryfikacji.</p></div>
        <div className="card info"><h3>Weryfikacja w grafie</h3><p>Węzeł <code>verify</code> działa przed wysłaniem wyniku: cytaty ocenione jako błędne są usuwane z odpowiedzi, zanim trafi ona do użytkownika.</p></div>
        <div className="card info"><h3>Streaming</h3><p><code>graph.stream(stream_mode="updates")</code> oddaje zmiany po każdym węźle — backend wysyła je przez SSE i stąd kroki agenta widać na żywo w czacie.</p></div>
        <div className="card info"><h3>Dlaczego nie pętla ReAct</h3><p>Agent, który sam w pętli wybiera narzędzia, zużywa 5–10 wywołań LLM na pytanie. Tu planer decyduje raz, więc pytanie kosztuje stałe 3 wywołania — mieści się w darmowym limicie.</p></div>
      </div>

      <details className="card code-block">
        <summary>Kod budujący graf (<code>backend/paragraf/agent/graph.py</code>)</summary>
        <pre>{`graph = StateGraph(AgentState)
graph.add_node("plan", self.plan)
graph.add_node("respond_directly", self.respond_directly)
graph.add_node("gather", self.gather)
graph.add_node("expand", self.expand)
graph.add_node("answer", self.answer)
graph.add_node("verify", self.verify)

graph.add_edge(START, "plan")
graph.add_conditional_edges("plan", _route, ["respond_directly", "gather"])
graph.add_edge("respond_directly", END)
graph.add_edge("gather", "expand")
graph.add_edge("expand", "answer")
graph.add_conditional_edges("answer", _route_after_answer, ["verify", END])
graph.add_edge("verify", END)
return graph.compile()`}</pre>
      </details>
    </div>
  );
}
