import { render, screen } from "../../test/render";
import { QueryPage } from "./QueryPage";

test("renders read-only query controls", () => {
  render(<QueryPage />);
  expect(screen.getByText("Read-only Query")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Run Query" })).toBeInTheDocument();
});
