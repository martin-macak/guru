import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../../lib/api/client";

interface MetaPayload {
  lance: {
    path: string;
    chunk_count: number;
    token_count: number;
    tags: string[];
    ingested_at: string | null;
  };
  graph: { node_id: string; degree: number; links: { kind: string; target: string }[] } | null;
}

export function DocumentMetaPane({
  path,
  graphEnabled,
}: {
  path: string;
  graphEnabled: boolean;
}) {
  const { data, isLoading } = useQuery<MetaPayload>({
    queryKey: ["doc-meta", path],
    queryFn: async () => apiClient.get<MetaPayload>(`/documents/${encodeURIComponent(path)}/metadata`),
    enabled: !!path,
  });
  if (isLoading || !data) return <div className="text-sm text-neutral-500">Loading…</div>;
  return (
    <div className="space-y-4 text-sm">
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
          LanceDB
        </h3>
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-neutral-700">
          <dt>path</dt>
          <dd>{data.lance.path}</dd>
          <dt>chunks</dt>
          <dd>{data.lance.chunk_count}</dd>
          <dt>tokens</dt>
          <dd>{data.lance.token_count}</dd>
          <dt>tags</dt>
          <dd>{data.lance.tags.join(", ") || "—"}</dd>
          <dt>ingested</dt>
          <dd>{data.lance.ingested_at ?? "—"}</dd>
        </dl>
      </section>
      {graphEnabled && data.graph ? (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
            Graph
          </h3>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-neutral-700">
            <dt>node</dt>
            <dd>{data.graph.node_id}</dd>
            <dt>degree</dt>
            <dd>{data.graph.degree}</dd>
          </dl>
          {data.graph.links.length > 0 ? (
            <ul className="mt-2 space-y-1">
              {data.graph.links.map((l, i) => (
                <li key={i}>
                  <span className="text-neutral-500">{l.kind}</span> → {l.target}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
