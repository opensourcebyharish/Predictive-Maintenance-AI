/**
 * React Testing Library smoke tests for the shared UI primitives:
 * correct semantics, keyboard focusability, provenance badges, routing utils.
 */

import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { screen } from "@testing-library/react";

import { Panel } from "@/components/ui/Panel";
import { StatTile } from "@/components/ui/StatTile";
import { Badge, SimBadge } from "@/components/ui/Badge";
import { StatusDot } from "@/components/ui/StatusDot";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Sidebar } from "@/components/layout/Sidebar";
import { renderWithRouter } from "@/test/utils";

describe("panel", () => {
  it("renders title, subtitle, actions and content", () => {
    renderWithRouter(
      <Panel title="Fleet" subtitle="live" actions={<span>refresh</span>}>
        <p data-testid="panel-body">engine cycles</p>
      </Panel>,
    );
    expect(screen.getByRole("heading", { name: "Fleet" })).toBeInTheDocument();
    expect(screen.getByText("live")).toBeInTheDocument();
    expect(screen.getByText("refresh")).toBeInTheDocument();
    expect(screen.getByTestId("panel-body")).toBeInTheDocument();
  });
});

describe("statTile", () => {
  it("formats numbers and exposes aria-labels", () => {
    renderWithRouter(<StatTile label="Machines" value={12} tone="healthy" ariaLabel="Machines: 12" />);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByLabelText("Machines: 12")).toBeInTheDocument();
  });

  it("renders dash for missing values", () => {
    renderWithRouter(<StatTile label="Active alerts" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("badges", () => {
  it("SimBadge marks simulated data", () => {
    renderWithRouter(<SimBadge isSimulated />);
    expect(screen.getByText("Sim")).toBeInTheDocument();
    expect(screen.getByLabelText("Simulated data")).toBeInTheDocument();
  });

  it("SimBadge marks real data", () => {
    renderWithRouter(<SimBadge isSimulated={false} />);
    expect(screen.getByText("Real")).toBeInTheDocument();
    expect(screen.getByLabelText("Real sensor data")).toBeInTheDocument();
  });

  it("Badge accepts tone variants", () => {
    renderWithRouter(<Badge tone="critical">critical</Badge>);
    expect(screen.getByText("critical")).toBeInTheDocument();
  });
});

describe("statusDot", () => {
  it("provides screen-reader labels", () => {
    renderWithRouter(<StatusDot color="bg-healthy" label="Connected" />);
    expect(screen.getByRole("img", { name: "Connected" })).toBeInTheDocument();
  });
});

describe("states", () => {
  it("error state exposes role=alert with retry wiring", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = renderWithRouter(<EmptyStateWithRetry onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Cannot reach backend")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    void rerender; // single mount is enough for the interaction assertion
  });

  it("empty state conveys hint text", () => {
    renderWithRouter(<EmptyState title="No machines yet" hint="Run the simulator" />);
    expect(screen.getByText("No machines yet")).toBeInTheDocument();
    expect(screen.getByText("Run the simulator")).toBeInTheDocument();
  });

  it("loading state is announced politely", () => {
    renderWithRouter(<LoadingState label="Loading fleet" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Loading fleet");
  });
});

describe("sidebar navigation", () => {
  it("renders all six routes as links", () => {
    renderWithRouter(<Sidebar activeAlerts={2} />, { path: "/" });

    for (const label of ["Overview", "Live Monitoring", "AI Analytics", "Devices", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    // The Alerts link name includes the live badge count.
    expect(screen.getByRole("link", { name: /Alerts/ })).toBeInTheDocument();
    expect(screen.getByLabelText("2 active alerts")).toBeInTheDocument();
  });

  it("keyboard navigation reaches the links", async () => {
    const user = userEvent.setup();
    renderWithRouter(<Sidebar />, { path: "/" });
    const first = screen.getByRole("link", { name: "Overview" });
    first.focus();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("link", { name: "Live Monitoring" }));
  });
});

function EmptyStateWithRetry({ onRetry }: { onRetry: () => void }): ReactElement {
  return <ErrorState message="Cannot reach backend" onRetry={onRetry} />;
}
