import { useState } from "react";

export function QueryInput({
  onRun,
  onRestore,
  inResultsMode,
}: {
  onRun: (cypher: string) => void;
  onRestore?: () => void;
  inResultsMode?: boolean;
}) {
  const [text, setText] = useState("");
  return (
    <div className="flex items-center gap-2 border-b border-neutral-200 bg-white p-2">
      <label htmlFor="cypher" className="sr-only">Cypher</label>
      <input
        id="cypher"
        className="flex-1 rounded border border-neutral-300 px-2 py-1 font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Cypher (read-only)"
      />
      <button
        type="button"
        onClick={() => onRun(text)}
        className="rounded bg-neutral-900 px-2 py-1 text-xs text-white"
      >
        Run
      </button>
      {inResultsMode && onRestore ? (
        <button
          type="button"
          onClick={onRestore}
          className="rounded border border-neutral-300 px-2 py-1 text-xs"
        >
          Back to exploration
        </button>
      ) : null}
    </div>
  );
}
