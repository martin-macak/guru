import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { RightPane } from "../../app/layout/RightPane";
import { useWorkbench } from "../../lib/state/workbench";
import type { DocumentSearchHit } from "../../lib/api/hooks";
import { DocumentDetail } from "./DocumentDetail";
import { DocumentList } from "./DocumentList";
import { DocumentMetaPane } from "./DocumentMetaPane";
import { DocumentSearchBox } from "./DocumentSearchBox";

export function DocumentsPage() {
  const params = useParams();
  const navigate = useNavigate();
  const setSurface = useWorkbench((s) => s.setSurface);
  const boot = useWorkbench((s) => s.boot);
  const selectedPath = params["*"] || null;
  const [hits, setHits] = useState<DocumentSearchHit[] | null>(null);

  useEffect(() => setSurface("documents"), [setSurface]);

  function onSelect(path: string) {
    navigate(`/documents/${path}`);
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <section className="flex w-[320px] flex-col border-r border-neutral-200 bg-white">
        <DocumentSearchBox onResults={setHits} />
        <div className="flex-1 overflow-auto">
          {hits ? (
            <ul className="divide-y divide-neutral-200">
              {hits.map((hit) => (
                <li
                  key={hit.path}
                  aria-selected={hit.path === selectedPath}
                  onClick={() => onSelect(hit.path)}
                  className={
                    "cursor-pointer p-3 text-sm " +
                    (hit.path === selectedPath
                      ? "bg-neutral-900 text-white"
                      : "hover:bg-neutral-100")
                  }
                >
                  <div className="font-medium">{hit.title}</div>
                  <div className="text-xs text-neutral-500">
                    score {hit.score.toFixed(2)} · {hit.excerpt}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <DocumentList onSelect={onSelect} selectedPath={selectedPath} />
          )}
        </div>
      </section>
      <section className="flex flex-1 overflow-hidden">
        {selectedPath ? (
          <div className="flex-1 overflow-auto">
            <DocumentDetail path={selectedPath} />
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-neutral-500">
            Select a document to view its content.
          </div>
        )}
        <RightPane>
          {selectedPath ? (
            <DocumentMetaPane path={selectedPath} graphEnabled={boot.graph.enabled} />
          ) : (
            <p className="text-sm text-neutral-500">Select a document to see its metadata.</p>
          )}
        </RightPane>
      </section>
    </div>
  );
}
