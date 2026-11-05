import type { ChatError, ChatPayload, Example, ProvisionResponse, Step } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

export interface ChatHandlers {
  onStep: (step: Step) => void;
  onDelta: (text: string) => void;
  onFinal: (payload: ChatPayload) => void;
  onError: (error: ChatError) => void;
}

/** POST /api/chat and parse the SSE stream (EventSource cannot POST, so we read the body). */
export async function streamChat(
  question: string,
  history: { role: "user" | "assistant"; content: string }[],
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, history }),
      signal,
    });
  } catch {
    handlers.onError({ code: "network", message: "Brak połączenia z serwerem. Czy backend działa?" });
    return;
  }
  if (!response.ok || !response.body) {
    handlers.onError({ code: "internal", message: `Błąd serwera (${response.status}).` });
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      dispatch(raw, handlers);
    }
  }
}

function dispatch(raw: string, handlers: ChatHandlers) {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!data.length) return;
  const parsed = JSON.parse(data.join("\n"));
  if (event === "step") handlers.onStep(parsed);
  else if (event === "delta") handlers.onDelta(parsed.text);
  else if (event === "final") handlers.onFinal(parsed);
  else if (event === "error") handlers.onError(parsed);
}

/**
 * Fire-and-forget wake-up: free hosting puts the backend and database to sleep when idle.
 * /api/health touches both, so they start booting before the visitor asks anything.
 */
export function wakeBackend(): void {
  fetch(`${BASE}/api/health`).catch(() => {
    // Nothing to show: if the backend is really down, the chat reports it on the first question.
  });
}

export async function fetchProvision(id: string): Promise<ProvisionResponse> {
  const res = await fetch(`${BASE}/api/provisions/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchExamples(): Promise<{ examples: Example[]; topics: string[] }> {
  const res = await fetch(`${BASE}/api/examples`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

