// TODO(Phase 5): rewrite graph surface with new workbench store API
// The previous GraphPage used selection.artifactId, selectArtifact, and registerGraphEntities
// which were removed in the workbench rewrite. This stub keeps the router from crashing.

export function GraphPage() {
  return (
    <div data-testid="graph-surface" className="flex-1 p-6">
      <p className="text-sm text-neutral-500">Graph surface coming soon.</p>
    </div>
  );
}
