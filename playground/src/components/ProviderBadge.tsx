const COLORS: Record<string, string> = {
  openai: "bg-emerald-700 text-emerald-100",
  anthropic: "bg-amber-700 text-amber-100",
  mock: "bg-slate-600 text-slate-100",
};

function parseSlot(name: string): { provider: string; model: string | null } {
  const m = name.match(/^([^\s(]+)\s*\(([^)]+)\)\s*$/);
  if (m) return { provider: m[1], model: m[2] };
  return { provider: name, model: null };
}

export default function ProviderBadge({ name }: { name: string }) {
  const { provider, model } = parseSlot(name);
  const cls = COLORS[provider.toLowerCase()] ?? "bg-slate-600 text-slate-100";
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded ${cls}`}>
      <span>{provider}</span>
      {model && <span className="opacity-70 font-mono">{model}</span>}
    </span>
  );
}
