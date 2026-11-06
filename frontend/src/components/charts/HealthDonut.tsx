import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { MachineSummary } from "@/api/types";
import { healthLabel } from "@/lib/format";
import { SERIES } from "@/lib/health";

interface Slice {
  name: string;
  value: number;
  color: string;
}

/**
 * Machine-health distribution donut: healthy / anomalous / elevated /
 * critical / no-data share of the fleet.
 */
export function HealthDonut({ machines, height = 200 }: { machines: MachineSummary[]; height?: number }) {
  const order = ["healthy", "anomalous", "elevated_risk", "critical_risk", "unknown"] as const;
  const colors: Record<(typeof order)[number], string> = {
    healthy: SERIES.healthy,
    anomalous: SERIES.warning,
    elevated_risk: SERIES.warning,
    critical_risk: SERIES.critical,
    unknown: SERIES.dim,
  };
  const slices: Slice[] = order
    .map((health) => ({
      name: healthLabel(health),
      value: machines.filter((m) => m.health === health).length,
      color: colors[health],
    }))
    .filter((s) => s.value > 0);

  if (machines.length === 0) {
    return <p className="grid h-40 place-items-center text-xs text-ink-faint">No machines ingested yet</p>;
  }

  return (
    <div className="flex items-center gap-4" style={{ minHeight: height }} role="img" aria-label="Machine health distribution">
      <div style={{ width: 150, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              innerRadius="62%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="#0c1520"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {slices.map((slice) => (
                <Cell key={slice.name} fill={slice.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "#101c29",
                border: "1px solid #294059",
                borderRadius: 6,
                fontSize: 12,
                padding: "6px 10px",
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1.5 text-xs" aria-label="Health legend">
        {slices.map((slice) => (
          <li key={slice.name} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: slice.color }} aria-hidden="true" />
            <span className="text-ink-dim">{slice.name}</span>
            <span className="tnum ml-auto pl-4 font-semibold text-ink">{slice.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

