import { useCallback, useMemo, useState } from "react";
import type { Edge, Node } from "reactflow";

import { rootsToFlow } from "./mapGraph";
import type { GraphRoots } from "./useGraphRoots";

interface NeighborsPayload {
  nodes: { id: string; label: string; kind: string; kb?: string }[];
  edges: { source: string; target: string; kind: string }[];
}

export function useGraphCanvas(roots: GraphRoots | undefined) {
  const rootsFlow = useMemo(() => (roots ? rootsToFlow(roots) : { nodes: [], edges: [] }), [roots]);
  const [extraNodes, setExtraNodes] = useState<Node[]>([]);
  const [extraEdges, setExtraEdges] = useState<Edge[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const mergeNeighbors = useCallback((focusId: string, payload: NeighborsPayload) => {
    setExtraNodes((prev) => {
      const existing = new Set(prev.map((n) => n.id).concat(rootsFlow.nodes.map((n) => n.id)));
      const additions: Node[] = [];
      payload.nodes.forEach((n, i) => {
        if (existing.has(n.id)) return;
        additions.push({
          id: n.id,
          data: { label: n.label, kind: n.kind, kb: n.kb },
          position: { x: 400 + 120 * Math.cos(i), y: 120 * Math.sin(i) },
          type: "default",
        });
      });
      return [...prev, ...additions];
    });
    setExtraEdges((prev) => {
      const existing = new Set(prev.map((e) => `${e.source}->${e.target}`));
      const additions: Edge[] = payload.edges
        .filter((e) => !existing.has(`${e.source}->${e.target}`))
        .map((e) => ({ id: `${e.source}->${e.target}`, source: e.source, target: e.target, label: e.kind }));
      return [...prev, ...additions];
    });
    setSelectedId(focusId);
  }, [rootsFlow.nodes]);

  const clear = useCallback(() => {
    setExtraNodes([]);
    setExtraEdges([]);
    setSelectedId(null);
  }, []);

  return {
    nodes: [...rootsFlow.nodes, ...extraNodes],
    edges: [...rootsFlow.edges, ...extraEdges],
    selectedId,
    setSelectedId,
    mergeNeighbors,
    clear,
  };
}
