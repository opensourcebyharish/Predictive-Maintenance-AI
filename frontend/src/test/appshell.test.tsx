/**
 * AppShell + Sidebar (Phase 5.2 Step 2): navigation across every route,
 * document.title syncing, active-link semantics, alert badge, connection
 * indicator and the responsive shell structure.
 *
 * jsdom note: Tailwind CSS is not applied in vitest (css:false), so the
 * desktop aside and the mobile nav row — normally one `hidden` and one
 * `md:hidden` copy — are BOTH in the accessibility tree and tab order.
 * Tests below use getAllBy* with an explanatory comment instead of assuming
 * a single sidebar instance.
 */

import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { ApiError, api } from "@/api/client";
import { API_BASE, NETWORK_ERROR_HANDLERS } from "@/test/mocks/handlers";
import { READINESS_OK } from "@/test/mocks/fixtures";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";

afterEach(() => {
  vi.useRealTimers();
});

const NAV_LABELS = ["Overview", "Live Monitoring", "AI Analytics", "Alerts", "Devices", "Settings"] as const;

describe("AppShell", () => {
  it("renders brand, responsive nav copies, connection badge and alert pill", async () => {
    renderFullPath(undefined, "/");

    expect(await screen.findByLabelText("Predictive Maintenance AI home")).toBeInTheDocument();

    // Desktop aside + mobile nav row each render a Sidebar; with CSS missing
    // in jsdom both copies stay focusable (display:none semantics are
    // honoured in real browsers only).
    expect(await screen.findAllByRole("navigation", { name: "Primary" })).toHaveLength(2);
    for (const label of NAV_LABELS) {
      // accName joins the pill text without a separator ("Alerts2 active
      // alerts"), so no word-boundary assertion is possible.
      const pattern = label === "Alerts" ? /^alerts/i : new RegExp(`^${label}$`, "i");
      expect(screen.getAllByRole("link", { name: pattern })).toHaveLength(2);
    }

    // Connection badge reacts to the successful /health probe.
    expect(await screen.findByLabelText("Backend connection: Backend online · v0.2.0 · services ready")).toBeInTheDocument();

    // Poll summary drives the pill on both nav copies (fixture: 2 active).
    expect(await screen.findAllByLabelText("2 active alerts")).toHaveLength(2);
  });

  it("navigates into Alerts, marks it current and syncs document.title", async () => {
    const user = userEvent.setup();
    renderFullPath(undefined, "/");

    expect(await screen.findByText("Fleet Overview")).toBeInTheDocument();
    expect(document.title).toBe("Overview · Predictive Maintenance AI");

    await user.click(screen.getAllByRole("link", { name: /^alerts/i })[0]);

    expect(await screen.findByRole("heading", { name: "Alerts & Incidents" })).toBeInTheDocument();
    expect(document.title).toBe("Alerts & Incidents · Predictive Maintenance AI");
    for (const link of screen.getAllByRole("link", { name: /^alerts/i })) {
      expect(link).toHaveAttribute("aria-current", "page");
    }
    for (const link of screen.getAllByRole("link", { name: /^overview$/i })) {
      expect(link).not.toHaveAttribute("aria-current");
    }
  });

  it("crosses the remaining routes with correct titles and headings", async () => {
    const user = userEvent.setup();
    renderFullPath(undefined, "/monitoring");

    expect(await screen.findByRole("heading", { name: "Live Monitoring" })).toBeInTheDocument();
    expect(document.title).toBe("Live Monitoring · Predictive Maintenance AI");

    await user.click(screen.getAllByRole("link", { name: /^ai analytics$/i })[0]);
    expect(await screen.findByRole("heading", { name: "AI Analytics" })).toBeInTheDocument();
    expect(document.title).toBe("AI Analytics · Predictive Maintenance AI");

    await user.click(screen.getAllByRole("link", { name: /^settings$/i })[0]);
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(document.title).toBe("Settings · Predictive Maintenance AI");

    await user.click(screen.getAllByRole("link", { name: /^devices$/i })[0]);
    expect(await screen.findByRole("heading", { name: "Device Management" })).toBeInTheDocument();
    expect(document.title).toBe("Device Management · Predictive Maintenance AI");
  });

  it("uses a route-derived fallback title on unindexed paths", async () => {
    renderFullPath(undefined, "/devices/SIM-001");
    await waitFor(() => expect(document.title).toBe("Devices · Predictive Maintenance AI"));
  });

  it("flips the connection badge to offline after a network-level failure", async () => {
    renderFullPath(undefined, "/");
    await screen.findByLabelText("Backend connection: Backend online · v0.2.0 · services ready");

    server.use(...NETWORK_ERROR_HANDLERS);
    await expect(api.request("/health")).rejects.toBeInstanceOf(ApiError);

    await screen.findByLabelText("Backend connection: Backend offline · network failure");
  });

  it("reports HTTP failures separately from connectivity and readiness", async () => {
    server.use(
      http.get(`${API_BASE}/health`, () =>
        HttpResponse.json(
          { detail: { error: "internal_error", message: "simulated backend failure" } },
          { status: 500 },
        ),
      ),
    );
    renderFullPath(undefined, "/");

    const badge = await screen.findByLabelText("Backend connection: Backend HTTP failure · 500");
    expect(badge).toBeInTheDocument();
  });

  it("does not call the service fully healthy when /ready reports not ready", async () => {
    server.use(
      http.get(`${API_BASE}/ready`, () =>
        HttpResponse.json({
          ...READINESS_OK,
          ready: false,
          datasets: Object.fromEntries(
            Object.entries(READINESS_OK.datasets).map(([id, dataset]) => [
              id,
              { ...dataset, ready: false },
            ]),
          ),
        }),
      ),
    );
    renderFullPath(undefined, "/");

    const badge = await screen.findByLabelText(
      "Backend connection: Backend connected · service not ready",
    );
    expect(badge).toBeInTheDocument();
  });

  it("moves keyboard focus through the primary navigation", async () => {
    const user = userEvent.setup();
    renderFullPath(undefined, "/");
    await screen.findByLabelText("Backend connection: Backend online · v0.2.0 · services ready");

    screen.getAllByRole("link", { name: /^overview$/i })[0].focus();
    await user.tab();

    expect(document.activeElement).toHaveAccessibleName(/^live monitoring$/i);
  });

  it("exposes the responsive shell structure for real CSS to act on", () => {
    const { container, unmount } = renderFullPath(undefined, "/");
    // Desktop: aside hidden below md, flex from md up.
    const aside = container.querySelector("aside");
    expect(aside?.className).toContain("hidden");
    expect(aside?.className).toContain("md:flex");
    expect(aside?.textContent).toContain("Live Monitoring");

    // Mobile: separate nav row hidden from md up.
    expect(container.querySelector(".md\\:hidden")?.textContent).toContain("Settings");

    unmount();
  });
});
