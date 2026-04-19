import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useGraphCanvas } from "./useGraphCanvas";
import { wrapperWithQueryClient } from "../../test/render";

const rootsPayload = {
  federation_root: { id: "federation" as const, label: "Federation" },
  kbs: [{ name: "local", project_root: "/p", tags: [] }],
};

describe("useGraphCanvas", () => {
  it("starts with roots only", () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    const ids = result.current.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["federation", "kb:local"]);
  });

  it("merges neighbors without duplicating existing nodes", async () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    await act(async () => {
      result.current.mergeNeighbors("doc:a.md", {
        nodes: [
          { id: "doc:a.md", label: "A", kind: "document", kb: "local" },
          { id: "kb:local", label: "local", kind: "kb" },
          { id: "doc:b.md", label: "B", kind: "document", kb: "local" },
        ],
        edges: [{ source: "doc:a.md", target: "doc:b.md", kind: "RELATED" }],
      });
    });
    const ids = result.current.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["doc:a.md", "doc:b.md", "federation", "kb:local"]);
  });

  it("clear resets to roots only", async () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    await act(async () => {
      result.current.mergeNeighbors("doc:a.md", {
        nodes: [{ id: "doc:a.md", label: "A", kind: "document", kb: "local" }],
        edges: [],
      });
      result.current.clear();
    });
    const ids = result.current.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["federation", "kb:local"]);
  });

  it("replaceProjection keeps roots and swaps extras", async () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    await act(async () => {
      result.current.replaceProjection({
        nodes: [
          { id: "doc:x", label: "X", kind: "document", kb: "local" },
          { id: "federation", label: "F", kind: "federation" },
        ],
        edges: [],
      });
    });
    expect(result.current.nodes.map((n) => n.id).sort()).toEqual(["doc:x", "federation", "kb:local"]);
  });

  it("restore rewinds to prior canvas state", async () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    await act(async () => {
      result.current.mergeNeighbors("doc:a", {
        nodes: [{ id: "doc:a", label: "A", kind: "document", kb: "local" }],
        edges: [],
      });
    });
    const snapshot = { nodes: result.current.nodes, edges: result.current.edges };
    await act(async () => {
      result.current.replaceProjection({ nodes: [{ id: "doc:x", label: "X", kind: "document", kb: "local" }], edges: [] });
    });
    expect(result.current.nodes.find((n) => n.id === "doc:x")).toBeDefined();
    await act(async () => result.current.restore(snapshot));
    expect(result.current.nodes.find((n) => n.id === "doc:a")).toBeDefined();
    expect(result.current.nodes.find((n) => n.id === "doc:x")).toBeUndefined();
  });
});
