import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentSearchBox } from "./DocumentSearchBox";

describe("DocumentSearchBox", () => {
  it("calls onResults with hits when query submitted", async () => {
    mockServer.use(
      http.post("/documents/search", () =>
        HttpResponse.json({ hits: [{ path: "a.md", title: "A", excerpt: "hit", score: 0.9 }] }),
      ),
    );
    const onResults = vi.fn();
    renderWithRouter(<DocumentSearchBox onResults={onResults} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "foo" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(onResults).toHaveBeenCalled());
    expect(onResults.mock.calls[0][0][0]).toEqual({
      path: "a.md",
      title: "A",
      excerpt: "hit",
      score: 0.9,
    });
  });

  it("clears results when input emptied", async () => {
    const onResults = vi.fn();
    renderWithRouter(<DocumentSearchBox onResults={onResults} />);
    const input = screen.getByPlaceholderText(/search/i);
    // Set a value first, then clear it to simulate the user emptying the input
    fireEvent.change(input, { target: { value: "something" } });
    fireEvent.change(input, { target: { value: "" } });
    expect(onResults).toHaveBeenLastCalledWith(null);
  });
});
