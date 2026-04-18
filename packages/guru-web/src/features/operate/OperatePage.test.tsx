import { render, screen } from "../../test/render";
import { OperatePage } from "./OperatePage";

test("renders runtime status cards", () => {
  render(<OperatePage />);
  expect(screen.getByText("Server Status")).toBeInTheDocument();
  expect(screen.getByText("Graph Status")).toBeInTheDocument();
});
