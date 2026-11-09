import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';

import WorkspacePage from './pages/WorkspacePage';
import ProjectsPage from './pages/ProjectsPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import RunProgressPage from './pages/RunProgressPage';
import RunResultsPage from './pages/RunResultsPage';
import GeneratedTestsPage from './pages/GeneratedTestsPage';
import DebuggerPage from './pages/DebuggerPage';
import QualityPage from './pages/QualityPage';
import ReportPage from './pages/ReportPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<WorkspacePage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="runs/:runId/progress" element={<RunProgressPage />} />
        <Route path="runs/:runId/results" element={<RunResultsPage />} />
        <Route path="runs/:runId/tests" element={<GeneratedTestsPage />} />
        <Route path="runs/:runId/debugger" element={<DebuggerPage />} />
        <Route path="runs/:runId/quality" element={<QualityPage />} />
        <Route path="runs/:runId/report" element={<ReportPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
