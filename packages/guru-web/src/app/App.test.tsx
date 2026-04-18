import { render, screen } from "../test/render";
import { App } from "./App";

test("renders guru web shell title", () => {
  render(<App />);
  expect(screen.getByText("Guru")).toBeInTheDocument();
  expect(screen.getByText("Knowledge Workbench")).toBeInTheDocument();
});
