import { Outlet } from "react-router-dom";

import { useWorkbench } from "../../lib/state/workbench";
import { MenuBar } from "./MenuBar";
import { RightPane } from "./RightPane";

export function AppShell() {
  const boot = useWorkbench((s) => s.boot);
  return (
    <div className="flex h-screen flex-col bg-neutral-50">
      <MenuBar projectName={boot.project.name} />
      <div data-surface-main className="flex min-h-0 flex-1 overflow-hidden">
        <main className="flex min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
        <RightPane>{null}</RightPane>
      </div>
    </div>
  );
}
