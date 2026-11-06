/**
 * Reusable React Testing Library render utilities.
 *
 * renderWithRouter / renderApp provide the routing context that pages and the
 * App shell expect. MSW (src/test/mocks/server.ts) supplies the backend data.
 */

import { render, renderHook, type RenderOptions, type RenderHookResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { App } from "@/App";

interface RouterRenderOptions extends Omit<RenderOptions, "wrapper"> {
  /** URL the MemoryRouter starts at, e.g. "/alerts?status=active". */
  route?: string;
  /** Route pattern for the rendered tree inside <Routes> (default "*"). */
  path?: string;
}

export function renderWithRouter(
  ui: ReactElement,
  { route = "/", path = "*", ...options }: RouterRenderOptions = {},
): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={ui} />
      </Routes>
    </MemoryRouter>,
    options,
  );
}

/** Renders the whole app (AppShell + routed pages) at a given URL. */
export function renderApp(routes: ReactNode, initialEntry = "/"): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>{routes}</Routes>
    </MemoryRouter>,
  );
}

/**
 * Renders the full `<App />` route table at a URL — the right entry point when
 * a test exercises cross-page navigation (sidebar links, Links, route params
 * and document.title updates). UI defaults to the whole application.
 */
export function renderFullPath(ui: ReactElement = <App />, entry = "/"): ReturnType<typeof render> {
  return render(<MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter>);
}

export function renderHookWithRouter<TResult>(
  hook: () => TResult,
  options?: RouterRenderOptions,
): RenderHookResult<TResult, undefined> {
  const Wrapper = ({ children }: { children?: ReactNode }) => (
    <MemoryRouter initialEntries={[options?.route ?? "/"]}>{children}</MemoryRouter>
  );
  return renderHook(hook, { wrapper: Wrapper, ...(options ?? {}) });
}
