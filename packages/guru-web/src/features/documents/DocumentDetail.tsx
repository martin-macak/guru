import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate } from "react-router-dom";

import { useDocument } from "../../lib/api/hooks";

export function DocumentDetail({ path }: { path: string }) {
  const { data, isLoading } = useDocument(path);
  const navigate = useNavigate();
  if (isLoading) return <div className="p-6 text-sm text-neutral-500">Loading…</div>;
  if (!data) return null;
  return (
    <article className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 p-4">
        <h1 className="text-xl font-semibold">{data.title}</h1>
        <button
          type="button"
          onClick={() => navigate(`/graph?focus=${encodeURIComponent(`doc:${data.path}`)}`)}
          className="rounded bg-neutral-900 px-3 py-1 text-sm text-white hover:bg-neutral-700"
        >
          Go to graph
        </button>
      </header>
      <div className="flex-1 overflow-auto p-6 prose prose-neutral max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content}</ReactMarkdown>
      </div>
    </article>
  );
}
