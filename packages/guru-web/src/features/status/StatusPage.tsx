import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useWorkbench } from "../../lib/state/workbench";
import { reconcileSync, useSyncStatus } from "../../lib/api/hooks";

export function StatusPage() {
  const setSurface = useWorkbench((s) => s.setSurface);
  useEffect(() => setSurface("status"), [setSurface]);
  const boot = useWorkbench((s) => s.boot);
  const { data, isLoading } = useSyncStatus();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  async function reconcile() {
    setBusy(true);
    try {
      const next = await reconcileSync();
      qc.setQueryData(["sync", "status"], next);
    } finally {
      setBusy(false);
    }
  }

  if (isLoading || !data) return <div className="p-6 text-sm text-neutral-500">Loading…</div>;

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-xl font-semibold">Status</h1>
      <section className="mt-6 grid max-w-3xl grid-cols-3 gap-4">
        <Card title="LanceDB documents" value={data.lancedb_count} />
        <Card title="Graph documents" value={data.graph_count} />
        <Card title="drift" value={data.drift} />
      </section>
      <section className="mt-6 max-w-3xl rounded border border-neutral-200 bg-white p-4 text-sm">
        <div>
          Project: <strong>{boot.project.name}</strong>
        </div>
        <div>
          Graph daemon: <strong>{data.graph_enabled ? "enabled" : "disabled"}</strong>
        </div>
        <div>
          Last reconciled: <strong>{data.last_reconciled_at ?? "—"}</strong>
        </div>
        <button
          type="button"
          onClick={reconcile}
          disabled={!data.graph_enabled || busy}
          className="mt-4 rounded bg-neutral-900 px-3 py-1 text-white disabled:opacity-50"
        >
          Reconcile now
        </button>
      </section>
    </div>
  );
}

function Card({ title, value }: { title: string; value: number }) {
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">{title}</div>
      <div className="mt-1 text-3xl font-semibold">{value}</div>
    </div>
  );
}
