import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { mockServer } from "../../test/msw";
import { useGraphRoots } from "./useGraphRoots";
import { wrapperWithQueryClient } from "../../test/render";

describe("useGraphRoots", () => {
  it("returns federation_root + kbs", async () => {
    mockServer.use(
      http.get("/graph/roots", () =>
        HttpResponse.json({
          federation_root: { id: "federation", label: "Federation" },
          kbs: [{ name: "local", project_root: "/p", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", last_seen_at: null, tags: [], metadata: {} }],
        }),
      ),
    );
    const { result } = renderHook(() => useGraphRoots(), { wrapper: wrapperWithQueryClient });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data!.federation_root.id).toBe("federation");
    expect(result.current.data!.kbs[0].name).toBe("local");
  });
});
