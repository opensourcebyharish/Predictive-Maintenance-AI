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
        // Infrastructure phase gate: api client/hooks/mocks/tooling are covered
        // now; page and panel components are covered during Phase 5 page work.
        statements: 15,
        branches: 15,
        functions: 15,
        lines: 15,
      },
    },
  },
});
