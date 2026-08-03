import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import HealthPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("HealthPage", () => {
  it("reports frontend health and contract boundary", async () => {
    render(<HealthPage />);
    expect(screen.getByRole("heading", { name: "Frontend health" })).toBeInTheDocument();
    expect(screen.getByText("Review 冻结契约已生成")).toBeInTheDocument();
    expect(await screen.findByText("mock-api")).toBeInTheDocument();
  });
});
