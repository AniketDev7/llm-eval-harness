import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";

const RunEval = lazy(() => import("./pages/RunEval"));
const LoadSuite = lazy(() => import("./pages/LoadSuite"));
const History = lazy(() => import("./pages/History"));
const Compare = lazy(() => import("./pages/Compare"));
const Export = lazy(() => import("./pages/Export"));

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<div className="text-sm text-muted">Loading page…</div>}>
        <Routes>
          <Route path="/" element={<Navigate to="/run" replace />} />
          <Route path="/run" element={<RunEval />} />
          <Route path="/suite" element={<LoadSuite />} />
          <Route path="/history" element={<History />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/export" element={<Export />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
