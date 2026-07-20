import { useState } from "react";
import { Plus, Play, Trash2, Loader2 } from "lucide-react";
import { apiErrorMessage, runEval, RunRecord, ProviderConfig } from "../api/client";
import ScoreCard from "../components/ScoreCard";
import AssertionResultRow from "../components/AssertionResult";
import ProviderBadge from "../components/ProviderBadge";

interface AssertionDraft {
  type: string;
  params: Record<string, unknown>;
}

type FieldKind = "text" | "number" | "textarea" | "json";
interface FieldDef {
  key: string;
  label: string;
  kind: FieldKind;
  default: unknown;
  placeholder?: string;
}

const ASSERTION_SCHEMA: Record<string, { description: string; fields: FieldDef[] }> = {
  json_schema: {
    description: "Validate response is JSON matching a schema",
    fields: [{ key: "schema", label: "JSON schema", kind: "json", default: { type: "object" } }],
  },
  regex: {
    description: "Response must match regex pattern",
    fields: [{ key: "pattern", label: "Pattern", kind: "text", default: "", placeholder: "^[A-Z].*" }],
  },
  max_length: {
    description: "Response length must be ≤ value characters",
    fields: [{ key: "value", label: "Max chars", kind: "number", default: 500 }],
  },
  min_length: {
    description: "Response length must be ≥ value characters",
    fields: [{ key: "value", label: "Min chars", kind: "number", default: 50 }],
  },
  no_truncation: {
    description: "Detect mid-sentence cutoffs (no params needed)",
    fields: [],
  },
  semantic_similarity: {
    description: "Embedding similarity vs reference text",
    fields: [
      { key: "reference", label: "Reference text", kind: "textarea", default: "", placeholder: "Expected answer or ground truth" },
      { key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.7 },
    ],
  },
  answer_relevancy: {
    description: "LLM judge: does response answer the prompt?",
    fields: [{ key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.7 }],
  },
  faithfulness: {
    description: "Hybrid: LLM judge + embedding grounding vs source context",
    fields: [
      { key: "context", label: "Source context", kind: "textarea", default: "", placeholder: "Paste the source document the response must be grounded in" },
      { key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.8 },
    ],
  },
  llm_as_judge: {
    description: "Custom LLM-judged rubric",
    fields: [
      { key: "rubric", label: "Rubric", kind: "textarea", default: "Rate the overall quality of this response." },
      { key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.7 },
    ],
  },
  instruction_compliance: {
    description: "Did the response follow the given instruction?",
    fields: [
      { key: "rubric", label: "Instruction", kind: "textarea", default: "", placeholder: "e.g. Respond only in JSON" },
      { key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.7 },
    ],
  },
  prompt_injection_resistance: {
    description: "Detect compliance with injected instructions",
    fields: [{ key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.8 }],
  },
  consistency: {
    description: "Semantic agreement across repeated runs (case runs > 1 required)",
    fields: [{ key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.7 }],
  },
  recency_check: {
    description: "Detect stale-knowledge phrases",
    fields: [{ key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.7 }],
  },
  no_pii: {
    description: "Detect PII leakage — email, SSN, etc. (no params)",
    fields: [],
  },
  no_toxicity: {
    description: "Detect toxic content",
    fields: [{ key: "threshold", label: "Threshold (0-1)", kind: "number", default: 0.8 }],
  },
  max_latency_ms: {
    description: "Response latency must be ≤ value ms",
    fields: [{ key: "value", label: "Max ms", kind: "number", default: 10000 }],
  },
};

const ASSERTION_TYPES = Object.keys(ASSERTION_SCHEMA);

function defaultParams(type: string): Record<string, unknown> {
  const schema = ASSERTION_SCHEMA[type];
  if (!schema) return {};
  const out: Record<string, unknown> = {};
  for (const f of schema.fields) out[f.key] = f.default;
  return out;
}

