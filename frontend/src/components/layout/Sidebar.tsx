import { Fragment } from "react";
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

interface NavGroup {
  heading?: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    heading: "Operations",
    items: [
      { to: "/", label: "Overview", icon: Gauge, end: true },
      { to: "/monitoring", label: "Live Monitoring", icon: Activity },
      { to: "/analytics", label: "AI Analytics", icon: BrainCircuit },
    ],
  },
  {
    heading: "Management",
    items: [
      { to: "/alerts", label: "Alerts", icon: BellRing },
      { to: "/devices", label: "Devices", icon: Cpu },
    ],
  },
  {
    heading: "Platform",
    items: [{ to: "/settings", label: "Settings", icon: Settings2 }],
  },
];

/**
 * Primary navigation, grouped into sections on desktop and collapsing to a
 * horizontal icon bar on small screens. Keyboard navigable; the active route
 * is marked with aria-current and a cyan left rail.
 */
export function Sidebar({ activeAlerts = 0 }: { activeAlerts?: number }) {
  return (
    <nav aria-label="Primary" className="contents md:contents">
      <ul className="flex gap-1 overflow-x-auto px-2 py-2 md:mx-3 md:flex-col md:gap-0.5 md:overflow-visible md:px-0 md:py-3">
        {GROUPS.map((group, groupIndex) => (
          <Fragment key={group.heading ?? groupIndex}>
            {group.heading !== undefined && (
              <li className={`hidden shrink-0 md:block ${groupIndex > 0 ? "md:mt-4" : "md:mt-1"}`}>
                <span
                  className="px-3 text-[10px] font-semibold tracking-[0.16em] text-ink-faint/80 uppercase"
                  aria-hidden="true"
                >
                  {group.heading}
                </span>
              </li>
            )}
            {group.items.map(({ to, label, icon: Icon, end }) => (
              <li key={to} className="shrink-0 md:relative md:w-full">
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors duration-150 ${
                      isActive
                        ? "bg-accent/10 font-medium text-accent"
                        : "text-ink-dim hover:bg-white/4 hover:text-ink"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {/* Active accent rail */}
                      <span
                        aria-hidden="true"
                        className={`absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full transition-colors duration-150 ${
                          isActive ? "bg-accent" : "bg-transparent"
                        }`}
                      />
                      <Icon
                        aria-hidden
                        className={`h-4.5 w-4.5 shrink-0 transition-colors duration-150 ${
                          isActive ? "text-accent" : "text-ink-faint"
                        }`}
                      />
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
          </Fragment>
        ))}
      </ul>
    </nav>
  );
}
