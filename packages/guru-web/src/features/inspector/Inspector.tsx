// Inspector is preserved for future use. Currently shows document path from workbench store.

import { useWorkbench } from "../../lib/state/workbench";

export function Inspector() {
  const selectedDocumentPath = useWorkbench((s) => s.selectedDocumentPath);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-neutral-500">
          Inspector
        </h2>
        <p className="mt-2 text-sm text-neutral-600">
          Select a document to inspect its metadata.
        </p>
      </div>

      {selectedDocumentPath ? (
        <article className="rounded border border-neutral-200 bg-neutral-50 p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-neutral-500">
            document
          </div>
          <dl className="mt-3 space-y-2 text-sm text-neutral-700">
            <div>
              <dt className="font-medium text-neutral-900">Path</dt>
              <dd className="break-all">{selectedDocumentPath}</dd>
            </div>
          </dl>
        </article>
      ) : (
        <div className="rounded border border-dashed border-neutral-300 bg-neutral-50 p-4 text-sm text-neutral-600">
          No current selection.
        </div>
      )}
    </div>
  );
}
