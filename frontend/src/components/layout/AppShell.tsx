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

/** Wordmark: pulsing telemetry node + product name (rendered once, in the topbar). */
function Brand() {
  return (
    <a
      href="/"
      className="flex items-center gap-2.5 rounded-md py-1 outline-hidden"
      aria-label="Predictive Maintenance AI home"
    >
      <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-accent/25 bg-accent/10">
        <motion.span
          className="h-2 w-2 rounded-full bg-accent"
          animate={{ opacity: [1, 0.4, 1] }}
          transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
        />
        <span
          className="pointer-events-none absolute inset-0 rounded-lg shadow-[0_0_14px_0_rgb(45_212_238/0.25)_inset]"
          aria-hidden="true"
        />
      </span>
      <span className="leading-tight">
        <span className="block text-[13px] font-semibold tracking-wide text-ink">Predictive Maintenance</span>
        <span className="block text-[10px] tracking-[0.22em] text-ink-faint uppercase">Control deck</span>
      </span>
    </a>
  );
}

/**
 * App shell: dedicated sidebar column (navigation + meta footer) on md+,
 * horizontal nav bar on mobile, and a sticky topbar carrying the wordmark and
 * connection badge. The routed page content sits in a centred max-width well;
 * polling, titles and the alert badge stay centralised here.
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
      {/* Sidebar column (desktop): nav + meta footer */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-edge bg-panel/40 md:sticky md:top-0 md:flex md:h-screen">
        <div className="min-h-0 flex-1">
          <Sidebar activeAlerts={activeAlerts} />
        </div>
        <div className="border-t border-edge/70 px-4 py-3">
          <p className="flex items-center gap-1.5 text-[10px] tracking-[0.14em] text-ink-faint uppercase">
            <span className="h-1 w-1 rounded-full bg-ink-faint/60" aria-hidden="true" />
            IoT telemetry · C-MAPSS
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar (sticky): wordmark + connection badge */}
        <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-edge bg-panel/70 px-4 py-2.5 backdrop-blur-md md:px-6">
          <Brand />
          <ConnectionBadge />
        </header>

        {/* Mobile nav row */}
        <div className="border-b border-edge md:hidden">
          <Sidebar activeAlerts={activeAlerts} />
        </div>

        {/* Routed page */}
        <main className="relative min-w-0 flex-1 px-4 py-5 md:px-8 md:py-8">
          <div className="mx-auto w-full max-w-[1440px]">{children}</div>
        </main>
      </div>
    </div>
  );
}
