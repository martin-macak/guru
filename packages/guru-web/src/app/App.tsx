import { Button } from "../components/ui/button";

export function App() {
  return (
    <main className="app-shell">
      <section className="app-card" aria-labelledby="guru-title">
        <p className="app-eyebrow">Knowledge Workbench</p>
        <h1 className="app-title" id="guru-title">
          Guru
        </h1>
        <p className="app-copy">Local-first, repo-aware navigation for knowledge work.</p>
        <Button type="button">Open workbench</Button>
      </section>
    </main>
  );
}
