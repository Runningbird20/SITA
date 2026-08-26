import { Route, Routes } from "react-router-dom";
import { AuthGate } from "./components/AuthGate";
import { Layout } from "./components/Layout";
import { AlertsPage } from "./pages/AlertsPage";
import { DetectionsPage } from "./pages/DetectionsPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { IocsPage } from "./pages/IocsPage";
import { MitrePage } from "./pages/MitrePage";
import { OverviewPage } from "./pages/OverviewPage";
import { StatusPage } from "./pages/StatusPage";

function App() {
  return (
    <Routes>
      {/* Not gated by AuthGate — /status stays reachable for diagnostics
       * the same way /healthz does, regardless of API auth. See DEF.md §
       * Phase 14. */}
      <Route path="/status" element={<StatusPage />} />
      <Route
        element={
          <AuthGate>
            <Layout />
          </AuthGate>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="iocs" element={<IocsPage />} />
        <Route path="detections" element={<DetectionsPage />} />
        <Route path="mitre" element={<MitrePage />} />
      </Route>
    </Routes>
  );
}

export default App;
