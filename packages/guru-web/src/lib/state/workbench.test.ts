import { describe, expect, it } from "vitest";

import { useWorkbench } from "./workbench";
import { workbenchSurfaces } from "./url";

describe("workbench store", () => {
  it("surfaces are exactly documents, graph, status", () => {
    expect(workbenchSurfaces).toEqual(["documents", "graph", "status"]);
  });

  it("has no hardcoded entity or investigation mock data", () => {
    const state = useWorkbench.getState() as unknown as Record<string, unknown>;
    expect(state).not.toHaveProperty("workbenchEntities");
    expect(state).not.toHaveProperty("investigateResults");
  });
});
