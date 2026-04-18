import { knowledgeTreeGroups, useWorkbench } from "../../lib/state/workbench";
import { cn } from "../../lib/utils";

export function KnowledgeTree() {
  const { selection, selectEntity } = useWorkbench();

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">
          Knowledge Tree
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Traverse the current knowledge base without dropping into filesystem mode.
        </p>
      </div>

      {knowledgeTreeGroups.map((group) => (
        <section key={group.label}>
          <h3 className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {group.label}
          </h3>
          <div className="mt-2 space-y-2">
            {group.items.map((item) => {
              const isSelected =
                selection.documentId === item.id || selection.artifactId === item.id;

              return (
                <button
                  className={cn(
                    "w-full rounded-2xl border px-3 py-3 text-left transition",
                    isSelected
                      ? "border-teal-300 bg-teal-50 text-slate-950"
                      : "border-slate-200 bg-slate-50/80 text-slate-700 hover:bg-slate-100",
                  )}
                  key={item.id}
                  onClick={() => selectEntity(item.id)}
                  type="button"
                >
                  <div className="font-medium">{item.title}</div>
                  <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">
                    {item.kind}
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
