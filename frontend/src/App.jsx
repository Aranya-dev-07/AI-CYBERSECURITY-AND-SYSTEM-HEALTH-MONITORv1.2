import { Routes, Route } from "react-router-dom";
import { Toaster } from "react-hot-toast";

import { SystemStatusProvider } from "./context/SystemStatusContext.jsx";

import AppShell from "./layout/AppShell.jsx";

import Dashboard from "./pages/Dashboard.jsx";
import Monitoring from "./pages/Monitoring.jsx";
import AIWorkspace from "./pages/AIWorkspace.jsx";
import Cybersecurity from "./pages/Cybersecurity.jsx";
import Reports from "./pages/Reports.jsx";
import Settings from "./pages/Settings.jsx";

/**
 * NotFound — minimal inline 404 fallback, rendered inside AppShell so
 * the sidebar/topbar remain visible even on an unmatched route.
 */
function NotFound() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 py-24 text-center">
      <span className="text-6xl font-bold text-[var(--color-accent,#7c3aed)]">404</span>
      <p className="text-lg font-medium text-[var(--color-text-secondary,#94a3b8)]">
        Page not found.
      </p>
    </div>
  );
}

/**
 * App — central frontend orchestrator. Wraps the application in shared
 * context providers and defines all routes. All page content renders
 * inside AppShell (Sidebar + Topbar + <Outlet />). No business logic
 * lives here — routing and provider composition only.
 */
function App() {
  return (
    <SystemStatusProvider>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: "var(--color-surface, #1e293b)",
            color: "var(--color-text-primary, #f1f5f9)",
            border: "1px solid var(--color-border, #334155)",
          },
        }}
      />

      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="monitoring" element={<Monitoring />} />
          <Route path="ai-workspace" element={<AIWorkspace />} />
          <Route path="cybersecurity" element={<Cybersecurity />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </SystemStatusProvider>
  );
}

export default App;