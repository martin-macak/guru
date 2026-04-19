export interface OverlayEdge {
  source: string;
  target: string;
}

export function computePathToRoot(selectedId: string | null, localKbName: string): OverlayEdge[] {
  if (!selectedId || selectedId === "federation") return [];
  const kbId = `kb:${localKbName}`;
  if (selectedId === kbId) return [{ source: "federation", target: kbId }];
  return [
    { source: "federation", target: kbId },
    { source: kbId, target: selectedId },
  ];
}
