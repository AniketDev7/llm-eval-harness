import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  timeout: 120_000,
});

export function apiErrorMessage(error: unknown, fallback = "Request failed"): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : fallback;
  }

  const detail = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg ?? String(item))
      .filter(Boolean)
      .join("; ");
  }

  // When Vite cannot connect to the API proxy target it returns a plain 500,
  // not FastAPI's normal JSON error envelope.
  const data = error.response?.data;
  const plainProxyFailure =
    error.response?.status === 500 &&
    (typeof data !== "object" || data === null);
  if (!error.response || plainProxyFailure) {
    return "Cannot reach the API backend. Start it in another terminal with: " +
      "python3 -m llm_eval.cli playground --no-browser";
  }

  return `${fallback} (HTTP ${error.response.status})`;
}

export interface AssertionResult {
  type: string;
  passed: boolean;
  score: number;
  detail: string;
}

export interface EvalResult {
  eval_name: string;
  category: string;
  provider: string;
  prompt: string;
  response: string;
  latency_ms: number;
  tokens_used: number;
  assertions: AssertionResult[];
  error?: string | null;
}

export interface RunRecord {
  id: string;
  timestamp: string;
  suite_name: string;
  suite_version: string;
  provider: string;
  composite_score: number;
  coverage_score: number;
  accuracy_score: number;
  format_score: number;
  hallucination_score: number;
  threshold_status: string;
  results: EvalResult[];
}

export interface RunRow {
  id: string;
  timestamp: string;
  suite_name: string;
  suite_version: string;
  provider: string;
  composite_score: number;
  coverage_score: number;
  accuracy_score: number;
  format_score: number;
  hallucination_score: number;
  threshold_status: string;
}

export interface ProviderConfig {
  name: string;
  model?: string;
}

export async function runEval(payload: {
  prompt: string;
  providers: ProviderConfig[];
  assertions: Array<Record<string, unknown>>;
  model_config_settings?: Record<string, unknown>;
  variables?: Record<string, unknown>;
}): Promise<{ runs: RunRecord[] }> {
  const res = await api.post("/run", payload);
  return res.data;
}

export async function listRuns(page = 1): Promise<{ runs: RunRow[] }> {
  const res = await api.get("/runs", { params: { page } });
  return res.data;
}

export async function getRunDetail(runId: string) {
  const res = await api.get(`/runs/${runId}`);
  return res.data;
}

export async function getHistory() {
  const res = await api.get("/history");
  return res.data as { history: Record<string, Array<{ timestamp: string; composite_score: number; threshold_status: string; run_id: string }>> };
}

export async function compareRuns(runA: string, runB: string) {
  const res = await api.get("/compare", { params: { run_a: runA, run_b: runB } });
  return res.data;
}

export function exportUrl(runId: string, format: "json" | "html") {
  return `/api/export/${runId}?format=${format}`;
}
