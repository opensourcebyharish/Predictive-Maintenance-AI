import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { useEffect } from "react";
import type { Location } from "react-router-dom";
import { useLocation } from "react-router-dom";

import { fetchAlertSummary } from "@/api/endpoints";
import { usePollIntervalMs } from "@/api/useSettings";
import { ConnectionBadge } from "@/components/layout/ConnectionBadge";
import { Sidebar } from "@/components/layout/Sidebar";
import { useResource } from "@/api/hooks";

/** Route → document.title, one place for the whole app. */
const TITLES: Record<string, string> = {
  "/": "Overview",
  "/monitoring": "Live Monitoring",
  "/analytics": "AI Analytics",
  "/alerts": "Alerts & Incidents",
  "/devices": "Device Management",
  "/settings": "Settings",
};

function titleFor(location: Location): string {
  const base = TITLES[location.pathname] ?? location.pathname.split("/")[1]?.replace(/^\w/, (c) => c.toUpperCase()) ?? "";
  return base === "" ? "Predictive Maintenance AI" : `${base} · Predictive Maintenance AI`;
}

/**
 * App shell: fixed sidebar (desktop) / horizontal nav (mobile), topbar with
 * connection badge, and the routed page with a subtle enter animation.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();

  useEffect(() => {
    document.title = titleFor(location);
  }, [location]);

  // Global nav awareness: cheap summary poll shared with the sidebar badge.
  const pollMs = usePollIntervalMs();
  const pollNav = pollMs > 0 ? Math.max(pollMs, 15000) : 0;
  const summary = useResource(() => fetchAlertSummary(), undefined, { pollMs: pollNav });
  const activeAlerts = summary.data === null ? 0 : (summary.data.by_status["active"] ?? 0);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/* Brand block */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5 md:w-56 md:shrink-0 md:flex-col md:items-start md:border-r md:border-b-0 md:px-4">
        <a href="/" className="flex items-center gap-2.5 outline-hidden" aria-label="Predictive Maintenance AI home">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-accent/10 ring-1 ring-accent/30">
            <motion.span
              className="h-2 w-2 rounded-full bg-accent"
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
            />
          </span>
          <span className="leading-tight">
            <span className="block text-[13px] font-semibold tracking-wide text-ink">Predictive Maintenance</span>
            <span className="block text-[10px] tracking-[0.18em] text-ink-faint uppercase">Control deck</span>
          </span>
        </a>
      </div>

      {/* Sidebar navigation (md+) */}
      <aside className="hidden w-48 shrink-0 flex-col border-r border-edge md:flex">
        <Sidebar activeAlerts={activeAlerts} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="flex items-center justify-end gap-3 border-b border-edge bg-panel/60 px-4 py-2 backdrop-blur-sm">
          <ConnectionBadge />
        </header>

        {/* Mobile nav row */}
        <div className="border-b border-edge md:hidden">
          <Sidebar activeAlerts={activeAlerts} />
        </div>

        {/* Routed page */}
        <main className="min-w-0 flex-1 px-4 py-5 md:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}
