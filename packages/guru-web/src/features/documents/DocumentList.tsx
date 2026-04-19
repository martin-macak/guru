import { useDocuments } from "../../lib/api/hooks";

export function DocumentList({
  onSelect,
  selectedPath,
}: {
  onSelect: (path: string) => void;
  selectedPath: string | null;
}) {
  const { data, isLoading, isError } = useDocuments();
  if (isLoading) return <div className="p-3 text-sm text-neutral-500">Loading…</div>;
  if (isError) return <div className="p-3 text-sm text-red-600">Failed to load documents.</div>;
  return (
    <ul className="divide-y divide-neutral-200">
      {(data ?? []).map((doc) => (
        <li
          key={doc.path}
          aria-label={doc.title}
          aria-selected={doc.path === selectedPath}
          role="listitem"
          onClick={() => onSelect(doc.path)}
          className={
            "cursor-pointer p-3 text-sm " +
            (doc.path === selectedPath ? "bg-neutral-900 text-white" : "hover:bg-neutral-100")
          }
        >
          <div className="font-medium">{doc.title}</div>
          <div className="text-xs text-neutral-500">{doc.excerpt}</div>
        </li>
      ))}
    </ul>
  );
}
