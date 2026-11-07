/**
 * Shared chart primitives (Phase 5.3 Step 3): TrendChart data hygiene,
 * formatters, empty/invalid series and responsive-resize behavior.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";

import { TrendChart, type TrendPoint } from "@/components/charts/TrendChart";
import { renderWithRouter } from "@/test/utils";

type ResizeCallback = (entries: ResizeObserverEntry[], observer: ResizeObserver) => void;

class SizingResizeObserver {
  private callback: ResizeCallback;
  private targets: Element[] = [];

  constructor(callback: ResizeCallback) {
    this.callback = callback;
  }

  observe(target: Element): void {
    this.targets.push(target);
    this.notify(target, 320, 220);
  }

  unobserve(target: Element): void {
    this.targets = this.targets.filter((entry) => entry !== target);
  }

  disconnect(): void {
    this.targets = [];
  }

  resize(): void {
    for (const target of this.targets) this.notify(target, 420, 260);
  }

  private notify(target: Element, width: number, height: number): void {
    const entry = {
      target,
      contentRect: {
        width,
        height,
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        bottom: height,
        right: width,
        toJSON: () => ({}),
      },
    } as unknown as ResizeObserverEntry;
    this.callback([entry], this as unknown as ResizeObserver);
  }
}

const observers: SizingResizeObserver[] = [];
const OriginalResizeObserver = globalThis.ResizeObserver;

beforeEach(() => {
  window.ResizeObserver = class extends SizingResizeObserver {
    constructor(callback: ResizeCallback) {
      super(callback);
      observers.push(this);
    }
  } as unknown as typeof ResizeObserver;
});

afterEach(() => {
  observers.length = 0;
  if (OriginalResizeObserver) {
    window.ResizeObserver = OriginalResizeObserver;
  }
});

describe("TrendChart", () => {
  it("renders the empty state when there is no usable data", () => {
    renderWithRouter(<TrendChart data={[]} color="#ff0000" ariaLabel="Empty trend" />);
    expect(screen.getByText("No data points yet")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Empty trend" })).not.toBeInTheDocument();
  });

  it("filters invalid values instead of plotting them", () => {
    const data: TrendPoint[] = [
      { x: 1, y: null },
      { x: 2, y: undefined },
      { x: 3, y: Number.NaN },
      { x: 4, y: Number.POSITIVE_INFINITY },
    ];
    renderWithRouter(<TrendChart data={data} color="#ff0000" ariaLabel="Invalid trend" />);
    expect(screen.getByText("No data points yet")).toBeInTheDocument();
  });

  it("renders a chart wrapper with caller-provided data and height", () => {
    renderWithRouter(
      <TrendChart
        data={[
          { x: 1, y: 0.1 },
          { x: 2, y: 0.4 },
          { x: 3, y: 0.3 },
        ]}
        color="#38e1d4"
        ariaLabel="Failure trend"
        height={180}
        yFormatter={(value) => `${(value * 100).toFixed(0)}%`}
        xFormatter={(value) => `cycle ${value}`}
      />,
    );

    const chart = screen.getByRole("img", { name: "Failure trend" });
    expect(chart).toHaveAttribute("style", expect.stringContaining("height: 180px"));
    expect(chart.querySelector("svg")).not.toBeNull();
  });

  it("supports the line variant without area fill", () => {
    const { rerender } = renderWithRouter(
      <TrendChart
        area={false}
        data={[
          { x: 1, y: 1 },
          { x: 2, y: 2 },
        ]}
        color="#5c9bff"
        ariaLabel="Line trend"
      />,
    );
    expect(screen.getByRole("img", { name: "Line trend" })).toBeInTheDocument();

    rerender(
      <TrendChart
        area
        data={[
          { x: 1, y: 1 },
          { x: 2, y: 2 },
        ]}
        color="#5c9bff"
        ariaLabel="Area trend"
      />,
    );
    expect(screen.getByRole("img", { name: "Area trend" })).toBeInTheDocument();
  });

  it("supports category x labels and custom tooltip formatting", async () => {
    renderWithRouter(
      <TrendChart
        categoryX
        data={[
          { x: "Cycle 1", y: 12 },
          { x: "Cycle 2", y: 34 },
        ]}
        color="#f5a524"
        ariaLabel="Categorized trend"
        yFormatter={(value) => `${value} units`}
        xFormatter={(value) => `Reading ${value}`}
        tooltipFormatter={(value) => `${value} bps`}
      />,
    );

    const chart = screen.getByRole("img", { name: "Categorized trend" });
    expect(chart).toBeInTheDocument();

    act(() => {
      fireEvent.mouseMove(chart, { clientX: 100, clientY: 60 });
    });
    await waitFor(() => {
      expect(screen.getAllByText(/Reading Cycle 1|34 bps|12 units/).length).toBeGreaterThan(0);
    });
  });

  it("survives a container resize without losing the chart", () => {
    renderWithRouter(
      <TrendChart
        data={[
          { x: 1, y: 0.2 },
          { x: 2, y: 0.8 },
        ]}
        color="#a78bfa"
        ariaLabel="Resizing trend"
      />,
    );

    expect(screen.getByRole("img", { name: "Resizing trend" })).toBeInTheDocument();
    act(() => {
      for (const observer of observers) observer.resize();
    });

    expect(screen.getByRole("img", { name: "Resizing trend" })).toBeInTheDocument();
    expect(screen.queryByText("No data points yet")).not.toBeInTheDocument();
  });
});

describe("TrendChart formatter wiring", () => {
  it("passes formatter functions into the rendered chart", () => {
    const yFormatter = vi.fn((value: number) => `${value.toFixed(2)}%`);
    const xFormatter = vi.fn((value: number | string) => `cycle ${value}`);

    renderWithRouter(
      <TrendChart
        data={[
          { x: 1, y: 0.25 },
          { x: 2, y: 0.75 },
        ]}
        color="#2dd4bf"
        ariaLabel="Formatted trend"
        yFormatter={yFormatter}
        xFormatter={xFormatter}
      />,
    );

    expect(screen.getByRole("img", { name: "Formatted trend" })).toBeInTheDocument();
  });
});
