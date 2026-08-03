import { fireEvent, render, screen } from "@testing-library/react";
import { FilePanel } from "./file-panel";
import { frontendApi } from "@/lib/api/frontend-api";
it("retains a failed upload and exposes retry", async () => { render(<FilePanel projectId="atlas" scenario="failure" />); const file = new File(["source"], "research.pdf", { type: "application/pdf" }); fireEvent.change(screen.getByLabelText("选择资料"), { target: { files: [file] } }); expect(await screen.findByText("上传失败 · 62%")).toBeInTheDocument(); expect(screen.getByText(/存储暂不可用/)).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "重试此文件" })); expect(await screen.findByText("已上传 · 100%")).toBeInTheDocument(); });

it("retains the original file and retry affordance when retry rejects", async () => {
  const retry = vi.spyOn(frontendApi.files, "retry").mockRejectedValueOnce(new Error("重试存储失败"));
  const unhandledRejection = vi.fn();
  window.addEventListener("unhandledrejection", unhandledRejection);
  render(<FilePanel projectId="atlas" scenario="failure" />);
  const file = new File(["source"], "retry-me.pdf", { type: "application/pdf" });

  fireEvent.change(screen.getByLabelText("选择资料"), { target: { files: [file] } });
  expect(await screen.findByText("上传失败 · 62%")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "重试此文件" }));
  expect(await screen.findByText("重试存储失败")).toBeInTheDocument();
  expect(screen.getByText("上传失败 · 0%")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重试此文件" })).toBeEnabled();
  expect(retry).toHaveBeenCalledWith("atlas", expect.objectContaining({ name: "retry-me.pdf", retryFile: file }));
  expect(unhandledRejection).not.toHaveBeenCalled();

  window.removeEventListener("unhandledrejection", unhandledRejection);
  retry.mockRestore();
});
