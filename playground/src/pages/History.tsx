import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { getHistory, listRuns, RunRow } from "../api/client";
import ProviderBadge from "../components/ProviderBadge";

const STATUS_COLOR: Record<string, string> = {
  PASS: "bg-green-600",
  REVIEW: "bg-yellow-500 text-black",
  ALERT: "bg-orange-500",
  PAUSE: "bg-red-600",
};

export default function History() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [chartData, setChartData] = useState<any[]>([]);
  const [providers, setProviders] = useState<string[]>([]);

  useEffect(() => {
    listRuns().then((r) => setRuns(r.runs));
    getHistory().then((h) => {
      const provs = Object.keys(h.history);
      setProviders(provs);
      // Build chart data: each row is {timestamp, [provider]: score, ...}
      const stamps = new Set<string>();
      provs.forEach((p) => h.history[p].forEach((row) => stamps.add(row.timestamp)));
      const ordered = Array.from(stamps).sort();
      const rows = ordered.map((ts) => {
        const out: any = { timestamp: ts.slice(0, 10) };
        provs.forEach((p) => {
          const found = h.history[p].find((row) => row.timestamp === ts);
          if (found) out[p] = found.composite_score;
        });
        return out;
      });
      setChartData(rows);
    });
  }, []);

  const colors: Record<string, string> = { openai: "#22c55e", anthropic: "#f59e0b", mock: "#94a3b8" };

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold mb-1">History</h1>
      <p className="text-muted text-sm mb-6">Past runs and composite-score trend.</p>

      <div className="bg-card border border-border rounded-lg p-5 mb-6">
        <div className="text-xs uppercase tracking-wider text-muted mb-3">Score Trend</div>
        {chartData.length === 0 ? (
          <div className="text-sm text-muted py-8 text-center">No history yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="timestamp" stroke="#94a3b8" />
              <YAxis domain={[0, 1]} stroke="#94a3b8" />
              <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", color: "#e2e8f0" }} />
              <Legend />
              {providers.map((p) => (
                <Line key={p} type="monotone" dataKey={p} stroke={colors[p] ?? "#22c55e"} strokeWidth={2} dot={{ r: 3 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-bg text-xs uppercase text-muted">
            <tr>
              <th className="text-left p-3">Date</th>
              <th className="text-left p-3">Suite</th>
              <th className="text-left p-3">Provider</th>
              <th className="text-right p-3">Score</th>
              <th className="text-left p-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-border">
                <td className="p-3 text-muted font-mono text-xs">{r.timestamp.slice(0, 19)}</td>
                <td className="p-3">{r.suite_name} <span className="text-muted text-xs">v{r.suite_version}</span></td>
                <td className="p-3"><ProviderBadge name={r.provider} /></td>
                <td className="p-3 text-right font-mono">{(r.composite_score * 100).toFixed(1)}%</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs text-white ${STATUS_COLOR[r.threshold_status] ?? "bg-card"}`}>
                    {r.threshold_status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs.length === 0 && (
          <div className="text-sm text-muted py-8 text-center">No runs yet. Try the Run Eval tab.</div>
        )}
      </div>
    </div>
  );
}
