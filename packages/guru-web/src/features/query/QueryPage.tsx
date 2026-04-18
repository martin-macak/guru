export function QueryPage() {
  return (
    <section className="space-y-4">
      <h3 className="text-lg font-semibold tracking-[-0.03em] text-slate-950">Read-only Query</h3>
      <label className="block">
        <span className="sr-only">Cypher query</span>
        <textarea
          aria-label="Cypher query"
          className="min-h-48 w-full rounded-[1.5rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-950 shadow-sm outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
          defaultValue={"MATCH (artifact)-[rel]->(neighbor)\nRETURN artifact, rel, neighbor\nLIMIT 25"}
        />
      </label>
      <button
        className="rounded-full bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
        type="button"
      >
        Run Query
      </button>
    </section>
  );
}
