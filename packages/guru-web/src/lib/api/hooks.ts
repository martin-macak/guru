import { useQuery } from "@tanstack/react-query";

import { apiClient, getBoot } from "./client";

export function useBootQuery() {
  return useQuery({
    queryKey: ["boot"],
    queryFn: getBoot,
    retry: false,
  });
}

export interface SyncStatus {
  lancedb_count: number;
  graph_count: number;
  drift: number;
  last_reconciled_at: string | null;
  graph_enabled: boolean;
}

export function useSyncStatus() {
  return useQuery<SyncStatus>({
    queryKey: ["sync", "status"],
    queryFn: async () => apiClient.get<SyncStatus>("/sync/status"),
    refetchInterval: 10_000,
  });
}

export async function reconcileSync(): Promise<SyncStatus> {
  return apiClient.post<SyncStatus>("/sync/reconcile", {});
}

export interface DocumentListItem {
  path: string;
  title: string;
  excerpt: string;
}

interface ServerDocumentListItem {
  file_path: string;
  frontmatter?: Record<string, unknown>;
  labels?: string[];
  chunk_count?: number;
}

interface ServerDocumentOut extends ServerDocumentListItem {
  content: string;
}

function adaptListItem(row: ServerDocumentListItem | DocumentListItem): DocumentListItem {
  // The server returns the storage shape (file_path, frontmatter, labels, chunk_count)
  // for CLI/MCP compatibility. Test mocks may provide the web shape directly
  // (path, title, excerpt); accept both.
  if ("path" in row && "title" in row) return row as DocumentListItem;
  const server = row as ServerDocumentListItem;
  const path = server.file_path;
  const frontmatterTitle = (server.frontmatter?.["title"] as string | undefined) ?? undefined;
  const title = frontmatterTitle || path.split("/").pop() || path;
  const excerpt = `${server.chunk_count ?? 0} chunks`;
  return { path, title, excerpt };
}

export function useDocuments() {
  return useQuery<DocumentListItem[]>({
    queryKey: ["documents"],
    queryFn: async () => {
      const rows = await apiClient.get<Array<ServerDocumentListItem | DocumentListItem>>(
        "/documents",
      );
      return rows.map(adaptListItem);
    },
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

function adaptDocumentOut(row: ServerDocumentOut | DocumentOut): DocumentOut {
  if ("path" in row && "title" in row) return row as DocumentOut;
  const server = row as ServerDocumentOut;
  const path = server.file_path;
  const frontmatterTitle = (server.frontmatter?.["title"] as string | undefined) ?? undefined;
  const title = frontmatterTitle || path.split("/").pop() || path;
  return { path, title, content: server.content };
}

export function useDocument(path: string | null) {
  return useQuery<DocumentOut | null>({
    queryKey: ["document", path],
    queryFn: async () => {
      if (!path) return null;
      const row = await apiClient.get<ServerDocumentOut | DocumentOut>(
        `/documents/${encodeURIComponent(path)}`,
      );
      return adaptDocumentOut(row);
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
