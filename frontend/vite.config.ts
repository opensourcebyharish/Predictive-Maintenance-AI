/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Shared by the app build and Vitest (tests import modules via "@/...").
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    // jsdom + Testing Library for React component tests.
    environment: "jsdom",
    globals: false, // import { describe, it, expect } from "vitest" explicitly
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false, // skip Tailwind processing in tests (classes are not asserted)
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      reportsDirectory: "coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx", // entry point, no logic
        "src/**/*.d.ts",
        "src/test/**", // test tooling itself
        "src/**/*.test.{ts,tsx}",
        "src/**/*.spec.{ts,tsx}",
      ],
      thresholds: {
        // Phase 5.2 gate: component + dashboard-page suites kept the suite at
        // 91.76 stmts / 83.8 branch / 94.11 funcs / 93.46 lines — thresholds
        // sit just under with a whole-percent of run-to-run headroom.
        statements: 90,
        branches: 82,
        functions: 93,
        lines: 92,
      },
    },
  },
});
