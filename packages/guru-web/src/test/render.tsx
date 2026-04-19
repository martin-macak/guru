import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender } from "@testing-library/react";
import type { RenderOptions, RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { Location, ReactElement } from "react";

export * from "@testing-library/react";
export { render } from "@testing-library/react";

interface RenderWithRouterOptions extends Omit<RenderOptions, "wrapper"> {
  route?: string;
}

interface RouterLocation {
  pathname: string;
  search: string;
  hash: string;
}

interface RenderWithRouterResult extends RenderResult {
  router: {
    state: {
      location: RouterLocation;
    };
  };
}

function LocationSpy({ locationRef }: { locationRef: { current: RouterLocation } }) {
  const loc = useLocation();
  locationRef.current = { pathname: loc.pathname, search: loc.search, hash: loc.hash };
  return null;
}

export function renderWithRouter(
  ui: ReactElement,
  { route = "/", ...options }: RenderWithRouterOptions = {},
): RenderWithRouterResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const locationRef: { current: RouterLocation } = {
    current: { pathname: "/", search: "", hash: "" },
  };

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <LocationSpy locationRef={locationRef} />
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  const result = rtlRender(ui, { wrapper: Wrapper, ...options });

  return {
    ...result,
    router: {
      state: {
        get location() {
          return locationRef.current;
        },
      },
    },
  };
}
