import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { frontendApi } from "@/lib/api/frontend-api";
import { SessionRecovery } from "./session-recovery";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

afterEach(() => {
  vi.restoreAllMocks();
  push.mockClear();
});

it("keeps a safe return target when sending the user to login", () => {
  render(<SessionRecovery returnTo="https://untrusted.example/steal" />);

  fireEvent.click(screen.getByRole("button", { name: "重新登录" }));

  expect(push).toHaveBeenCalledWith("/login?returnTo=%2Fprojects");
});

it("keeps the return target and offers login after refresh failure", async () => {
  vi.spyOn(frontendApi.identity, "refresh").mockRejectedValue(new Error("refresh failed"));
  render(<SessionRecovery returnTo="/projects/atlas/versions/atlas-v1" />);

  fireEvent.click(screen.getByRole("button", { name: "恢复会话" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("会话恢复失败，请重新登录");
  expect(push).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重新登录" }));
  expect(push).toHaveBeenCalledWith(
    "/login?returnTo=%2Fprojects%2Fatlas%2Fversions%2Fatlas-v1",
  );
});
