import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { useEffect } from "react";

import { useWorkbench } from "../../lib/state/workbench";
import { useGraphRoots } from "./useGraphRoots";
import { rootsToFlow } from "./mapGraph";

export function GraphPage() {
  const setSurface = useWorkbench((s) => s.setSurface);
  useEffect(() => setSurface("graph"), [setSurface]);
  const roots = useGraphRoots();
  if (roots.isLoading) return <div className="flex-1 p-6 text-sm text-neutral-500">Loading graph…</div>;
  if (roots.isError || !roots.data) return <div className="flex-1 p-6 text-sm text-red-600">Graph unavailable.</div>;
  const flow = rootsToFlow(roots.data);
  return (
    <div className="flex flex-1">
      <ReactFlow nodes={flow.nodes} edges={flow.edges}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
