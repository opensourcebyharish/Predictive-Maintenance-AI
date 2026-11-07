import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { SERIES } from "@/lib/health";

export interface TrendPoint {
  x: number | string;
  y: number | null | undefined;
}

interface TrendChartProps {
  data: TrendPoint[];
  color: string;
  ariaLabel: string;
  height?: number;
  /** Use an area fill instead of a plain line. */
  area?: boolean;
  domain?: [number | "auto", number | "auto"];
  /** Category ticks ("Cycle 12") vs numeric axis. */
  categoryX?: boolean;
  yFormatter?: (value: number) => string;
  xFormatter?: (value: number | string) => string;
  tooltipFormatter?: (value: number) => ReactNode;
}

/** Shared tooltip surfaces so every chart reads as one system. */
const TOOLTIP_STYLE = {
  background: SERIES.panel2,
  border: `1px solid ${SERIES.edgeBright}`,
  borderRadius: 8,
  boxShadow: "0 16px 40px -16px rgb(1 4 9 / 0.95)",
  fontSize: 12,
  padding: "8px 12px",
} as const;

/**
 * Shared responsive trend chart (Recharts). Series color and axis formatter
 * provided by the caller; grid, cursor and tooltip chrome stay consistent
 * app-wide. Animations stay off: data is polled, so frames must not jump.
 */
export function TrendChart({
  data,
  color,
  ariaLabel,
  height = 220,
  area = true,
  domain = ["auto", "auto"],
  categoryX = false,
  yFormatter,
  xFormatter,
  tooltipFormatter,
}: TrendChartProps) {
  const points = data
    .filter((p) => p.y !== null && p.y !== undefined && Number.isFinite(p.y))
    .map((p) => ({ x: p.x, y: p.y as number }));

  if (points.length === 0) {
    return <p className="grid h-40 place-items-center text-xs text-ink-faint">No data points yet</p>;
  }

  const gradientId = `trend-${color.replace("#", "")}`;
  const Chart = area ? AreaChart : LineChart;
  const Series = area ? Area : Line;

  return (
    <div style={{ height }} role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={points} margin={{ top: 8, right: 10, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="80%" stopColor={color} stopOpacity={0.02} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 6" vertical={false} />
          <XAxis
            dataKey="x"
            tickLine={false}
            axisLine={{ stroke: SERIES.edgeBright }}
            tickMargin={8}
            minTickGap={28}
            {...(categoryX ? { type: "category" as const } : { type: "number" as const, domain: ["dataMin", "dataMax"] as [string, string] })}
          />
          <YAxis
            width={56}
            tickLine={false}
            axisLine={false}
            domain={domain}
            tickFormatter={(v: number) => (yFormatter ? yFormatter(v) : String(v))}
          />
          <Tooltip
            cursor={{ stroke: SERIES.edgeBright, strokeOpacity: 0.9, strokeWidth: 1 }}
            contentStyle={TOOLTIP_STYLE}
            itemStyle={{ color: "#e9eff6", padding: 0, lineHeight: "16px" }}
            labelStyle={{ color: "#6d7f8e", fontWeight: 500, marginBottom: 2 }}
            formatter={(value) => {
              if (typeof value !== "number") return value;
              if (tooltipFormatter) return tooltipFormatter(value);
              return String(yFormatter ? yFormatter(value) : value);
            }}
            labelFormatter={(label) => (xFormatter ? xFormatter(label as string) : `x: ${label}`)}
          />
          <Series
            dataKey="y"
            type="monotone"
            stroke={color}
            strokeWidth={2}
            fill={area ? `url(#${gradientId})` : undefined}
            fillOpacity={1}
            dot={false}
            activeDot={{ r: 3.5, fill: color, stroke: SERIES.panel, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}
