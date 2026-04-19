import { useState } from "react";

export function QueryInput({
  onRun,
  onRestore,
  inResultsMode,
  error,
}: {
  onRun: (cypher: string) => void;
  onRestore?: () => void;
  inResultsMode?: boolean;
  error?: string | null;
}) {
  const [text, setText] = useState("");
  return (
    <div className="flex flex-col border-b border-neutral-200 bg-white">
      <div className="flex items-center gap-2 p-2">
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
      {error ? (
        <p role="alert" className="px-2 pb-1 text-xs text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
