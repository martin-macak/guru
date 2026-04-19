import { Outlet } from "react-router-dom";

import { useWorkbench } from "../../lib/state/workbench";
import { MenuBar } from "./MenuBar";

/**
 * The app shell owns the top menu bar and the full-viewport main area. Each
 * surface (Documents, Graph, Status) renders its own {@link RightPane} with
 * surface-specific metadata content; the shell MUST NOT render a second
 * RightPane here — doing so produced duplicate "Metadata" columns (see the
 * "renders exactly one metadata pane when mounted inside AppShell" test).
 */
export function AppShell() {
  const boot = useWorkbench((s) => s.boot);
  return (
    <div className="flex h-screen flex-col bg-neutral-50">
      <MenuBar projectName={boot.project.name} />
      <main data-surface-main className="flex min-h-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
