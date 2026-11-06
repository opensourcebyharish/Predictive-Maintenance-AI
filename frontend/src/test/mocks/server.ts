/**
 * Singleton MSW server for Vitest. Installed from src/test/setup.ts; tests may
 * override handlers per-test via server.use(...) — setup resets to defaults.
 */

import { setupServer } from "msw/node";

import { DEFAULT_HANDLERS } from "@/test/mocks/handlers";

export const server = setupServer(...DEFAULT_HANDLERS);
