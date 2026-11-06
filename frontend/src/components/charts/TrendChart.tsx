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

/**
 * Shared responsive trend chart (Recharts). Series color and axis formatter
 * provided by the caller; grid + tooltip chrome is consistent app-wide.
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
        <Chart data={points} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 6" vertical={false} />
          <XAxis
            dataKey="x"
            tickLine={false}
            axisLine={{ stroke: "#294059" }}
            tickMargin={6}
            minTickGap={28}
            {...(categoryX ? { type: "category" as const } : { type: "number" as const, domain: ["dataMin", "dataMax"] as [string, string] })}
          />
          <YAxis
            width={52}
            tickLine={false}
            axisLine={false}
            domain={domain}
            tickFormatter={(v: number) => (yFormatter ? yFormatter(v) : String(v))}
          />
          <Tooltip
            cursor={{ stroke: color, strokeOpacity: 0.3 }}
            contentStyle={{
              background: "#101c29",
              border: "1px solid #294059",
              borderRadius: 6,
              fontSize: 12,
              padding: "6px 10px",
            }}
            labelStyle={{ color: "#9daeba" }}
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
            strokeWidth={1.8}
            fill={area ? `url(#${gradientId})` : undefined}
            fillOpacity={1}
            dot={false}
            activeDot={{ r: 3, fill: color, stroke: "#0c1520" }}
            isAnimationActive={false}
          />
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}
