import type { RuntimeStatusSnapshot } from "../../lib/api/client";

const fallbackRuntime: RuntimeStatusSnapshot = {
  project: {
    name: "guru",
    root: "/tmp/guru",
  },
  web: {
    enabled: true,
    available: true,
    url: "http://127.0.0.1:41773",
    reason: null,
    autoOpen: false,
  },
  graph: {
    enabled: true,
  },
};

type OperatePageProps = {
  runtime?: RuntimeStatusSnapshot;
};

export function OperatePage({ runtime = fallbackRuntime }: OperatePageProps) {

  return (
    <section className="grid gap-4 xl:grid-cols-2">
      <section className="rounded-[1.75rem] border border-slate-200 bg-white p-4">
        <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">Server Status</h3>
        <dl className="mt-4 space-y-3 text-sm text-slate-700">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-slate-500">Project</dt>
            <dd className="font-medium text-slate-950">{runtime.project.name}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-slate-500">Web</dt>
            <dd className="font-medium text-slate-950">
              {runtime.web.available ? "available" : runtime.web.reason ?? "unavailable"}
            </dd>
          </div>
        </dl>
      </section>

      <section className="rounded-[1.75rem] border border-slate-200 bg-slate-50/80 p-4">
        <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">Graph Status</h3>
        <dl className="mt-4 space-y-3 text-sm text-slate-700">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-slate-500">Runtime</dt>
            <dd className="font-medium text-slate-950">
              {runtime.graph.enabled ? "enabled" : "disabled"}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-slate-500">Web URL</dt>
            <dd className="truncate font-medium text-slate-950">
              {runtime.web.url ?? "not published"}
            </dd>
          </div>
        </dl>
      </section>
    </section>
  );
}
