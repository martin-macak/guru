import { useState } from "react";

import { DocumentSearchHit, searchDocuments } from "../../lib/api/hooks";

export function DocumentSearchBox({
  onResults,
}: {
  onResults: (hits: DocumentSearchHit[] | null) => void;
}) {
  const [q, setQ] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!q.trim()) {
      onResults(null);
      return;
    }
    const hits = await searchDocuments(q.trim());
    onResults(hits);
  }

  return (
    <form
      role="search"
      onSubmit={submit}
      className="flex items-center gap-2 border-b border-neutral-200 p-2"
    >
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          if (!e.target.value) onResults(null);
        }}
        placeholder="Search documents (similarity)"
        className="flex-1 rounded border border-neutral-300 px-2 py-1 text-sm"
      />
      <button
        type="submit"
        className="rounded bg-neutral-900 px-2 py-1 text-sm text-white hover:bg-neutral-700"
      >
        Search
      </button>
    </form>
  );
}
