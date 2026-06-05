import { AssertionResult as TR } from "../api/client";
import { CheckCircle2, XCircle } from "lucide-react";

export default function AssertionResultRow({ a }: { a: TR }) {
  return (
    <div className="flex items-start gap-2 text-sm py-1">
      {a.passed ? (
        <CheckCircle2 className="w-4 h-4 text-accent mt-0.5 shrink-0" />
      ) : (
        <XCircle className="w-4 h-4 text-danger mt-0.5 shrink-0" />
      )}
      <div className="flex-1">
        <div className="font-mono text-xs">
          {a.type} <span className="text-muted">({a.score.toFixed(2)})</span>
        </div>
        <div className="text-xs text-muted">{a.detail}</div>
      </div>
    </div>
  );
}
