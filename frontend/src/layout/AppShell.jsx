import { useState, useCallback } from "react";
import { Outlet } from "react-router-dom";

import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";

const SIDEBAR_WIDTH_EXPANDED = "16rem";
const SIDEBAR_WIDTH_COLLAPSED = "4.5rem";

/**
 * AppShell — the primary workspace layout for Lavender Trinetra.
 *
 * Structure:
 *   - Fixed-position Sidebar on the left (collapsible width).
 *   - Sticky Topbar spanning the remaining width.
 *   - A scrollable main content region that renders the active
 *     routed page via <Outlet />.
 *
 * Purely structural — no data fetching or business logic lives here.
 */
function AppShell() {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const toggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const sidebarWidth = isSidebarCollapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH_EXPANDED;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--color-bg,#0f1115)] text-[var(--color-text-primary,#f1f5f9)]">
      {/* Fixed sidebar */}
      <aside
        className="fixed inset-y-0 left-0 z-30 h-screen flex-shrink-0 border-r border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] transition-[width] duration-200 ease-in-out"
        style={{ width: sidebarWidth }}
      >
        <Sidebar isCollapsed={isSidebarCollapsed} onToggleCollapse={toggleSidebar} />
      </aside>

      {/* Right-hand column: sticky topbar + scrollable content */}
      <div
        className="flex min-w-0 flex-1 flex-col transition-[margin] duration-200 ease-in-out"
        style={{ marginLeft: sidebarWidth }}
      >
        <header className="sticky top-0 z-20 flex-shrink-0 border-b border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--color-surface,#171923)]/80">
          <Topbar isSidebarCollapsed={isSidebarCollapsed} onToggleSidebar={toggleSidebar} />
        </header>

        <main className="flex-1 overflow-y-auto overflow-x-hidden bg-[var(--color-bg,#0f1115)] px-6 py-6 md:px-8 md:py-8">
          <div className="mx-auto w-full max-w-[1600px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

export default AppShell;