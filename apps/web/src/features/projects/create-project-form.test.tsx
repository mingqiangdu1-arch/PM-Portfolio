import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { CreateProjectForm } from "./create-project-form";
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
it("preserves the form when creation fails", async () => { render(<CreateProjectForm scenario="failure" />); fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "保留名称" } }); fireEvent.change(screen.getByLabelText("项目目标"), { target: { value: "保留目标" } }); fireEvent.click(screen.getByRole("button", { name: "创建项目与 V1" })); expect(await screen.findByRole("alert")).toHaveTextContent("表单内容已保留"); expect(screen.getByLabelText("项目名称")).toHaveValue("保留名称"); expect(screen.getByLabelText("项目目标")).toHaveValue("保留目标"); expect(push).not.toHaveBeenCalled(); });
it("opens the generated V1 overview after success", async () => { push.mockClear(); render(<CreateProjectForm />); fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "新项目" } }); fireEvent.change(screen.getByLabelText("项目目标"), { target: { value: "验证目标" } }); fireEvent.click(screen.getByRole("button", { name: "创建项目与 V1" })); await waitFor(() => expect(push).toHaveBeenCalledWith("/projects/new-project?created=1")); });
