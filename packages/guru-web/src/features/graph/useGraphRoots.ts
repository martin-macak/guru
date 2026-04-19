import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../lib/api/client";

export interface Kb {
  name: string;
  project_root: string;
  tags: string[];
}
export interface GraphRoots {
  federation_root: { id: "federation"; label: string };
  kbs: Kb[];
}

export function useGraphRoots() {
  return useQuery<GraphRoots>({
    queryKey: ["graph", "roots"],
    queryFn: async () => apiClient.get<GraphRoots>("/graph/roots"),
  });
}
