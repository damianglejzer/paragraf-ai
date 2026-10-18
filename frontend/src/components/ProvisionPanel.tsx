import { useEffect, useState } from "react";
import { fetchProvision } from "../api";
import type { Citation, ProvisionResponse, ProvisionView } from "../types";
import { StatusBadge } from "./AnswerView";
import { External, X } from "./Icons";

function highlight(text: string, quote: string | undefined) {
  const words = (quote ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return text;
  // match the quote word by word, allowing any whitespace (incl. line breaks) in between
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const match = new RegExp(escaped.join("\\s+"), "i").exec(text);
  if (!match) return text;
  return (
    <>
      {text.slice(0, match.index)}
      <mark>{match[0]}</mark>
      {text.slice(match.index + match[0].length)}
    </>
  );
}

function unitLabel(v: ProvisionView) {
  const m = v.citation.match(/(§ \S+|ust\. \S+)/);
  return m ? m[1] : v.citation;
}

export function ProvisionPanel({ target, onClose, onNavigate }: {
  target: { id: string; citation?: Citation };
  onClose: () => void;
  onNavigate: (id: string) => void;
}) {
  const [data, setData] = useState<ProvisionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    fetchProvision(target.id).then(setData).catch(() => setError("Nie udało się wczytać przepisu."));
  }, [target.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const article = data?.article ?? data?.provision;
  const focusId = data?.provision.id;
  const units = article?.children.length ? article.children : article ? [article] : [];
  const quote = target.citation?.quote;

  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <aside className="panel" aria-label="Podgląd przepisu">
        <div className="panel-head">
          <div style={{ flex: 1 }}>
            <h2>{article?.citation.replace(/ (§|ust\.) .*? (\w+)$/, " $2") ?? "…"}</h2>
            <div className="path">{data ? data.provision.full_path.split(", ").slice(0, -1).join(" › ") : ""}</div>
            {article?.hierarchy_titles.length ? <div className="path">{article.hierarchy_titles.filter(Boolean).join(" › ")}</div> : null}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Zamknij"><X /></button>
        </div>
        <div className="panel-body">
          {error && <div className="error">{error}</div>}
          {!data && !error && <div className="note"><span className="spinner" /> Wczytuję…</div>}
          {target.citation && (
            <div className="card" style={{ padding: "10px 12px" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                <strong style={{ fontSize: 13 }}>Cytat [{target.citation.index}]</strong>
                <StatusBadge status={target.citation.status} />
              </div>
              <div style={{ fontSize: 13.5 }}>Twierdzenie: {target.citation.claim}</div>
              {target.citation.explanation && <div className="note" style={{ marginTop: 4 }}>Weryfikator: {target.citation.explanation}</div>}
            </div>
          )}
          {units.map((u) => (
            <div key={u.id} className={`law-unit ${u.id === focusId && units.length > 1 ? "focus" : ""}`}>
              {units.length > 1 && <div className="u">{unitLabel(u)}</div>}
              <div className="law-text">{u.id === focusId || units.length === 1 ? highlight(u.text, quote) : u.text}</div>
            </div>
          ))}
          {article && article.references.length > 0 && (
            <div className="panel-section">
              <h3>Odesłania z tego przepisu</h3>
              {article.references.map((r) => (
                <button key={r} className="ref-chip" onClick={() => onNavigate(r)}>{prettyId(r)}</button>
              ))}
            </div>
          )}
          {data && (
            <div className="source">
              Źródło: {data.act.title} ({data.act.eli}){" "}
              <a href={data.act.source_url} target="_blank" rel="noreferrer">tekst w API ELI <External size={11} /></a>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

const SUP: Record<string, string> = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
export function prettyId(id: string) {
  const [act, art, unit] = id.split(":");
  const num = (s: string) => {
    const [base, ...rest] = s.split("_");
    return base + rest.map((r) => (/^\d+$/.test(r) ? r.split("").map((c) => SUP[c]).join("") : r)).join("");
  };
  let out = `art. ${num(art.replace("art_", ""))}`;
  if (unit?.startsWith("par_")) out += ` § ${num(unit.slice(4))}`;
  if (unit?.startsWith("ust_")) out += ` ust. ${num(unit.slice(4))}`;
  return `${out} ${act}`;
}
