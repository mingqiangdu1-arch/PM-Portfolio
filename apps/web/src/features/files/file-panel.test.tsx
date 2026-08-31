import { fireEvent, render, screen } from "@testing-library/react";
import { FilePanel } from "./file-panel";
import { frontendApi } from "@/lib/api/frontend-api";
it("retains a failed upload and exposes retry", async () => { render(<FilePanel projectId="atlas" scenario="failure" />); await screen.findByText("尚未上传资料"); const file = new File(["source"], "research.pdf", { type: "application/pdf" }); fireEvent.change(screen.getByLabelText("选择资料"), { target: { files: [file] } }); expect(await screen.findByText("上传失败 · 62%")).toBeInTheDocument(); expect(screen.getByText(/存储暂不可用/)).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "重试此文件" })); expect(await screen.findByText("已上传 · 100%")).toBeInTheDocument(); });

it("retains the original file and retry affordance when retry rejects", async () => {
  const retry = vi.spyOn(frontendApi.files, "retry").mockRejectedValueOnce(new Error("重试存储失败"));
  const unhandledRejection = vi.fn();
  window.addEventListener("unhandledrejection", unhandledRejection);
  render(<FilePanel projectId="atlas" scenario="failure" />);
  await screen.findByText("尚未上传资料");
  const file = new File(["source"], "retry-me.pdf", { type: "application/pdf" });

  fireEvent.change(screen.getByLabelText("选择资料"), { target: { files: [file] } });
  expect(await screen.findByText("上传失败 · 62%")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "重试此文件" }));
  expect(await screen.findByText("项目资料上传未完成，请稍后重试。")).toBeInTheDocument();
  expect(screen.getByText("上传失败 · 0%")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重试此文件" })).toBeEnabled();
  expect(retry).toHaveBeenCalledWith("atlas", expect.objectContaining({ name: "retry-me.pdf", retryFile: file }));
  expect(unhandledRejection).not.toHaveBeenCalled();

  window.removeEventListener("unhandledrejection", unhandledRejection);
  retry.mockRestore();
});

it("restores completed files when the project material page is reopened", async () => {
  const list = vi.spyOn(frontendApi.files, "list").mockResolvedValueOnce([
    { id: "version-1", name: "brief.txt", progress: 100, status: "uploaded", relation: null },
  ]);
  render(<FilePanel projectId="atlas" />);

  expect(await screen.findByText("brief.txt")).toBeInTheDocument();
  expect(screen.getByText("已上传 · 100%")).toBeInTheDocument();
  expect(list).toHaveBeenCalledWith("atlas");
  list.mockRestore();
});

it("rejects an empty file with clear copy before calling the upload API", async () => {
  const upload = vi.spyOn(frontendApi.files, "upload");
  render(<FilePanel projectId="atlas" />);
  await screen.findByText("尚未上传资料");

  fireEvent.change(screen.getByLabelText("选择资料"), { target: { files: [new File([], "empty.txt", { type: "text/plain" })] } });

  expect(await screen.findByRole("alert")).toHaveTextContent("文件内容为空，无法上传。");
  expect(screen.queryByRole("button", { name: "重试此文件" })).not.toBeInTheDocument();
  expect(upload).not.toHaveBeenCalled();
  upload.mockRestore();
});

it("does not expose an unexpected internal upload error", async () => {
  const upload = vi.spyOn(frontendApi.files, "upload").mockRejectedValueOnce(new Error("internal stack: minio.local"));
  render(<FilePanel projectId="atlas" />);
  await screen.findByText("尚未上传资料");

  fireEvent.change(screen.getByLabelText("选择资料"), { target: { files: [new File(["content"], "brief.txt", { type: "text/plain" })] } });

  expect(await screen.findByRole("alert")).toHaveTextContent("项目资料上传未完成，请稍后重试。");
  expect(screen.queryByText(/minio\.local/)).not.toBeInTheDocument();
  upload.mockRestore();
});
