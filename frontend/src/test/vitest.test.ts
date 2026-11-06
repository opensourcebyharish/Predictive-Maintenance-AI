/**
 * Step 5 verifies the test infrastructure itself: Vitest executes, asserters
 * work, and the DOM environment is live. Kept intentionally minimal.
 */

import { describe, expect, it } from "vitest";

describe("vitest runner", () => {
  it("executes basic assertions", () => {
    expect(1 + 1).toBe(2);
    expect({ api: "mocked" }).toEqual({ api: "mocked" });
    expect("predictive-maintenance").toMatch(/^predictive/);
  });

  it("supports async tests", async () => {
    await Promise.resolve();
    expect(true).toBe(true);
  });

  it("runs in jsdom with jest-dom matchers available", () => {
    const node = document.createElement("div");
    node.textContent = "control deck";
    document.body.append(node);
    expect(node).toBeInTheDocument();
    expect(node).toHaveTextContent("control deck");
    node.remove();
    expect(node).not.toBeInTheDocument();
  });
});
