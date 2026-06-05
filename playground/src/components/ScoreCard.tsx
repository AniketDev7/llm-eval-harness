import { RunRecord } from "../api/client";

const STATUS_CLASS: Record<string, string> = {
  PASS: "bg-green-600",
  REVIEW: "bg-yellow-500 text-black",
  ALERT: "bg-orange-500",
  PAUSE: "bg-red-600",
};

export default function ScoreCard({ record }: { record: RunRecord | { composite_score: number; coverage_score: number; accuracy_score: number; format_score: number; hallucination_score: number; threshold_status: string; provider: string } }) {
  const cls = STATUS_CLASS[record.threshold_status] ?? "bg-card";
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className="text-xs text-muted uppercase tracking-wider">{record.provider}</div>
          <div className="text-3xl font-semibold">
            {(record.composite_score * 100).toFixed(1)}%
          </div>
        </div>
        <span className={`px-3 py-1 rounded text-xs font-semibold text-white ${cls}`}>
          {record.threshold_status}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 text-xs">
        <Sub label="Coverage" pct={record.coverage_score} weight="40%" />
        <Sub label="Accuracy" pct={record.accuracy_score} weight="30%" />
        <Sub label="Format" pct={record.format_score} weight="20%" />
        <Sub label="Halluc." pct={record.hallucination_score} weight="10%" />
      </div>
    </div>
  );
}

function Sub({ label, pct, weight }: { label: string; pct: number; weight: string }) {
  return (
    <div className="text-center">
      <div className="text-muted">{label} <span className="opacity-60">{weight}</span></div>
      <div className="font-mono">{(pct * 100).toFixed(0)}%</div>
    </div>
  );
}
