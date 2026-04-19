import { describe, expect, it } from "vitest";
import { computePathToRoot } from "./computePathToRoot";

describe("computePathToRoot", () => {
  it("returns [] when selection is the federation root", () => {
    expect(computePathToRoot("federation", "local")).toEqual([]);
  });

  it("returns [federation -> kb] when selection is a KB node", () => {
    expect(computePathToRoot("kb:local", "local")).toEqual([
      { source: "federation", target: "kb:local" },
    ]);
  });

  it("returns [federation -> kb -> doc] when selection is a document", () => {
    expect(computePathToRoot("doc:a.md", "local")).toEqual([
      { source: "federation", target: "kb:local" },
      { source: "kb:local", target: "doc:a.md" },
    ]);
  });

  it("returns [] when selection is null", () => {
    expect(computePathToRoot(null, "local")).toEqual([]);
  });
});
