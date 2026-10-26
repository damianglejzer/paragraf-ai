export type CitationStatus = "verified" | "uncertain" | "wrong";
export type AnswerStatus = "answer" | "clarify" | "refuse";

export interface Step {
  node: "plan" | "gather" | "expand" | "answer" | "verify" | string;
  title: string;
  ms: number;
  detail: Record<string, unknown>;
}

export interface Citation {
  index: number;
  provision_id: string;
  citation: string | null;
  quote: string;
  claim: string;
  status: CitationStatus;
  verdict: string | null;
  explanation: string;
  quote_score: number | null;
}

export interface ChatPayload {
  status: AnswerStatus;
  answer: string;
  citations: Citation[];
  steps: Step[];
  rewrite: string | null;
  metrics: {
    total_ms: number;
    tokens: number;
    llm_calls: number;
    cost_usd: number;
  };
  cached: boolean;
}

export interface ChatError {
  code: "too_long" | "budget" | "rate_limited" | "busy" | "internal" | "network";
  message: string;
}

export interface UserMessage {
  role: "user";
  id: string;
  text: string;
}

export interface AssistantMessage {
  role: "assistant";
  id: string;
  steps: Step[];
  text: string;
  payload: ChatPayload | null;
  error: ChatError | null;
  pending: boolean;
}

export type Message = UserMessage | AssistantMessage;

export interface ProvisionView {
  id: string;
  citation: string;
  full_path: string;
  text: string;
  hierarchy_titles: string[];
  children: ProvisionView[];
  references: string[];
}

export interface ProvisionResponse {
  provision: ProvisionView;
  article: ProvisionView | null;
  act: { code: string; name: string; eli: string; title: string; announcement_date: string; source_url: string };
}

export interface Example {
  label: string;
  question: string;
}
