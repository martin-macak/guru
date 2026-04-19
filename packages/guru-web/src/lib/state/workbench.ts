import { create } from "zustand";

import type { BootPayload } from "../api/client";
import type { WorkbenchSurface } from "./url";

interface WorkbenchState {
  boot: BootPayload;
  surface: WorkbenchSurface;
  selectedDocumentPath: string | null;
  selectedGraphNodeId: string | null;
  rightPaneOpen: Record<WorkbenchSurface, boolean>;

  setSurface: (s: WorkbenchSurface) => void;
  selectDocument: (path: string | null) => void;
  selectGraphNode: (id: string | null) => void;
  toggleRightPane: (s: WorkbenchSurface) => void;
  setBoot: (b: BootPayload) => void;
}

function loadPaneState(): Record<WorkbenchSurface, boolean> {
  try {
    const raw = localStorage.getItem("guru.workbench.paneState");
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore
  }
  return { documents: true, graph: true, status: false };
}

function savePaneState(state: Record<WorkbenchSurface, boolean>) {
  try {
    localStorage.setItem("guru.workbench.paneState", JSON.stringify(state));
  } catch {
    // ignore
  }
}

export const useWorkbench = create<WorkbenchState>((set) => ({
  boot: {
    project: { name: "", root: "" },
    web: { enabled: true, available: true, url: null, reason: null, autoOpen: false },
    graph: { enabled: false },
  },
  surface: "documents",
  selectedDocumentPath: null,
  selectedGraphNodeId: null,
  rightPaneOpen: loadPaneState(),

  setSurface: (s) => set({ surface: s }),
  selectDocument: (path) => set({ selectedDocumentPath: path }),
  selectGraphNode: (id) => set({ selectedGraphNodeId: id }),
  toggleRightPane: (s) =>
    set((prev) => {
      const next = { ...prev.rightPaneOpen, [s]: !prev.rightPaneOpen[s] };
      savePaneState(next);
      return { rightPaneOpen: next };
    }),
  setBoot: (b) => set({ boot: b }),
}));
