import { Button } from "../components/ui/button";

export function App() {
  return (
    <main className="grid min-h-screen place-items-center p-8">
      <section
        aria-labelledby="guru-title"
        className="w-full max-w-2xl rounded-3xl border border-slate-200/80 bg-white/80 p-8 shadow-[0_24px_80px_rgba(15,23,42,0.1)] backdrop-blur-md sm:p-12"
      >
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">
          Knowledge Workbench
        </p>
        <h1 className="text-5xl font-semibold tracking-[-0.06em] text-slate-950 sm:text-7xl" id="guru-title">
          Guru
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-600">
          Local-first, repo-aware navigation for knowledge work.
        </p>
        <div className="mt-8">
          <Button type="button">Open workbench</Button>
        </div>
      </section>
    </main>
  );
}
