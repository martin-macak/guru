import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MiniMap } from "reactflow";
import "reactflow/dist/style.css";

import type { GraphDisabledPayload, GraphNeighborsPayload } from "../../lib/api/client";
import { getGraphNeighbors, isGraphDisabled } from "../../lib/api/client";
import { useWorkbench } from "../../lib/state/workbench";
import { mapGraph } from "./mapGraph";

function EmptyGraphState({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50/70 p-6 text-sm text-slate-600">
      <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">{title}</h3>
      <p className="mt-2">{body}</p>
    </div>
  );
}

export function GraphPage() {
  const { boot, selection, selectArtifact } = useWorkbench();
  const [depth, setDepth] = useState(1);
  const [graphState, setGraphState] = useState<{
    status: "idle" | "loading" | "ready" | "error";
    data: GraphNeighborsPayload | GraphDisabledPayload | null;
  }>({
    status: "idle",
    data: null,
  });
  const focusArtifactId = selection.artifactId;

  useEffect(() => {
    let cancelled = false;

    if (!boot.graph.enabled || !focusArtifactId) {
      setGraphState({ status: "idle", data: null });
      return () => {
        cancelled = true;
      };
    }

    setGraphState({ status: "loading", data: null });

    getGraphNeighbors({
      nodeId: focusArtifactId,
      depth,
    })
      .then((data) => {
        if (!cancelled) {
          setGraphState({ status: "ready", data });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGraphState({ status: "error", data: null });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [boot.graph.enabled, depth, focusArtifactId]);

  const mappedGraph = useMemo(() => {
    const data = graphState.data;

    if (!data || isGraphDisabled(data)) {
      return null;
    }

    return mapGraph(data);
  }, [graphState.data]);

  const focusedNode = useMemo(() => {
    const data = graphState.data;

    if (!data || isGraphDisabled(data) || !focusArtifactId) {
      return null;
    }

    return (
      data.nodes.find((node) => node.id === focusArtifactId) ??
      data.nodes.find((node) => node.id === data.node_id) ??
      null
    );
  }, [focusArtifactId, graphState.data]);

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">
            Artifact neighborhood
          </h3>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            React Flow renders a bounded neighborhood around the focused artifact. Selection
            remains the source of truth.
          </p>
        </div>

        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
          <span className="font-medium text-slate-700">Neighborhood depth</span>
          <button
            className="rounded-full border border-slate-300 px-3 py-1 text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={depth <= 1}
            onClick={() => setDepth((current) => Math.max(1, current - 1))}
            type="button"
          >
            -
          </button>
          <span className="w-6 text-center font-semibold text-slate-950">{depth}</span>
          <button
            className="rounded-full border border-slate-300 px-3 py-1 text-slate-700"
            onClick={() => setDepth((current) => current + 1)}
            type="button"
          >
            +
          </button>
        </div>
      </div>

      {!boot.graph.enabled ? (
        <EmptyGraphState
          body="Graph support is disabled for this project."
          title="Graph unavailable"
        />
      ) : !focusArtifactId ? (
        <EmptyGraphState
          body="Select an artifact to explore its neighborhood."
          title="Graph waiting for selection"
        />
      ) : graphState.status === "loading" ? (
        <EmptyGraphState body="Loading the focused artifact neighborhood." title="Loading graph" />
      ) : graphState.status === "error" ? (
        <EmptyGraphState
          body="The browser could not load the current graph neighborhood."
          title="Graph request failed"
        />
      ) : graphState.data && isGraphDisabled(graphState.data) ? (
        <EmptyGraphState
          body="The graph daemon is unavailable right now."
          title="Graph unavailable"
        />
      ) : mappedGraph && focusedNode ? (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
            <article className="rounded-[1.75rem] border border-slate-200 bg-slate-50/80 p-4">
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                Focused node
              </div>
              <h4 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {focusedNode.label}
              </h4>
              <p className="mt-3 text-sm text-slate-600 break-all">{focusedNode.id}</p>
              <dl className="mt-4 space-y-2 text-sm text-slate-700">
                <div>
                  <dt className="font-medium text-slate-950">Kind</dt>
                  <dd>
                    {typeof focusedNode.properties.kind === "string"
                      ? focusedNode.properties.kind
                      : "artifact"}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-950">Neighborhood</dt>
                  <dd>
                    {mappedGraph.nodes.length} nodes · {mappedGraph.edges.length} edges
                  </dd>
                </div>
              </dl>
            </article>

            <div
              aria-label="graph-canvas"
              className="h-[480px] overflow-hidden rounded-[1.75rem] border border-slate-200 bg-white"
            >
              <ReactFlow
                edges={mappedGraph.edges}
                fitView
                nodes={mappedGraph.nodes}
                onNodeClick={(_event, node) => selectArtifact(node.id)}
              >
                <MiniMap pannable zoomable />
                <Controls showInteractive={false} />
                <Background color="#cbd5e1" gap={20} />
              </ReactFlow>
            </div>
          </div>
        </div>
      ) : (
        <EmptyGraphState
          body="No graph neighborhood was returned for the current selection."
          title="No graph data"
        />
      )}
    </section>
  );
}
