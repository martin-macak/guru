import { useBootQuery } from "../lib/api/hooks";
import { WorkbenchProvider } from "../lib/state/workbench";
import { surfaceFromPathname } from "../lib/state/url";
import { AppProviders } from "./providers";
import { AppRouter } from "./router";

function AppBody() {
  const boot = useBootQuery();

  if (boot.isPending) {
    return <p className="p-6 text-sm text-slate-600">Loading Guru…</p>;
  }

  if (boot.isError || !boot.data) {
    return <p className="p-6 text-sm text-slate-600">Server unavailable</p>;
  }

  return (
    <WorkbenchProvider boot={boot.data} initialSurface={surfaceFromPathname(window.location.pathname)}>
      <AppRouter />
    </WorkbenchProvider>
  );
}

export function App() {
  return (
    <AppProviders>
      <AppBody />
    </AppProviders>
  );
}
