import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";

import { renderWithRouter } from "../../test/render";
import { QueryInput } from "./QueryInput";

describe("QueryInput", () => {
  it("calls onRun with the cypher text when submitted", () => {
    const onRun = vi.fn();
    renderWithRouter(<QueryInput onRun={onRun} />);
    fireEvent.change(screen.getByLabelText(/cypher/i), { target: { value: "MATCH (n) RETURN n" } });
    fireEvent.click(screen.getByRole("button", { name: /^run$/i }));
    expect(onRun).toHaveBeenCalledWith("MATCH (n) RETURN n");
  });

  it("calls onRestore when Back to exploration clicked", () => {
    const onRestore = vi.fn();
    renderWithRouter(<QueryInput onRun={() => {}} onRestore={onRestore} inResultsMode />);
    fireEvent.click(screen.getByRole("button", { name: /back to exploration/i }));
    expect(onRestore).toHaveBeenCalled();
  });
});
