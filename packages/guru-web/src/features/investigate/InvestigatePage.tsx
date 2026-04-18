import { useState } from "react";

import { filterInvestigateResults, useWorkbench } from "../../lib/state/workbench";
import { cn } from "../../lib/utils";

export function InvestigatePage() {
  const [query, setQuery] = useState("");
  const { selection, selectEntity } = useWorkbench();
  const results = filterInvestigateResults(query);

  return (
    <section className="space-y-5">
      <label className="block">
        <span className="sr-only">Search knowledge base</span>
        <input
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-950 shadow-sm outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search knowledge base"
          type="search"
          value={query}
        />
      </label>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
        <section className="rounded-[1.75rem] border border-slate-200 bg-slate-50/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">Results</h3>
            <span className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
              {results.length} hits
            </span>
          </div>

          <div className="mt-4 space-y-3">
            {results.length ? (
              results.map((result) => {
                const isSelected =
                  selection.documentId === result.entityId || selection.artifactId === result.entityId;

                return (
                  <button
                    className={cn(
                      "w-full rounded-2xl border px-4 py-3 text-left transition",
                      isSelected
                        ? "border-teal-300 bg-teal-50"
                        : "border-slate-200 bg-white hover:bg-slate-100",
                    )}
                    key={result.id}
                    onClick={() => selectEntity(result.entityId)}
                    type="button"
                  >
                    <div className="font-medium text-slate-950">{result.title}</div>
                    <div className="mt-2 text-sm text-slate-600">{result.excerpt}</div>
                  </button>
                );
              })
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-6 text-sm text-slate-600">
                No investigate results match the current search.
              </div>
            )}
          </div>
        </section>

        <aside className="rounded-[1.75rem] border border-slate-200 bg-white p-4">
          <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">Inspector</h3>
          <p className="mt-3 text-sm text-slate-600">
            Select a document or artifact to inspect its metadata.
          </p>
          <p className="mt-4 text-xs uppercase tracking-[0.18em] text-slate-500">
            Shared selection keeps the tree, result list, and inspector aligned.
          </p>
        </aside>
      </div>
    </section>
  );
}
