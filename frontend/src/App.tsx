import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { AlertsPage } from "@/pages/AlertsPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { DeviceDetailPage } from "@/pages/DeviceDetailPage";
import { DevicesPage } from "@/pages/DevicesPage";
import { LiveMonitoringPage } from "@/pages/LiveMonitoringPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { SettingsPage } from "@/pages/SettingsPage";

/**
 * Route table. Data pages are wrapped in AppShell which owns the connection
 * badge, sidebar and alert badge state.
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell><OverviewPage /></AppShell>} />
      <Route path="/monitoring" element={<AppShell><LiveMonitoringPage /></AppShell>} />
      <Route path="/analytics" element={<AppShell><AnalyticsPage /></AppShell>} />
      <Route path="/alerts" element={<AppShell><AlertsPage /></AppShell>} />
      <Route path="/devices" element={<AppShell><DevicesPage /></AppShell>} />
      <Route path="/devices/:machineId" element={<AppShell><DeviceDetailPage /></AppShell>} />
      <Route path="/settings" element={<AppShell><SettingsPage /></AppShell>} />
      <Route path="*" element={<AppShell><OverviewPage /></AppShell>} />
    </Routes>
  );
}
