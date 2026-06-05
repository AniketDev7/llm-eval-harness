import { useState, useEffect } from "react";
import { api } from "../api/client";

interface RunSummary {
  id: string;
  timestamp: string;
  suite_name: string;
  provider: string;
  composite_score: number;
  threshold_status: string;
}

const STATUS_COLORS: Record<string, string> = {
  PASS: "text-green-400",
  REVIEW: "text-yellow-400",
  ALERT: "text-orange-400",
  PAUSE: "text-red-400",
};

export default function Export() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    api.get("/runs").then((r) => {
      setRuns(r.data.runs ?? r.data);
      setLoading(false);
    });
  }, []);

  const download = async (runId: string, format: "json" | "html") => {
    setDownloading(`${runId}-${format}`);
    try {
      const resp = await api.get(`/export/${runId}?format=${format}`, {
        responseType: "blob",
      });
      const ext = format === "html" ? "html" : "json";
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `eval-report-${runId.slice(0, 8)}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed", err);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Export Reports</h1>
        <p className="text-zinc-400 mt-1 text-sm">
          Download JSON or HTML reports for any past eval run.
        </p>
      </div>

      {loading && <p className="text-zinc-400">Loading runs…</p>}

      {!loading && runs.length === 0 && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-8 text-center text-zinc-500">
          No runs found. Run{" "}
          <code className="font-mono text-zinc-300">llm-eval run evals/quickstart.yaml</code>{" "}
          first.
        </div>
      )}

      {!loading && runs.length > 0 && (
        <div className="rounded-lg border border-zinc-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-700 bg-zinc-800/60">
                <th className="px-4 py-3 text-left text-zinc-400 font-medium">Run ID</th>
                <th className="px-4 py-3 text-left text-zinc-400 font-medium">Suite</th>
                <th className="px-4 py-3 text-left text-zinc-400 font-medium">Provider</th>
                <th className="px-4 py-3 text-left text-zinc-400 font-medium">Score</th>
                <th className="px-4 py-3 text-left text-zinc-400 font-medium">Status</th>
                <th className="px-4 py-3 text-left text-zinc-400 font-medium">Timestamp</th>
                <th className="px-4 py-3 text-right text-zinc-400 font-medium">Download</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className="border-b border-zinc-800 hover:bg-zinc-800/40 transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-zinc-300 text-xs">
                    {run.id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-3 text-zinc-200">{run.suite_name}</td>
                  <td className="px-4 py-3 text-zinc-400 capitalize">{run.provider}</td>
                  <td className="px-4 py-3 text-zinc-200 font-mono">
                    {(run.composite_score * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-semibold text-xs ${STATUS_COLORS[run.threshold_status] ?? "text-zinc-400"}`}>
                      {run.threshold_status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-500 text-xs">
                    {new Date(run.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button
                      onClick={() => download(run.id, "json")}
                      disabled={downloading === `${run.id}-json`}
                      className="px-2.5 py-1 rounded text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-200 disabled:opacity-50 transition-colors"
                    >
                      {downloading === `${run.id}-json` ? "…" : "JSON"}
                    </button>
                    <button
                      onClick={() => download(run.id, "html")}
                      disabled={downloading === `${run.id}-html`}
                      className="px-2.5 py-1 rounded text-xs bg-indigo-700 hover:bg-indigo-600 text-white disabled:opacity-50 transition-colors"
                    >
                      {downloading === `${run.id}-html` ? "…" : "HTML"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
