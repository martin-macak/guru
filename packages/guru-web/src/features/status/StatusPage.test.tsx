import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { StatusPage } from "./StatusPage";

describe("StatusPage", () => {
  it("renders sync counts and reconcile button", async () => {
    mockServer.use(
      http.get("/sync/status", () =>
        HttpResponse.json({
          lancedb_count: 5,
          graph_count: 4,
          drift: 1,
          last_reconciled_at: null,
          graph_enabled: true,
        }),
      ),
    );
    renderWithRouter(<StatusPage />, { route: "/status" });
    await screen.findByText("LanceDB documents");
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("drift")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconcile now/i })).toBeInTheDocument();
  });

  it("triggers reconcile and updates counts", async () => {
    let phase = 0;
    mockServer.use(
      http.get("/sync/status", () => {
        phase++;
        return HttpResponse.json({
          lancedb_count: 5,
          graph_count: phase === 1 ? 4 : 5,
          drift: phase === 1 ? 1 : 0,
          last_reconciled_at: null,
          graph_enabled: true,
        });
      }),
      http.post("/sync/reconcile", () =>
        HttpResponse.json({
          lancedb_count: 5,
          graph_count: 5,
          drift: 0,
          last_reconciled_at: "now",
          graph_enabled: true,
        }),
      ),
    );
    renderWithRouter(<StatusPage />, { route: "/status" });
    await screen.findByText("1");
    fireEvent.click(screen.getByRole("button", { name: /reconcile now/i }));
    await waitFor(() => expect(screen.getByText("0")).toBeInTheDocument());
  });

  it("disables reconcile button when graph disabled", async () => {
    mockServer.use(
      http.get("/sync/status", () =>
        HttpResponse.json({
          lancedb_count: 5,
          graph_count: 0,
          drift: 5,
          last_reconciled_at: null,
          graph_enabled: false,
        }),
      ),
    );
    renderWithRouter(<StatusPage />, { route: "/status" });
    const btn = await screen.findByRole("button", { name: /reconcile now/i });
    expect(btn).toBeDisabled();
  });
});
