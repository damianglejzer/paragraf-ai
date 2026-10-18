import { useState } from "react";
import type { Step } from "../types";
import { Check, Chevron } from "./Icons";

const NEXT_LABEL: Record<string, string> = {
  start: "Analizuję pytanie",
  plan: "Szukam przepisów",
  gather: "Sprawdzam odesłania",
  expand: "Piszę odpowiedź z cytatami",
  answer: "Weryfikuję cytaty",
};

function StepDetail({ step }: { step: Step }) {
  const d = step.detail as Record<string, unknown>;
  if (step.node === "plan" && typeof d.search_query === "string" && d.search_query) {
    return <div className="sub">Zapytanie w języku ustawy: „{d.search_query}”</div>;
  }
  if (step.node === "gather" && Array.isArray(d.hits)) {
    return (
      <div className="sub">
        {(d.hits as string[]).slice(0, 8).map((h) => (
          <span className="chip" key={h}>{h}</span>
        ))}
        {typeof d.deadline === "string" && <span className="chip">termin: {d.deadline}</span>}
      </div>
    );
  }
  if (step.node === "expand" && Array.isArray(d.added)) {
    const added = d.added as string[];
    return <div className="sub">{added.length ? <>Dołączono: {added.map((a) => <span className="chip" key={a}>{a}</span>)}</> : "Brak dodatkowych odesłań"}</div>;
  }
  if (step.node === "verify") {
    return (
      <div className="sub">
        zweryfikowane: {String(d.verified ?? 0)} · niepewne: {String(d.uncertain ?? 0)} · odrzucone: {String(d.wrong ?? 0)}
      </div>
    );
  }
  return null;
}

export function AgentTrace({ steps, pending }: { steps: Step[]; pending: boolean }) {
  const [open, setOpen] = useState(true);
  const total = steps.reduce((s, x) => s + x.ms, 0);
  const last = steps.length ? steps[steps.length - 1].node : "start";
  const finishedEarly = last === "plan" && steps[0]?.detail?.action && ["clarify", "refuse"].includes(String(steps[0].detail.action));
  const running = pending && !finishedEarly && last !== "verify" ? NEXT_LABEL[last] : null;

  return (
    <div className="card trace">
      <button className="trace-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <strong>Kroki agenta</strong>
        <span>· {steps.length} {pending ? "" : `· ${(total / 1000).toFixed(1)} s`}</span>
        <span className={`chev ${open ? "open" : ""}`}><Chevron /></span>
      </button>
      {open && (
        <ol className="trace-steps">
          {steps.map((s, i) => (
            <li className="trace-step" key={i}>
              <span className="dot"><Check size={13} /></span>
              <div>
                {s.title}
                <StepDetail step={s} />
              </div>
              <span className="ms">{s.ms} ms</span>
            </li>
          ))}
          {running && (
            <li className="trace-step">
              <span className="dot run"><span className="spinner" /></span>
              <div>{running}…</div>
              <span />
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
