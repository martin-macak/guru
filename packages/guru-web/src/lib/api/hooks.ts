import { useQuery } from "@tanstack/react-query";

import { apiClient, getBoot } from "./client";

export function useBootQuery() {
  return useQuery({
    queryKey: ["boot"],
    queryFn: getBoot,
    retry: false,
  });
}

export interface DocumentListItem {
  path: string;
  title: string;
  excerpt: string;
}

export function useDocuments() {
  return useQuery<DocumentListItem[]>({
    queryKey: ["documents"],
    queryFn: async () => apiClient.get<DocumentListItem[]>("/documents"),
  });
}

export interface DocumentSearchHit {
  path: string;
  title: string;
  excerpt: string;
  score: number;
}

export async function searchDocuments(query: string, limit = 20): Promise<DocumentSearchHit[]> {
  const resp = await apiClient.post<{ hits: DocumentSearchHit[] }>("/documents/search", {
    query,
    limit,
  });
  return resp.hits;
}

export interface DocumentOut {
  path: string;
  title: string;
  content: string;
}

export function useDocument(path: string | null) {
  return useQuery<DocumentOut | null>({
    queryKey: ["document", path],
    queryFn: async () => {
      if (!path) return null;
      return apiClient.get<DocumentOut>(`/documents/${encodeURIComponent(path)}`);
    },
    enabled: !!path,
  });
}

export interface GraphQueryResult {
  nodes: { id: string; label: string; kind: string; kb?: string }[];
  edges: { source: string; target: string; kind: string }[];
}

export async function runGraphQuery(cypher: string): Promise<GraphQueryResult> {
  return apiClient.post<GraphQueryResult>("/graph/query", { cypher });
}
