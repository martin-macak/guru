import { useWorkbench } from "../../lib/state/workbench";

export function RightPane({ children }: { children: React.ReactNode }) {
  const surface = useWorkbench((s) => s.surface);
  const isOpen = useWorkbench((s) => s.rightPaneOpen[surface]);
  const toggle = useWorkbench((s) => s.toggleRightPane);

  return (
    <aside
      className={
        isOpen
          ? "w-80 border-l border-neutral-200 bg-white"
          : "w-8 border-l border-neutral-200 bg-neutral-50"
      }
      aria-label="Metadata"
    >
      <div className="flex items-center justify-between p-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
          {isOpen ? "Metadata" : ""}
        </span>
        <button
          type="button"
          aria-label="Toggle metadata pane"
          onClick={() => toggle(surface)}
          className="rounded p-1 text-neutral-500 hover:bg-neutral-100"
        >
          {isOpen ? "›" : "‹"}
        </button>
      </div>
      {isOpen ? <div className="p-3">{children}</div> : null}
    </aside>
  );
}
