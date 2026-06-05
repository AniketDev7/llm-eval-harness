import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import RunEval from "./pages/RunEval";
import LoadSuite from "./pages/LoadSuite";
import History from "./pages/History";
import Compare from "./pages/Compare";
import Export from "./pages/Export";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/run" replace />} />
        <Route path="/run" element={<RunEval />} />
        <Route path="/suite" element={<LoadSuite />} />
        <Route path="/history" element={<History />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/export" element={<Export />} />
      </Routes>
    </Layout>
  );
}
