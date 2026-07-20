import { useState } from "react";
import { Upload, Play, Loader2 } from "lucide-react";
import { api, apiErrorMessage, RunRecord } from "../api/client";
import ScoreCard from "../components/ScoreCard";
import AssertionResultRow from "../components/AssertionResult";

const SAMPLE = `name: inline-suite
version: "1.0"
providers: [openai]
model_config:
  temperature: 0.1
  max_tokens: 300
thresholds:
  review: 0.80
  alert: 0.70
  pause: 0.60
evals:
  - name: hello_world
    category: format
    prompt: "Say hello."
    assertions:
      - type: min_length
        value: 1
      - type: max_length
        value: 200
`;

export default function LoadSuite() {
  const [yamlText, setYamlText] = useState(SAMPLE);
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<RunRecord[]>([]);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then(setYamlText);
  }

  async function onRun() {
    setError(null);
    setLoading(true);
    setRecords([]);
    setLog([]);
    try {
      setLog(["validating suite", "running configured providers and assertions"]);
      const response = await api.post("/run-suite", { yaml_text: yamlText });
      setRecords(response.data.runs);
      setLog((current) => [...current, `completed: ${response.data.runs.length} provider run(s)`]);
    } catch (error: unknown) {
      setError(apiErrorMessage(error, "Suite run failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold mb-1">Load Suite</h1>
      <p className="text-muted text-sm mb-6">
        Paste or upload a YAML suite. For the canonical experience use the CLI: <code className="text-accent">llm-eval run evals/quickstart.yaml</code>
      </p>

      <div className="bg-card border border-border rounded-lg p-5 mb-6">
        <div className="flex justify-between items-center mb-2">
          <label className="text-xs uppercase tracking-wider text-muted">YAML</label>
          <label className="text-xs flex items-center gap-1 text-accent cursor-pointer hover:underline">
            <Upload className="w-3 h-3" /> Upload
            <input type="file" accept=".yaml,.yml" className="hidden" onChange={onFile} />
          </label>
        </div>
        <textarea
          value={yamlText}
          onChange={(e) => setYamlText(e.target.value)}
          rows={18}
          className="w-full bg-bg border border-border rounded p-3 font-mono text-xs focus:outline-none focus:border-accent"
        />
        <button
          onClick={onRun}
          disabled={loading}
          className="mt-4 inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Run Suite
        </button>
        {error && <div className="mt-3 text-sm text-danger">{error}</div>}
      </div>

      {log.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <div className="text-xs uppercase text-muted mb-2">Progress</div>
          <pre className="text-xs font-mono">{log.join("\n")}</pre>
        </div>
      )}

      {records.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          {records.map((r) => (
            <div key={r.id} className="space-y-3">
              <ScoreCard record={r} />
              <div className="bg-card border border-border rounded-lg p-4">
                {r.results.map((er, i) => (
                  <div key={i}>
                    <div className="text-xs font-mono text-muted">{er.eval_name}</div>
                    {er.assertions.map((a, j) => <AssertionResultRow key={j} a={a} />)}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
