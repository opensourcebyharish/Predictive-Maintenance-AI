/**
 * Vitest bootstrap (configured via vite.config.ts `test.setupFiles`).
 *
 * - wires @testing-library/jest-dom matchers
 * - installs the MSW server for every test file (network fully mocked —
 *   tests never touch the real backend)
 * - resets settings-carrying localStorage between tests
 * - polyfills APIs Recharts expects inside jsdom
 */

import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, afterAll, beforeEach } from "vitest";

import { server } from "@/test/mocks/server";

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});

beforeEach(() => {
  // Fresh, default settings for every test (base URL, polling interval).
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  // Restore default handlers so per-test server.use(...) overrides do not leak.
  server.resetHandlers();
  // Rendered RTL components would otherwise be reused across cases
  // (globals:false means RTL cannot register cleanup itself).
  cleanup();
});

afterAll(() => {
  server.close();
});

// Recharts uses ResizeObserver to measure responsive containers; jsdom lacks it.
class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!("ResizeObserver" in globalThis)) {
  (globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverMock;
}

// jsdom does not implement matchMedia; some framer-motion helpers query it.
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: (): void => {},
      removeListener: (): void => {},
      addEventListener: (): void => {},
      removeEventListener: (): void => {},
      dispatchEvent: (): boolean => false,
    }),
  });
}
