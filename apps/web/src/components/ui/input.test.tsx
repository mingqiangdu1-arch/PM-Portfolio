import { render, screen } from "@testing-library/react";
import { Input } from "./input";

describe("Input", () => {
  it("announces invalid state semantically", () => {
    render(<Input aria-label="项目名称" invalid />);
    expect(screen.getByRole("textbox", { name: "项目名称" })).toHaveAttribute("aria-invalid", "true");
  });
});
