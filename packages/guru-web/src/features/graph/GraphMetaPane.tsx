import { DocumentMetaPane } from "../documents/DocumentMetaPane";

export function GraphMetaPane({ selectedId }: { selectedId: string | null }) {
  if (!selectedId) return <p className="text-sm text-neutral-500">Select a node to see its metadata.</p>;
  if (selectedId === "federation")
    return <p className="text-sm text-neutral-500">The Federation root is a UI-only orientation anchor.</p>;
  if (selectedId.startsWith("kb:")) {
    const name = selectedId.slice(3);
    return (
      <div className="space-y-2 text-sm">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">Knowledge base</h3>
        <div>{name}</div>
      </div>
    );
  }
  if (selectedId.startsWith("doc:")) {
    const path = selectedId.slice(4);
    return <DocumentMetaPane path={path} graphEnabled={true} />;
  }
  return <p className="text-sm text-neutral-500">Unsupported node.</p>;
}
