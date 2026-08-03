import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { frontendApi } from "@/lib/api/frontend-api";
import { VersionDetail } from "./version-manager";
import { VersionManager } from "./version-manager";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("VersionManager", () => {
  it("leaves loading on list failure and recovers with retry", async () => {
    const list = vi.spyOn(frontendApi.projects, "versions");
    list.mockRejectedValueOnce(new Error("网络暂不可用")).mockResolvedValueOnce([
      {
        id: "atlas-v2",
        number: "V2",
        source: "atlas-v1",
        reason: "补充目标用户约束",
        createdAt: "2026-07-29T09:30:00Z",
        isWorking: true,
      },
    ]);

    render(<VersionManager projectId="atlas" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("版本列表加载失败");
    expect(screen.queryByText("正在加载版本谱系…")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("当前工作版本")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("shows an explicit empty state after an empty response", async () => {
    vi.spyOn(frontendApi.projects, "versions").mockResolvedValueOnce([]);

    render(<VersionManager projectId="atlas" />);

    expect(await screen.findByText("暂无版本")).toBeInTheDocument();
    expect(screen.queryByText("正在加载版本谱系…")).not.toBeInTheDocument();
  });
});

describe("VersionDetail", () => {
  it("keeps historical viewing read-only", async () => {
    render(<VersionDetail projectId="atlas" versionId="atlas-v1" />);
    expect(await screen.findByText("历史版本只读")).toBeInTheDocument();
    expect(screen.getByText(/查看 V1 · 当前工作版本 V2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "设为工作版本" })).toBeDisabled();
  });

  it("preserves derive reason after conflict", async () => {
    render(<VersionDetail projectId="atlas" versionId="atlas-v1" scenario="conflict" />);
    await screen.findByText("历史版本只读");
    fireEvent.change(screen.getByLabelText("派生原因"), { target: { value: "保留这条原因" } });
    fireEvent.click(screen.getByRole("button", { name: "确认派生新版本" }));
    expect(await screen.findByText("版本冲突")).toBeInTheDocument();
    expect(screen.getByLabelText("派生原因")).toHaveValue("保留这条原因");
  });
});
