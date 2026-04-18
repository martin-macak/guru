import { useWorkbench } from "../../lib/state/workbench";

export function Inspector() {
  const { selectedEntity } = useWorkbench();

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">
          Inspector
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Select a document or artifact to inspect its metadata.
        </p>
      </div>

      {selectedEntity ? (
        <article className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            {selectedEntity.kind}
          </div>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-slate-950">
            {selectedEntity.title}
          </h3>
          <p className="mt-3 text-sm text-slate-600">{selectedEntity.summary}</p>
          <dl className="mt-4 space-y-2 text-sm text-slate-700">
            <div>
              <dt className="font-medium text-slate-950">Type</dt>
              <dd>{selectedEntity.kind === "document" ? "Document" : "Artifact"}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-950">Location</dt>
              <dd className="break-all">{selectedEntity.location}</dd>
            </div>
          </dl>
        </article>
      ) : (
        <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-slate-50/70 p-4 text-sm text-slate-600">
          No current selection.
        </div>
      )}
    </div>
  );
}
