import { NavLink } from "react-router-dom";

import { useWorkbench } from "../../lib/state/workbench";
import { surfaceLabels, surfaceToPath, workbenchSurfaces } from "../../lib/state/url";
import { cn } from "../../lib/utils";

const surfaceDescriptions = {
  investigate: "Search and inspect indexed knowledge artifacts.",
  graph: "Traverse a bounded artifact neighborhood with selection-centered focus.",
  query: "Run advanced read-only graph queries against the current knowledge base.",
  operate: "Check server health, graph availability, and indexing runtime status.",
} as const;

export function AppShell() {
  const { boot, surface } = useWorkbench();

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(13,148,136,0.2),_transparent_38%),linear-gradient(180deg,_#f8fafc_0%,_#ecfeff_100%)] text-slate-950">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
        <header className="rounded-[2rem] border border-white/70 bg-white/80 px-5 py-4 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-md">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-teal-700">
                Knowledge Workbench
              </p>
              <div className="mt-3 flex items-baseline gap-3">
                <h1 className="text-3xl font-semibold tracking-[-0.05em]">{boot.project.name}</h1>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
                  {boot.graph.enabled ? "graph online" : "graph disabled"}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600">{boot.project.root}</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50/90 px-4 py-3 text-sm text-slate-600">
              <div className="font-medium text-slate-900">Web runtime</div>
              <div>{boot.web.available ? boot.web.url : boot.web.reason ?? "unavailable"}</div>
            </div>
          </div>
        </header>

        <div className="grid flex-1 gap-6 lg:grid-cols-[240px_minmax(0,1fr)_280px]">
          <aside className="rounded-[2rem] border border-white/70 bg-white/80 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-md">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Surfaces
            </p>
            <nav className="space-y-2" aria-label="Workbench navigation">
              {workbenchSurfaces.map((candidate) => (
                <NavLink
                  className={({ isActive }) =>
                    cn(
                      "flex rounded-2xl px-4 py-3 text-sm font-medium transition",
                      isActive
                        ? "bg-slate-950 text-white shadow-[0_16px_32px_rgba(15,23,42,0.18)]"
                        : "bg-slate-100/70 text-slate-700 hover:bg-slate-200/80",
                    )
                  }
                  key={candidate}
                  to={surfaceToPath(candidate)}
                >
                  {surfaceLabels[candidate]}
                </NavLink>
              ))}
            </nav>
          </aside>

          <main className="rounded-[2rem] border border-white/70 bg-white/85 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-md">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Active surface</p>
            <h2 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">{surfaceLabels[surface]}</h2>
            <p className="mt-3 max-w-2xl text-base text-slate-600">{surfaceDescriptions[surface]}</p>
          </main>

          <aside className="rounded-[2rem] border border-white/70 bg-white/80 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-md">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Inspector</p>
            <div className="mt-4 space-y-4 text-sm text-slate-600">
              <section>
                <h3 className="font-medium text-slate-900">Selection</h3>
                <p className="mt-1">Boot handshake is loaded. Routing is driving the active surface.</p>
              </section>
              <section>
                <h3 className="font-medium text-slate-900">Status</h3>
                <p className="mt-1">
                  Web {boot.web.enabled ? "enabled" : "disabled"} ·{" "}
                  {boot.web.available ? "available" : boot.web.reason ?? "unavailable"}
                </p>
              </section>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
