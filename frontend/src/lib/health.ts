/**
 * Health-status presentation rules: color tokens, labels, icon mapping.
 * Single source of truth so every page renders risk consistently.
 */

import type { AlertSeverity, AlertStatus, AlertType, MachineHealth } from "@/api/types";

export type HealthTone = "healthy" | "warning" | "critical" | "neutral";

interface HealthStyle {
  tone: HealthTone;
  label: string;
  text: string;
  dot: string;
  chip: string;
  bar: string;
  /** Soft rail color for row-level severity signalling. */
  rail: string;
}

/** Tailwind classes for each health state (dark industrial palette). */
export const HEALTH_STYLES: Record<MachineHealth, HealthStyle> = {
  healthy: {
    tone: "healthy",
    label: "Healthy",
    text: "text-healthy",
    dot: "bg-healthy",
    chip: "bg-healthy/10 text-healthy border-healthy/30",
    bar: "bg-healthy",
    rail: "border-l-healthy",
  },
  anomalous: {
    tone: "warning",
    label: "Anomalous",
    text: "text-warning",
    dot: "bg-warning",
    chip: "bg-warning/10 text-warning border-warning/30",
    bar: "bg-warning",
    rail: "border-l-warning",
  },
  elevated_risk: {
    tone: "warning",
    label: "Elevated risk",
    text: "text-warning",
    dot: "bg-warning",
    chip: "bg-warning/10 text-warning border-warning/30",
    bar: "bg-warning",
    rail: "border-l-warning",
  },
  critical_risk: {
    tone: "critical",
    label: "Critical",
    text: "text-critical",
    dot: "bg-critical",
    chip: "bg-critical/10 text-critical border-critical/30",
    bar: "bg-critical",
    rail: "border-l-critical",
  },
  unknown: {
    tone: "neutral",
    label: "No data",
    text: "text-ink-faint",
    dot: "bg-ink-faint",
    chip: "bg-white/5 text-ink-dim border-white/10",
    bar: "bg-ink-faint",
    rail: "border-l-edge-bright",
  },
};

export function healthStyle(health: string): HealthStyle {
  return HEALTH_STYLES[health as MachineHealth] ?? HEALTH_STYLES.unknown;
}

/** Dot color for table legends (kept with the palette, not the chart). */
export function legendDot(health: string): string {
  return healthStyle(health).dot;
}

/** Health as a 0-1 capacity score for gauges and distributions. */
export function healthScore(health: string): number {
  switch (health) {
    case "healthy":
      return 1;
    case "anomalous":
      return 0.6;
    case "elevated_risk":
      return 0.4;
    case "critical_risk":
      return 0.1;
    default:
      return 0;
  }
}

export const SEVERITY_STYLES: Record<AlertSeverity, { chip: string; label: string; rail: string }> = {
  low: { chip: "bg-white/5 text-ink-dim border-white/10", label: "Low", rail: "bg-edge-bright" },
  medium: { chip: "bg-info/10 text-info border-info/30", label: "Medium", rail: "bg-info" },
  high: { chip: "bg-warning/10 text-warning border-warning/30", label: "High", rail: "bg-warning" },
  critical: { chip: "bg-critical/10 text-critical border-critical/30", label: "Critical", rail: "bg-critical" },
};

export const ALERT_STATUS_STYLES: Record<AlertStatus, { chip: string; label: string }> = {
  active: { chip: "bg-warning/10 text-warning border-warning/30", label: "Active" },
  acknowledged: { chip: "bg-info/10 text-info border-info/30", label: "Acknowledged" },
  resolved: { chip: "bg-healthy/10 text-healthy border-healthy/30", label: "Resolved" },
};

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  anomaly_detected: "Anomaly detected",
  elevated_failure_risk: "Elevated failure risk",
  critical_failure_risk: "Critical failure risk",
  machine_recovered: "Machine recovered",
};

/** Series colors used across Recharts visualisations (mirror --color-* tokens). */
export const SERIES = {
  healthy: "#3ddc97",
  warning: "#fbbf24",
  critical: "#fb5560",
  info: "#6ea8fe",
  accent: "#2dd4ee",
  dim: "#6d7f8e",
  violet: "#a78bfa",
  edge: "#16232f",
  edgeBright: "#25384d",
  panel: "#0a121b",
  panel2: "#0e1826",
} as const;
