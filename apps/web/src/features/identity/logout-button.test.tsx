import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { frontendApi } from "@/lib/api/frontend-api";
import { LogoutButton } from "./logout-button";
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

afterEach(() => {
  vi.restoreAllMocks();
  push.mockClear();
});

it("invalidates the session before returning to login", async () => {
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "退出" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/login?loggedOut=1"));
});

it("shows a safe recovery path when logout fails without leaking the error", async () => {
  vi.spyOn(frontendApi.identity, "logout").mockRejectedValue(new Error("Bearer secret-token"));
  render(<LogoutButton />);

  fireEvent.click(screen.getByRole("button", { name: "退出" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("本地会话已清理");
  expect(screen.getByRole("alert")).not.toHaveTextContent("secret-token");
  expect(push).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "前往登录" }));
  expect(push).toHaveBeenCalledWith("/login?loggedOut=1");
});
