import { useEffect, useState } from "react";
import { apiErrorMessage, compareRuns, listRuns, RunRow } from "../api/client";
import ScoreCard from "../components/ScoreCard";
import ProviderBadge from "../components/ProviderBadge";

export default function Compare() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns().then((r) => setRuns(r.runs));
  }, []);

  async function doCompare() {
    setError(null);
    setData(null);
    if (!a || !b) {
      setError("Pick two runs.");
      return;
    }
    try {
      const res = await compareRuns(a, b);
      setData(res);
    } catch (error: unknown) {
      setError(apiErrorMessage(error, "Compare failed"));
    }
  }

  function renderSide(side: any) {
    if (!side) return null;
    const run = side.run;
    const results = side.results;
    return (
      <div className="space-y-3">
        <ScoreCard record={run} />
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <ProviderBadge name={run.provider} />
            <span className="text-xs text-muted">{run.timestamp}</span>
          </div>
          {results.map((r: any, i: number) => (
            <div key={i} className="border-t border-border pt-2 mt-2 first:border-0 first:mt-0 first:pt-0">
              <div className="text-xs font-mono text-muted">{r.eval_name}</div>
              <div className="text-xs">
                {r.assertion_type}{" "}
                <span className={r.assertion_passed ? "text-accent" : "text-danger"}>
                  {r.assertion_passed ? "PASS" : "FAIL"} ({r.assertion_score.toFixed(2)})
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold mb-1">Compare Runs</h1>
      <p className="text-muted text-sm mb-6">Side-by-side view of any two past runs.</p>

      <div className="bg-card border border-border rounded-lg p-4 mb-6 flex gap-3">
        <select value={a} onChange={(e) => setA(e.target.value)} className="flex-1 bg-bg border border-border rounded p-2 text-sm">
          <option value="">-- Run A --</option>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>{r.timestamp.slice(0, 16)} | {r.provider} | {(r.composite_score * 100).toFixed(0)}%</option>
          ))}
        </select>
        <select value={b} onChange={(e) => setB(e.target.value)} className="flex-1 bg-bg border border-border rounded p-2 text-sm">
          <option value="">-- Run B --</option>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>{r.timestamp.slice(0, 16)} | {r.provider} | {(r.composite_score * 100).toFixed(0)}%</option>
          ))}
        </select>
        <button onClick={doCompare} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded text-sm">
          Compare
        </button>
      </div>

      {error && <div className="text-sm text-danger mb-4">{error}</div>}

      {data && (
        <div className="grid md:grid-cols-2 gap-4">
          {renderSide(data.run_a)}
          {renderSide(data.run_b)}
        </div>
      )}
    </div>
  );
}
