import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute, PublicOnlyRoute } from "./auth/RouteGuards";
import { AppLayout } from "./components/AppLayout";
import { ToastProvider } from "./components/ui/Toast";
import BenchmarkLab from "./pages/BenchmarkLab";
import ComingSoon from "./pages/ComingSoon";
import Dashboard from "./pages/Dashboard";
import DatasetDetail from "./pages/DatasetDetail";
import Datasets from "./pages/Datasets";
import ExperimentDetail from "./pages/ExperimentDetail";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import ProjectDetail from "./pages/ProjectDetail";
import ProjectExperiments from "./pages/ProjectExperiments";
import Projects from "./pages/Projects";
import Register from "./pages/Register";
import WhatIf from "./pages/WhatIf";
import Models from "./pages/Models";
import Copilot from "./pages/Copilot";
import Deployments from "./pages/Deployments";
import Monitoring from "./pages/Monitoring";
import TrustReceiptPage from "./pages/TrustReceipt";
import WhatIfLab from "./pages/WhatIfLab";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route path="/app" element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/:projectId" element={<ProjectDetail />} />
          <Route path="projects/:projectId/experiments" element={<ProjectExperiments />} />
          <Route path="projects/:projectId/experiments/:experimentId" element={<ExperimentDetail />} />
          <Route path="projects/:projectId/experiments/:experimentId/what-if" element={<WhatIf />} />
          <Route path="projects/:projectId/datasets" element={<Datasets />} />
          <Route path="projects/:projectId/datasets/:datasetId" element={<DatasetDetail />} />
          <Route path="benchmarks" element={<BenchmarkLab />} />
          <Route path="projects/:projectId/models" element={<Models />} />
          <Route path="projects/:projectId/copilot" element={<Copilot />} />
          <Route path="projects/:projectId/deployments" element={<Deployments />} />
          <Route path="projects/:projectId/monitoring" element={<Monitoring />} />
          <Route path="projects/:projectId/trust" element={<TrustReceiptPage />} />
          <Route path="projects/:projectId/what-if" element={<WhatIfLab />} />
          <Route path="coming-soon/:slug" element={<ComingSoon />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
