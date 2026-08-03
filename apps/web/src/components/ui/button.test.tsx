import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("Button", () => {
  it("exposes loading state without relying on color", () => {
    render(<Button loading>保存</Button>);
    const button = screen.getByRole("button", { name: "保存" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});
