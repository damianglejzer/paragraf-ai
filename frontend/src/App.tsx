import { useCallback, useEffect, useRef, useState } from "react";
import { fetchExamples, streamChat } from "./api";
import { AnswerView } from "./components/AnswerView";
import { HowItWorks } from "./components/HowItWorks";
import { Alert, Check, Moon, Send, Sun } from "./components/Icons";
import { ProvisionPanel } from "./components/ProvisionPanel";
import type { AssistantMessage, Citation, Example, Message } from "./types";

const MAX_CHARS = 500;
const FALLBACK_EXAMPLES: Example[] = [
  { label: "Zwolnienie na L4", question: "Czy mogę zostać zwolniony, kiedy jestem na L4?" },
  { label: "Urlop", question: "Ile dni urlopu wypoczynkowego przysługuje mi po 12 latach pracy?" },
  { label: "Ciąża", question: "Czy pracodawca może mnie zwolnić, kiedy jestem w ciąży? A co, jeśli mam umowę na czas określony albo na okres próbny?" },
  { label: "Wypowiedzenie", question: "Jak długi jest mój okres wypowiedzenia, jeśli pracuję w firmie od 4 lat?" },
  { label: "Zaległy urlop", question: "Co się stanie z moim niewykorzystanym urlopem z zeszłego roku? Czy przepada, jeśli nie wykorzystam go do końca września?" },
];
const uid = () => Math.random().toString(36).slice(2);

function getTheme(): "light" | "dark" {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage unavailable */ }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [tab, setTab] = useState<"chat" | "how">("chat");
  const [theme, setTheme] = useState(getTheme);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [examples, setExamples] = useState<Example[]>(FALLBACK_EXAMPLES);
  const [topics, setTopics] = useState<string[]>([]);
  const [panel, setPanel] = useState<{ id: string; citation?: Citation } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch { /* ignore */ }
  }, [theme]);

  useEffect(() => {
    fetchExamples().then((d) => { setExamples(d.examples); setTopics(d.topics); }).catch(() => undefined);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const update = (id: string, fn: (m: AssistantMessage) => AssistantMessage) =>
    setMessages((ms) => ms.map((m) => (m.id === id && m.role === "assistant" ? fn(m) : m)));

  const ask = useCallback(async (question: string, prior: Message[]) => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setInput("");
    const botId = uid();
    const history = prior
      .filter((m) => m.role === "user" || (m.role === "assistant" && m.payload))
      .map((m) => ({ role: m.role, content: m.role === "user" ? m.text : (m as AssistantMessage).payload!.answer }))
      .slice(-6);
    // only keep history when the assistant asked a clarifying question last
    const last = prior[prior.length - 1];
    const useHistory = last?.role === "assistant" && last.payload?.status === "clarify";
    setMessages([...prior, { role: "user", id: uid(), text: q }, { role: "assistant", id: botId, steps: [], text: "", payload: null, error: null, pending: true }]);
    await streamChat(q, useHistory ? history : [], {
      onStep: (s) => update(botId, (m) => ({ ...m, steps: [...m.steps, s] })),
      onDelta: (t) => update(botId, (m) => ({ ...m, text: m.text + t })),
      onFinal: (p) => update(botId, (m) => ({ ...m, payload: p, steps: p.steps.length ? p.steps : m.steps, pending: false })),
      onError: (e) => update(botId, (m) => ({ ...m, error: e, pending: false })),
    });
    update(botId, (m) => ({ ...m, pending: false }));
    setBusy(false);
    inputRef.current?.focus();
  }, [busy]);

  const retry = (botId: string) => {
    const idx = messages.findIndex((m) => m.id === botId);
    const user = messages[idx - 1];
    if (user?.role === "user") ask(user.text, messages.slice(0, idx - 1));
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">§</div>
          <div>Paragraf AI<small>asystent prawa z weryfikacją cytatów</small></div>
        </div>
        <nav className="tabs">
          <button className={`tab ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>Asystent</button>
          <button className={`tab ${tab === "how" ? "active" : ""}`} onClick={() => setTab("how")}>Jak to działa</button>
        </nav>
        <div className="spacer" />
        <div className="disclaimer"><Alert size={13} /> To nie jest porada prawna</div>
        <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Zmień motyw">
          {theme === "dark" ? <Sun /> : <Moon />}
        </button>
      </header>

      <div className="main">
        {tab === "how" ? (
          <HowItWorks />
        ) : (
          <div className="chat-col">
            <div className="scroll" ref={scrollRef}>
              <div className="thread">
                {messages.length === 0 && (
                  <div className="hero">
                    <h1>Odpowiedzi tylko z ustaw.<br /><em>Bez halucynacji.</em></h1>
                    <p>
                      Agent AI odpowiada na pytania z prawa pracy na podstawie całego Kodeksu pracy — zawsze
                      wskazując konkretny artykuł, paragraf lub ustęp. Osobny krok automatycznie weryfikuje, czy
                      cytowany przepis istnieje i naprawdę popiera odpowiedź.
                    </p>
                    <div className="features">
                      <span className="feature"><Check size={13} /> oficjalne teksty z API Sejmu</span>
                      <span className="feature"><Check size={13} /> weryfikacja każdego cytatu</span>
                      <span className="feature"><Check size={13} /> odmawia, gdy nie ma podstawy</span>
                    </div>
                    <div className="examples">
                      {examples.map((e) => (
                        <button key={e.question} className="example" onClick={() => ask(e.question, messages)}>
                          <div className="label">{e.label}</div>
                          <div className="q">{e.question}</div>
                        </button>
                      ))}
                    </div>
                    {topics.length > 0 && <div className="topics">Zakres demo: {topics.join(" · ")}</div>}
                  </div>
                )}
                {messages.map((m) =>
                  m.role === "user" ? (
                    <div key={m.id} className="msg-user">{m.text}</div>
                  ) : (
                    <AnswerView key={m.id} msg={m} onOpen={(c) => setPanel({ id: c.provision_id, citation: c })} onRetry={() => retry(m.id)} />
                  ),
                )}
              </div>
            </div>
            <div className="composer-wrap">
              <form className="card composer" onSubmit={(e) => { e.preventDefault(); ask(input, messages); }}>
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  maxLength={MAX_CHARS}
                  placeholder="Np. Czy pracodawca może odmówić mi urlopu na żądanie?"
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input, messages); } }}
                  aria-label="Pytanie"
                />
                {input.length > MAX_CHARS * 0.7 && <span className="count">{input.length}/{MAX_CHARS}</span>}
                <button className="send" type="submit" disabled={busy || !input.trim()}><Send size={15} /> Zapytaj</button>
              </form>
              <div className="composer-hint">Odpowiedzi generuje AI i mogą zawierać błędy · to nie jest porada prawna</div>
            </div>
          </div>
        )}
        {panel && tab === "chat" && (
          <ProvisionPanel target={panel} onClose={() => setPanel(null)} onNavigate={(id) => setPanel({ id })} />
        )}
      </div>
    </div>
  );
}