const PROVIDER_MODELS: Record<string, { label: string; models: string[] }> = {
  openai: {
    label: "OpenAI",
    models: [
      "gpt-5.5",
      "gpt-5.5-pro",
      "gpt-5",
      "gpt-5-mini",
      "gpt-4o",
      "gpt-4o-mini",
      "o3-mini",
    ],
  },
  anthropic: {
    label: "Anthropic",
    models: [
      "claude-opus-4-8",
      "claude-opus-4-7",
      "claude-sonnet-4-6",
      "claude-sonnet-4-5",
      "claude-haiku-4-5-20251001",
      "claude-3-5-sonnet-20241022",
    ],
  },
};

const DEFAULT_MODELS: Record<string, string> = {
  openai: "gpt-5.5",
  anthropic: "claude-sonnet-4-6",
};

export default function RunEval() {
  const [prompt, setPrompt] = useState("Explain unit testing in two sentences.");
  const [providers, setProviders] = useState<ProviderConfig[]>([
    { name: "openai", model: DEFAULT_MODELS.openai },
  ]);
  const [assertions, setAssertions] = useState<AssertionDraft[]>([
    { type: "max_length", params: defaultParams("max_length") },
  ]);
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<RunRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  function addProviderRow() {
    setProviders((curr) => [...curr, { name: "anthropic", model: DEFAULT_MODELS.anthropic }]);
  }

  function updateProviderRow(i: number, patch: Partial<ProviderConfig>) {
    setProviders((curr) =>
      curr.map((p, idx) => {
        if (idx !== i) return p;
        const next = { ...p, ...patch };
        // If provider changed and current model doesn't belong, reset to default.
        if (patch.name && next.model && !PROVIDER_MODELS[next.name]?.models.includes(next.model)) {
          next.model = DEFAULT_MODELS[next.name] ?? "";
        }
        return next;
      })
    );
  }

  function removeProviderRow(i: number) {
    setProviders((curr) => curr.filter((_, idx) => idx !== i));
  }

  function addAssertion() {
    setAssertions((a) => [...a, { type: "min_length", params: defaultParams("min_length") }]);
  }
  function changeAssertionType(i: number, type: string) {
    setAssertions((a) => a.map((it, idx) => (idx === i ? { type, params: defaultParams(type) } : it)));
  }
  function updateAssertionParam(i: number, key: string, val: unknown) {
    setAssertions((a) =>
      a.map((it, idx) => (idx === i ? { ...it, params: { ...it.params, [key]: val } } : it))
    );
  }
  function removeAssertion(i: number) {
    setAssertions((a) => a.filter((_, idx) => idx !== i));
  }

  async function onRun() {
    setError(null);
    setLoading(true);
    setRecords([]);
    try {
      const payload = {
        prompt,
        providers,
        assertions: assertions.map((a) => ({ type: a.type, ...a.params })),
      };
      const res = await runEval(payload);
      setRecords(res.runs);
    } catch (error: unknown) {
      setError(apiErrorMessage(error, "Eval run failed"));
    } finally {
      setLoading(false);
    }
  }


  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold mb-1">Run an Eval</h1>
      <p className="text-muted text-sm mb-6">
        Send a single prompt to one or more providers, attach assertions, see scored results.
      </p>

      <div className="bg-card border border-border rounded-lg p-5 mb-6">
        <label className="block text-xs uppercase tracking-wider text-muted mb-2">Prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={5}
          className="w-full bg-bg border border-border rounded p-3 font-mono text-sm focus:outline-none focus:border-accent"
        />

        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs uppercase tracking-wider text-muted">Providers</label>
            <button
              onClick={addProviderRow}
              className="text-xs flex items-center gap-1 text-accent hover:underline"
            >
              <Plus className="w-3 h-3" /> Add
            </button>
          </div>
          <div className="flex flex-col gap-2">
            {providers.map((p, i) => {
              const config = PROVIDER_MODELS[p.name];
              return (
                <div key={i} className="flex items-center gap-2">
                  <select
                    value={p.name}
                    onChange={(e) => updateProviderRow(i, { name: e.target.value })}
                    className="bg-bg border border-border rounded p-2 text-sm w-36"
                  >
                    {Object.entries(PROVIDER_MODELS).map(([name, cfg]) => (
                      <option key={name} value={name}>{cfg.label}</option>
                    ))}
                  </select>
                  <select
                    value={p.model ?? DEFAULT_MODELS[p.name]}
                    onChange={(e) => updateProviderRow(i, { model: e.target.value })}
                    className="bg-bg border border-border rounded p-2 text-sm flex-1 min-w-[220px]"
                  >
                    {config?.models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => removeProviderRow(i)}
                    disabled={providers.length === 1}
                    className="text-muted hover:text-danger p-2 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-muted mt-2">
            Add multiple rows to compare models — e.g. Anthropic Opus vs Sonnet on the same prompt.
          </p>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs uppercase tracking-wider text-muted">Assertions</label>
            <button
              onClick={addAssertion}
              className="text-xs flex items-center gap-1 text-accent hover:underline"
            >
              <Plus className="w-3 h-3" /> Add
            </button>
          </div>
          <div className="space-y-3">
            {assertions.map((a, i) => {
              const schema = ASSERTION_SCHEMA[a.type];
              return (
                <div key={i} className="border border-border rounded p-3 bg-bg/40">
                  <div className="flex gap-2 items-start">
                    <div className="flex-1">
                      <select
                        value={a.type}
                        onChange={(e) => changeAssertionType(i, e.target.value)}
                        className="bg-bg border border-border rounded p-2 text-sm w-full"
                      >
                        {ASSERTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      {schema && (
                        <p className="text-xs text-muted mt-1">{schema.description}</p>
                      )}
                    </div>
                    <button
                      onClick={() => removeAssertion(i)}
                      className="text-muted hover:text-danger p-2"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {schema && schema.fields.length > 0 && (
                    <div className="mt-3 grid gap-2">
                      {schema.fields.map((f) => (
                        <AssertionField
                          key={f.key}
                          field={f}
                          value={a.params[f.key]}
                          onChange={(v) => updateAssertionParam(i, f.key, v)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <button
          onClick={onRun}
          disabled={loading || providers.length === 0}
          className="mt-5 inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Run
        </button>
        {error && <div className="mt-3 text-sm text-danger">{error}</div>}
      </div>

      {records.length > 0 && (
        <div className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            {records.map((r) => <ScoreCard key={r.id} record={r} />)}
          </div>
          {records.map((r) => (
            <div key={r.id + "-detail"} className="bg-card border border-border rounded-lg p-5">
              <div className="flex items-center gap-2 mb-3">
                <ProviderBadge name={r.provider} />
                <span className="text-xs text-muted">{r.timestamp}</span>
              </div>
              {r.results.map((er, i) => (
                <div key={i} className="border-t border-border pt-3 mt-3 first:border-0 first:pt-0 first:mt-0">
                  <div className="text-xs text-muted mb-1">Response ({er.latency_ms}ms, {er.tokens_used} tokens)</div>
                  <pre className="bg-bg p-3 rounded text-sm whitespace-pre-wrap font-mono mb-3">{er.response || "(empty)"}</pre>
                  <div>
                    {er.assertions.map((a, j) => <AssertionResultRow key={j} a={a} />)}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AssertionField({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const baseCls = "w-full bg-bg border border-border rounded p-2 text-sm";

  if (field.kind === "textarea") {
    return (
      <label className="block">
        <span className="text-xs text-muted">{field.label}</span>
        <textarea
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          className={`${baseCls} font-mono`}
        />
      </label>
    );
  }

  if (field.kind === "number") {
    return (
      <label className="block">
        <span className="text-xs text-muted">{field.label}</span>
        <input
          type="number"
          step="any"
          value={value === undefined || value === null ? "" : (value as number)}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
          className={baseCls}
        />
      </label>
    );
  }

  if (field.kind === "json") {
    const display = typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);
    return (
      <label className="block">
        <span className="text-xs text-muted">{field.label}</span>
        <textarea
          value={display}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value));
            } catch {
              onChange(e.target.value);
            }
          }}
          rows={4}
          className={`${baseCls} font-mono`}
        />
      </label>
    );
  }

  return (
    <label className="block">
      <span className="text-xs text-muted">{field.label}</span>
      <input
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        className={`${baseCls} font-mono`}
      />
    </label>
  );
}
