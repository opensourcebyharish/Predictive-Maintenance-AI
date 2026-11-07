/**
 * Shared formatting + health-presentation utilities (Phase 5.3 Step 3).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  formatAgo,
  formatCount,
  formatDateTime,
  formatNumber,
  formatPercent,
  healthLabel,
  shortId,
} from "@/lib/format";
import {
  ALERT_STATUS_STYLES,
  ALERT_TYPE_LABELS,
  HEALTH_STYLES,
  SERIES,
  SEVERITY_STYLES,
  healthScore,
  healthStyle,
  legendDot,
} from "@/lib/health";

describe("formatDateTime", () => {
  it("returns an em dash for missing or invalid dates", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("formats an ISO timestamp", () => {
    expect(formatDateTime("2026-01-02T03:04:05.000Z")).toMatch(/2026/);
    expect(formatDateTime("2026-01-02T03:04:05.000Z")).toMatch(/Jan/);
  });
});

describe("formatAgo", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-06T12:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it.each([
    ["2026-11-06T11:59:58.000Z", "just now"],
    ["2026-11-06T11:59:20.000Z", "40s ago"],
    ["2026-11-06T11:58:00.000Z", "2m ago"],
    ["2026-11-06T09:00:00.000Z", "3h ago"],
    ["2026-11-04T12:00:00.000Z", "2d ago"],
  ])("renders %s as %s", (iso, expected) => {
    expect(formatAgo(iso)).toBe(expected);
  });

  it("returns an em dash for missing or invalid dates", () => {
    expect(formatAgo(null)).toBe("—");
    expect(formatAgo("invalid")).toBe("—");
  });
});

describe("formatNumber and formatPercent", () => {
  it.each([
    [null, "—"],
    [undefined, "—"],
    [Number.NaN, "—"],
    [Number.POSITIVE_INFINITY, "—"],
    [0.08491, "0.0849"],
    [1.2345, "1.23"],
    [12.34, "12.3"],
    [999.94, "999.9"],
  ])("formatNumber(%s) is %s", (value, expected) => {
    expect(formatNumber(value)).toBe(expected);
  });

  it("keeps the requested precision for small values", () => {
    expect(formatNumber(0.123456, 2)).toBe("0.12");
    expect(formatNumber(0.123456, 6)).toBe("0.123456");
  });

  it("formats thousands with locale grouping", () => {
    expect(formatNumber(1234.56)).toMatch(/1[,\u00A0]234\.6/);
    expect(formatCount(1000)).toMatch(/1[,\u00A0]000/);
  });

  it.each([
    [null, "—"],
    [Number.NaN, "—"],
    [0, "0.000%"],
    [0.123456, "12.346%"],
    [1, "100.000%"],
  ])("formatPercent(%s) is %s", (value, expected) => {
    expect(formatPercent(value)).toBe(expected);
  });

  it("honors custom percentage precision", () => {
    expect(formatPercent(0.123456, 1)).toBe("12.3%");
  });
});

describe("formatCount", () => {
  it("formats plain integers", () => {
    expect(formatCount(0)).toBe("0");
    expect(formatCount(42)).toBe("42");
  });

  it("returns an em dash for missing or non-finite counts", () => {
    expect(formatCount(null)).toBe("—");
    expect(formatCount(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("health labels and ids", () => {
  it("turns snake-case health values into spaces", () => {
    expect(healthLabel("critical_risk")).toBe("critical risk");
    expect(healthLabel("healthy")).toBe("healthy");
  });

  it("keeps short ids and truncates long ids", () => {
    expect(shortId("SIM-001")).toBe("SIM-001");
    expect(shortId("MACHINE-123456789012")).toHaveLength(13);
    expect(shortId("MACHINE-123456789012")).toMatch(/…$/);
  });
});

describe("health presentation rules", () => {
  it("exposes every configured health style", () => {
    expect(healthStyle("healthy")).toMatchObject({ tone: "healthy", label: "Healthy" });
    expect(healthStyle("anomalous")).toMatchObject({ tone: "warning", label: "Anomalous" });
    expect(healthStyle("elevated_risk")).toMatchObject({ tone: "warning", label: "Elevated risk" });
    expect(healthStyle("critical_risk")).toMatchObject({ tone: "critical", label: "Critical" });
    expect(healthStyle("unknown")).toMatchObject({ tone: "neutral", label: "No data" });
  });

  it("falls back to the unknown style for unrecognized health values", () => {
    expect(healthStyle("not-a-real-health")).toBe(HEALTH_STYLES.unknown);
  });

  it("maps health to legend dots from the same style", () => {
    expect(legendDot("healthy")).toBe(HEALTH_STYLES.healthy.dot);
    expect(legendDot("critical_risk")).toBe(HEALTH_STYLES.critical_risk.dot);
    expect(legendDot("unexpected")).toBe(HEALTH_STYLES.unknown.dot);
  });

  it.each([
    ["healthy", 1],
    ["anomalous", 0.6],
    ["elevated_risk", 0.4],
    ["critical_risk", 0.1],
    ["unknown", 0],
    ["not-a-real-health", 0],
  ])("healthScore(%s) is %s", (health, expected) => {
    expect(healthScore(health)).toBe(expected);
  });

  it("defines alert severity, status and type labels", () => {
    expect(SEVERITY_STYLES.low.label).toBe("Low");
    expect(SEVERITY_STYLES.medium.label).toBe("Medium");
    expect(SEVERITY_STYLES.high.label).toBe("High");
    expect(SEVERITY_STYLES.critical.label).toBe("Critical");

    expect(ALERT_STATUS_STYLES.active.label).toBe("Active");
    expect(ALERT_STATUS_STYLES.acknowledged.label).toBe("Acknowledged");
    expect(ALERT_STATUS_STYLES.resolved.label).toBe("Resolved");

    expect(ALERT_TYPE_LABELS.anomaly_detected).toBe("Anomaly detected");
    expect(ALERT_TYPE_LABELS.elevated_failure_risk).toBe("Elevated failure risk");
    expect(ALERT_TYPE_LABELS.critical_failure_risk).toBe("Critical failure risk");
    expect(ALERT_TYPE_LABELS.machine_recovered).toBe("Machine recovered");
  });

  it("keeps the shared chart series as six-digit hex colors", () => {
    for (const color of Object.values(SERIES)) {
      expect(color).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});
