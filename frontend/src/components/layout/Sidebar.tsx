import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BellRing,
  BrainCircuit,
  Cpu,
  Gauge,
  Settings2,
} from "lucide-react";
import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/monitoring", label: "Live Monitoring", icon: Activity },
  { to: "/analytics", label: "AI Analytics", icon: BrainCircuit },
  { to: "/alerts", label: "Alerts", icon: BellRing },
  { to: "/devices", label: "Devices", icon: Cpu },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

/**
 * Primary navigation. Collapses to a horizontal icon bar on small screens
 * (keyboard navigable; active route marked with aria-current).
 */
export function Sidebar({ activeAlerts = 0 }: { activeAlerts?: number }) {
  return (
    <nav aria-label="Primary" className="contents md:contents">
      <ul className="flex gap-1 overflow-x-auto px-2 py-2 md:mx-3 md:flex-col md:gap-0.5 md:px-0 md:py-3">
        {ITEMS.map(({ to, label, icon: Icon, end }) => (
          <li key={to} className="shrink-0 md:w-full">
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded px-3 py-2 text-sm transition focus-visible:outline-offset-0 ${
                  isActive
                    ? "bg-accent/10 font-medium text-accent"
                    : "text-ink-dim hover:bg-white/5 hover:text-ink"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon aria-hidden className={`h-4.5 w-4.5 shrink-0 ${isActive ? "text-accent" : ""}`} />
                  <span className="whitespace-nowrap">{label}</span>
                  {label === "Alerts" && activeAlerts > 0 && (
                    <span
                      className="tnum ml-auto rounded-full bg-critical/15 px-1.5 py-0.5 text-[10px] font-semibold text-critical"
                      aria-label={`${activeAlerts} active alerts`}
                    >
                      {activeAlerts}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
