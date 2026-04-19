import { createHashRouter, Navigate } from "react-router-dom";

import { DocumentsPage } from "../features/documents/DocumentsPage";
import { GraphPage } from "../features/graph/GraphPage";
import { StatusPage } from "../features/status/StatusPage";
import { AppShell } from "./layout/AppShell";

export const router = createHashRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/documents" replace /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/*", element: <DocumentsPage /> },
      { path: "graph", element: <GraphPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "*", element: <Navigate to="/documents" replace /> },
    ],
  },
]);
