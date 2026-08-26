import { Route, Routes } from "react-router-dom";
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
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="iocs" element={<IocsPage />} />
        <Route path="detections" element={<DetectionsPage />} />
        <Route path="mitre" element={<MitrePage />} />
      </Route>
      <Route path="/status" element={<StatusPage />} />
    </Routes>
  );
}

export default App;
