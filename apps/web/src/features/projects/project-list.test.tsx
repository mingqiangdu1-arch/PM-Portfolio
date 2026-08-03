import { fireEvent, render, screen } from "@testing-library/react";
import { ProjectList } from "./project-list";
describe("ProjectList states", () => { it("distinguishes first empty from filtered empty", async () => { const { unmount } = render(<ProjectList scenario="empty" />); expect(await screen.findByText("还没有项目")).toBeInTheDocument(); unmount(); render(<ProjectList scenario="filtered-empty" />); expect(await screen.findByText("没有匹配的项目")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "清除筛选" })); expect(screen.getByText("还没有项目")).toBeInTheDocument(); }); });
