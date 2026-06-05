import { Link, useLocation } from "react-router-dom";
import { Activity, FileCode2, History as HistoryIcon, GitCompareArrows, Download, FlaskConical } from "lucide-react";
import { ReactNode } from "react";

const nav = [
  { to: "/run", label: "Run Eval", icon: Activity },
  { to: "/suite", label: "Load Suite", icon: FileCode2 },
  { to: "/history", label: "History", icon: HistoryIcon },
  { to: "/compare", label: "Compare", icon: GitCompareArrows },
  { to: "/export", label: "Export", icon: Download },
];

export default function Layout({ children }: { children: ReactNode }) {
  const loc = useLocation();
  return (
    <div className="min-h-screen flex bg-bg text-text">
      <aside className="w-60 shrink-0 bg-surface border-r border-border p-4">
        <div className="flex items-center gap-2 mb-8 px-2">
          <FlaskConical className="w-6 h-6 text-accent" />
          <span className="font-semibold tracking-tight">llm-eval</span>
        </div>
        <nav className="space-y-1">
          {nav.map(({ to, label, icon: Icon }) => {
            const active = loc.pathname === to || (to === "/run" && loc.pathname === "/");
            return (
              <Link
                key={to}
                to={to}
                className={
                  "flex items-center gap-3 px-3 py-2 rounded text-sm transition " +
                  (active
                    ? "bg-card text-text"
                    : "text-muted hover:bg-card/60 hover:text-text")
                }
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="absolute bottom-4 text-xs text-muted px-2">
          v1.0.0
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
