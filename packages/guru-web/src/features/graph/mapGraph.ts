import type { Edge, Node } from "reactflow";

import type { GraphNeighborsPayload } from "../../lib/api/client";
import type { GraphRoots } from "./useGraphRoots";

export function rootsToFlow(roots: GraphRoots): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [
    {
      id: "federation",
      data: { label: roots.federation_root.label, kind: "federation" },
      position: { x: 0, y: 0 },
      type: "default",
      draggable: false,
    },
  ];
  const edges: Edge[] = [];
  const ringRadius = 240;
  roots.kbs.forEach((kb, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, roots.kbs.length);
    nodes.push({
      id: `kb:${kb.name}`,
      data: { label: kb.name, kind: "kb" },
      position: { x: ringRadius * Math.cos(angle), y: ringRadius * Math.sin(angle) },
      type: "default",
      draggable: false,
    });
    edges.push({
      id: `federation->kb:${kb.name}`,
      source: "federation",
      target: `kb:${kb.name}`,
      style: { strokeDasharray: "4 4", opacity: 0.6 },
    });
  });
  return { nodes, edges };
}

export type GraphNodeData = {
  label: string;
  subtitle: string | null;
  isFocus: boolean;
};

function readSubtitle(properties: Record<string, unknown>): string | null {
  const kind = properties.kind;

  return typeof kind === "string" && kind.length ? kind : null;
}

function nodePosition(index: number, total: number) {
  if (index === 0) {
    return { x: 0, y: 0 };
  }

  const ringIndex = index - 1;
  const count = Math.max(total - 1, 1);
  const angle = (2 * Math.PI * ringIndex) / count;
  const radius = 220;

  return {
    x: Math.round(Math.cos(angle) * radius),
    y: Math.round(Math.sin(angle) * radius),
  };
}

export function mapGraph(
  graph: GraphNeighborsPayload,
): { nodes: Array<Node<GraphNodeData>>; edges: Edge[] } {
  const orderedNodes = [...graph.nodes].sort((left, right) => {
    if (left.id === graph.node_id) {
      return -1;
    }
    if (right.id === graph.node_id) {
      return 1;
    }
    return left.label.localeCompare(right.label);
  });

  const nodes = orderedNodes.map((node, index) => {
    const isFocus = node.id === graph.node_id;

    return {
      id: node.id,
      position: nodePosition(index, orderedNodes.length),
      data: {
        label: node.label,
        subtitle: readSubtitle(node.properties),
        isFocus,
      },
      style: {
        borderRadius: 20,
        border: isFocus ? "2px solid #0f766e" : "1px solid #cbd5e1",
        background: isFocus ? "#ccfbf1" : "#ffffff",
        color: "#0f172a",
        boxShadow: isFocus ? "0 14px 34px rgba(13, 148, 136, 0.18)" : "0 12px 28px rgba(15, 23, 42, 0.10)",
        padding: 12,
        width: 190,
      },
    } satisfies Node<GraphNodeData>;
  });

  const edges = graph.edges.map((edge) => ({
    id: `${edge.from_id}-${edge.to_id}-${edge.rel_type}-${edge.kind ?? "plain"}`,
    source: edge.from_id,
    target: edge.to_id,
    label: edge.kind ?? edge.rel_type,
    animated: edge.from_id === graph.node_id || edge.to_id === graph.node_id,
    style: { stroke: "#0f766e", strokeWidth: 1.5 },
    labelStyle: { fill: "#334155", fontSize: 12, fontWeight: 600 },
  }));

  return { nodes, edges };
}
